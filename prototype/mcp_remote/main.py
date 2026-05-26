"""
远端 MCP 服务

提供真正的 MCP 服务，定义所有 Tools。
从加密 Token 中解密获取用户编号，用于数据查询。

关键安全原则：
- Tools 不接受 user_id 参数
- 用户编号从加密 Token 解密获取
- 所有数据查询强制使用当前用户编号

Token 机制：
- Access Token: 15 分钟有效期，用于 API 调用
- Refresh Token: 7 天有效期，用于获取新 Access Token
- Access Token 无需吊销（有效期短）
- Refresh Token 支持吊销
"""

import os
import sys
import json
import base64
import logging
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from mcp.server.fastmcp import FastMCP

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("错误: 需要安装 cryptography 库")
    print("运行: pip install cryptography")
    sys.exit(1)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 当前用户上下文（每个请求独立）
current_user_id: ContextVar[str] = ContextVar("current_user_id")

# 创建 MCP 服务
mcp = FastMCP("FinanceService")

# FastAPI 应用
app = FastAPI(title="MCP 远端服务")

# 配置
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8000")

# Token 加密密钥（从环境变量读取）
_TOKEN_KEY_B64 = os.environ.get("TOKEN_KEY")
if _TOKEN_KEY_B64:
    TOKEN_KEY = base64.b64decode(_TOKEN_KEY_B64)
else:
    # 原型测试时使用固定密钥（生产环境必须从环境变量读取）
    TOKEN_KEY = b'prototype-test-key-32-bytes-!!!!'  # 32 bytes
    logger.warning("使用测试密钥，生产环境请设置 TOKEN_KEY 环境变量")

# Token 类型
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Access Token 有效期
ACCESS_TOKEN_EXPIRES_MINUTES = 15

# 文件路径（与 tools 目录共享）
TOOLS_DIR = Path(__file__).parent.parent / "tools"
REVOKED_TOKENS_FILE = TOOLS_DIR / "revoked_tokens.json"
TOKEN_RECORDS_FILE = TOOLS_DIR / "token_records.json"


# ==================== 吊销黑名单管理 ====================

def load_revoked_tokens() -> set:
    """加载吊销的 Token JTI 黑名单"""
    if REVOKED_TOKENS_FILE.exists():
        with open(REVOKED_TOKENS_FILE, 'r') as f:
            return set(json.load(f))
    return set()


def save_revoked_tokens(revoked_set: set):
    """保存吊销黑名单"""
    with open(REVOKED_TOKENS_FILE, 'w') as f:
        json.dump(list(revoked_set), f, indent=2)


def is_token_revoked(jti: str) -> bool:
    """检查 Token 是否被吊销"""
    revoked = load_revoked_tokens()
    return jti in revoked


def add_to_revoked_list(jti: str):
    """添加到吊销黑名单"""
    revoked = load_revoked_tokens()
    revoked.add(jti)
    save_revoked_tokens(revoked)


def load_token_records() -> list:
    """加载 Token 记录"""
    if TOKEN_RECORDS_FILE.exists():
        with open(TOKEN_RECORDS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_token_records(records: list):
    """保存 Token 记录"""
    with open(TOKEN_RECORDS_FILE, 'w') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def update_token_status(jti: str, status: str):
    """更新 Token 记录状态"""
    records = load_token_records()
    for record in records:
        if record.get("refresh_jti") == jti:
            record["status"] = status
    save_token_records(records)


# ==================== Token 解密 ====================

def decrypt_token(token_b64: str) -> dict:
    """
    解密 Token 获取用户身份

    Args:
        token_b64: Base64 编码的加密 Token

    Returns:
        包含 user_id, token_type, jti, expires_at 的字典

    Raises:
        ValueError: Token 无效或过期
    """
    try:
        # 1. Base64 解码
        encrypted = base64.b64decode(token_b64)

        # 2. 解析 nonce 和 ciphertext
        if len(encrypted) < 12:
            raise ValueError("Token 格式错误")
        nonce = encrypted[:12]
        ciphertext_with_tag = encrypted[12:]

        # 3. AES-GCM 解密
        aesgcm = AESGCM(TOKEN_KEY)
        plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)

        # 4. 解析 JSON
        token_data = json.loads(plaintext.decode('utf-8'))

        # 5. 验证必要字段
        if 'user_id' not in token_data or 'expires_at' not in token_data:
            raise ValueError("Token 缺少必要字段")

        # 6. 验证有效期
        expires_at_str = token_data['expires_at']
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            raise ValueError("Token 已过期")

        return token_data

    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Token 解密失败: {str(e)}")


# ==================== Token 生成 ====================

