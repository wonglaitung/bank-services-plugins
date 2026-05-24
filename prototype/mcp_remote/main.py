"""
远端 MCP 服务

提供真正的 MCP 服务，定义所有 Tools。
从加密 Token 中解密获取用户编号，用于数据查询。

关键安全原则：
- Tools 不接受 user_id 参数
- 用户编号从加密 Token 解密获取
- 所有数据查询强制使用当前用户编号
"""

import os
import sys
import json
import base64
import logging
from datetime import datetime, timezone
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


# ==================== Token 解密 ====================

def decrypt_token(token_b64: str) -> dict:
    """
    解密 Token 获取用户身份

    Args:
        token_b64: Base64 编码的加密 Token

    Returns:
        包含 user_id, expires_at 的字典

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
        if response.status_code == 404:
            return {"error": "用户不存在"}
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
        if response.status_code == 404:
            return {"error": "用户不存在"}
        response.raise_for_status()
        user_data = response.json()
        return {
            "user_id": user_id,
            "name": user_data.get("name"),
            "department": user_data.get("department")
        }


@mcp.tool()
async def get_my_balance() -> dict:
    """
    获取当前用户的账户余额

    返回当前用户的财务余额信息。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        if response.status_code == 404:
            return {"error": "用户不存在"}
        response.raise_for_status()
        user_data = response.json()
        return {
            "user_id": user_id,
            "name": user_data.get("name"),
            "balance": user_data.get("balance", 0)
        }


@mcp.tool()
async def check_my_permission() -> dict:
    """
    检查当前用户的权限

    返回当前用户的角色和基本权限信息。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        if response.status_code == 404:
            return {"error": "用户不存在"}
        response.raise_for_status()
        user_data = response.json()
        role = user_data.get("role", "unknown")

        return {
            "user_id": user_id,
            "name": user_data.get("name"),
            "role": role,
            "permissions": {
                "can_view": True,
                "can_edit": role == "admin",
                "can_delete": role == "admin",
                "can_approve": role == "admin"
            }
        }


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