def generate_access_token(user_id: str) -> str:
    """
    生成新的 Access Token

    Args:
        user_id: 用户编号

    Returns:
        Base64 编码的加密 Token
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES)
    jti = secrets.token_urlsafe(16)

    token_data = {
        "user_id": user_id,
        "token_type": TOKEN_TYPE_ACCESS,
        "jti": jti,
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    # AES-GCM 加密
    aesgcm = AESGCM(TOKEN_KEY)
    nonce = os.urandom(12)
    plaintext = json.dumps(token_data).encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # 组装并 Base64 编码
    encrypted = nonce + ciphertext
    return base64.b64encode(encrypted).decode('utf-8')


# ==================== 认证端点 ====================

@app.post("/auth/refresh")
async def refresh_token(request: Request):
    """
    使用 Refresh Token 获取新的 Access Token

    请求: {"refresh_token": "xxx"}
    响应: {"access_token": "yyy", "expires_in": 900}
    """
    try:
        data = await request.json()
        refresh_token = data.get("refresh_token")

        if not refresh_token:
            raise HTTPException(400, "缺少 refresh_token")

        # 验证 Refresh Token
        token_data = decrypt_token(refresh_token)

        if token_data.get("token_type") != TOKEN_TYPE_REFRESH:
            raise HTTPException(401, "需要 Refresh Token")

        # 检查吊销黑名单
        jti = token_data.get("jti")
        if is_token_revoked(jti):
            raise HTTPException(401, "Token 已被吊销")

        user_id = token_data["user_id"]

        # 生成新的 Access Token
        access_token = generate_access_token(user_id)

        logger.info(f"Token 刷新成功: user={user_id}")

        return {
            "access_token": access_token,
            "expires_in": ACCESS_TOKEN_EXPIRES_MINUTES * 60  # 秒
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Token 刷新失败: {e}")
        raise HTTPException(401, str(e))
    except Exception as e:
        logger.error(f"Token 刷新异常: {e}")
        raise HTTPException(500, "刷新失败")


@app.post("/auth/revoke")
async def revoke_token(request: Request):
    """
    吊销 Refresh Token

    请求: {"jti": "abc123"}
    响应: {"status": "revoked"}
    """
    try:
        data = await request.json()
        jti = data.get("jti")

        if not jti:
            raise HTTPException(400, "缺少 jti")

        # 添加到黑名单
        add_to_revoked_list(jti)

        # 更新 Token 记录状态
        update_token_status(jti, "revoked")

        logger.info(f"Token 已吊销: jti={jti}")

        return {"status": "revoked"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"吊销 Token 异常: {e}")
        raise HTTPException(500, "吊销失败")


# ==================== 认证中间件 ====================

async def verify_request(request: Request) -> str:
    """
    验证请求并返回用户编号

    从 Authorization Header 提取加密 Token，解密获取用户编号。

    Returns:
        验证通过的用户编号

    Raises:
        HTTPException: 认证失败
    """
    # 提取 Token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_b64 = auth_header[7:]  # 去掉 "Bearer " 前缀
    else:
        token_b64 = auth_header

    if not token_b64:
        logger.warning("缺少认证 Token")
        raise HTTPException(401, "缺少认证 Token")

    try:
        # 解密 Token
        token_data = decrypt_token(token_b64)
        user_id = token_data["user_id"]

        # 验证 Token 类型（必须是 Access Token）
        token_type = token_data.get("token_type", TOKEN_TYPE_ACCESS)
        if token_type != TOKEN_TYPE_ACCESS:
            raise HTTPException(401, "需要 Access Token")

        # 验证用户编号格式（必须为9位数字）
        if not user_id.isdigit() or len(user_id) != 9:
            logger.warning(f"用户编号格式错误: {user_id}")
            raise HTTPException(400, "用户编号格式错误")

        logger.info(f"用户认证成功: {user_id}")
        return user_id

    except ValueError as e:
        logger.warning(f"Token 验证失败: {e}")
        raise HTTPException(401, str(e))


# ==================== MCP Tools 定义 ====================

@mcp.tool()
async def get_my_info() -> dict:
    """
    获取当前用户的信息

    返回当前登录用户的详细信息，包括姓名、部门、角色等。
    不接受任何用户标识参数，身份从认证上下文获取。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_my_department() -> dict:
    """
    获取当前用户所在部门的信息

    返回当前用户所属部门的基本信息。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_my_balance() -> dict:
    """
    获取当前用户的账户余额

    返回当前用户的财务余额信息。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def check_my_permission() -> dict:
    """
    检查当前用户的权限

    返回当前用户的角色和基本权限信息。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def list_all_users() -> dict:
    """
    管理员查询所有用户信息（不含金额）

    只有 admin 角色的用户才能调用此工具。
    返回所有用户的基本信息列表，不包括余额数据。
    权限检查由后台 API 执行。

    Returns:
        用户列表，包含 total 和 users 字段
        非管理员返回错误信息
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/admin/{user_id}/users")
        if response.status_code >= 400:
            return response.json()
        return response.json()


# ==================== MCP 请求端点 ====================

@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """
    处理 MCP JSON-RPC 请求

    1. 验证认证信息（解密 Token）
    2. 注入用户上下文
    3. 根据 method 调用对应的 MCP 方法
    """
    try:
        # 验证认证（解密 Token 获取 user_id）
        user_id = await verify_request(request)

        # 注入用户上下文
        current_user_id.set(user_id)

        # 获取 MCP 请求体
        mcp_request = await request.json()
        method = mcp_request.get("method", "")
        request_id = mcp_request.get("id")

        # 记录审计日志
        logger.info(f"MCP 请求: method={method}, user={user_id}")

        # 根据 method 处理请求
        if method == "tools/list":
            # 返回工具列表
            tools = await mcp.list_tools()
            return {
                "jsonrpc": "2.0",
                "result": {"tools": tools},
                "id": request_id
            }

        elif method == "tools/call":
            # 调用工具
            params = mcp_request.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            result = await mcp.call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": str(result)}]},
                "id": request_id
            }

        elif method == "initialize":
            # 初始化响应
            return {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "FinanceService", "version": "1.0.0"}
                },
                "id": request_id
            }

        elif method == "notifications/initialized":
            # initialized notification 不需要响应
            logger.info(f"客户端初始化完成: user={user_id}")
            return None

        elif method == "ping":
            # ping 请求
            return {
                "jsonrpc": "2.0",
                "result": {},
                "id": request_id
            }

        else:
            # 未知方法：notification 不返回错误，request 返回错误
            if request_id is None:
                logger.warning(f"忽略未知 notification: {method}")
                return None
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": request_id
            }

    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": e.detail}
        )
    except Exception as e:
        logger.error(f"处理 MCP 请求失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"内部服务器错误: {str(e)}"}
        )


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)