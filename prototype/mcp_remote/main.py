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
import functools
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from mcp.server.fastmcp import FastMCP

try:
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.backends import default_backend
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


# ==================== 安全调用装饰器 ====================

def secure_api_call(func):
    """
    安全 API 调用装饰器

    统一处理 API 调用异常，确保返回格式化的错误信息。
    防止原始异常信息暴露给大模型，避免干扰模型判断。
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            logger.error(f"后端接口调用失败: {e.response.status_code}")
            return {"error": f"后端接口调用失败: HTTP {e.response.status_code}"}
        except httpx.ConnectError as e:
            logger.error(f"无法连接后端服务: {e}")
            return {"error": "无法连接后端服务，请检查服务状态"}
        except httpx.TimeoutException as e:
            logger.error(f"后端服务响应超时: {e}")
            return {"error": "后端服务响应超时"}
        except Exception as e:
            logger.error(f"内部处理错误: {e}")
            return {"error": "内部处理错误，请联系管理员"}
    return wrapper

# 配置
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8000")

# RSA 密钥（从环境变量读取）
def load_rsa_keys():
    """加载 RSA 密钥对"""
    private_key = None
    public_key = None

    # 加载私钥
    env_private = os.environ.get("RSA_PRIVATE_KEY")
    if env_private:
        private_key = serialization.load_pem_private_key(
            env_private.encode('utf-8'),
            password=None,
            backend=default_backend()
        )
    else:
        # 从文件加载
        private_key_file = Path(__file__).parent.parent / "tools" / "private_key.pem"
        if private_key_file.exists():
            with open(private_key_file, 'rb') as f:
                private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            logger.info(f"从文件加载私钥: {private_key_file}")

    # 加载公钥
    env_public = os.environ.get("RSA_PUBLIC_KEY")
    if env_public:
        public_key = serialization.load_pem_public_key(
            env_public.encode('utf-8'),
            backend=default_backend()
        )
    else:
        # 从文件加载
        public_key_file = Path(__file__).parent.parent / "tools" / "public_key.pem"
        if public_key_file.exists():
            with open(public_key_file, 'rb') as f:
                public_key = serialization.load_pem_public_key(
                    f.read(),
                    backend=default_backend()
                )
            logger.info(f"从文件加载公钥: {public_key_file}")

    if not private_key:
        logger.warning("未找到 RSA 私钥，请设置 RSA_PRIVATE_KEY 环境变量或生成密钥对")

    if not public_key:
        logger.warning("未找到 RSA 公钥，请设置 RSA_PUBLIC_KEY 环境变量或生成密钥对")

    return private_key, public_key

# 全局密钥
RSA_PRIVATE_KEY, RSA_PUBLIC_KEY = load_rsa_keys()

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
    用 RSA 私钥解密 Token 获取用户身份

    Args:
        token_b64: Base64 编码的加密 Token

    Returns:
        包含 user_id, token_type, jti, expires_at 的字典

    Raises:
        ValueError: Token 无效或过期
    """
    try:
        if not RSA_PRIVATE_KEY:
            raise ValueError("服务未配置 RSA 私钥")

        # 1. 清理 Token 字符串
        token_b64 = token_b64.strip()

        # 2. 补齐 Base64 padding（如果需要）
        padding_needed = 4 - (len(token_b64) % 4)
        if padding_needed != 4:
            token_b64 += '=' * padding_needed

        # 3. Base64 解码
        ciphertext = base64.b64decode(token_b64)

        # 4. RSA-OAEP 解密
        plaintext = RSA_PRIVATE_KEY.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        # 5. 解析 JSON
        token_data = json.loads(plaintext.decode('utf-8'))

        # 6. 验证必要字段
        if 'user_id' not in token_data or 'expires_at' not in token_data:
            raise ValueError("Token 缺少必要字段")

        # 7. 验证有效期
        expires_at_str = token_data['expires_at']
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            raise ValueError("Token 已过期")

        return token_data

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Token 解密失败: {str(e)}")


# ==================== Token 生成 ====================

def generate_access_token(user_id: str) -> str:
    """
    用 RSA 公钥生成新的 Access Token

    Args:
        user_id: 用户编号

    Returns:
        Base64 编码的加密 Token
    """
    if not RSA_PUBLIC_KEY:
        raise ValueError("服务未配置 RSA 公钥")

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

    # RSA-OAEP 加密
    plaintext = json.dumps(token_data).encode('utf-8')
    ciphertext = RSA_PUBLIC_KEY.encrypt(
        plaintext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    return base64.b64encode(ciphertext).decode('utf-8')


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
@secure_api_call
async def get_my_info() -> dict:
    """
    获取当前用户的完整个人信息。

    当用户询问"我的信息"、"我是谁"、"我的资料"、"个人信息"或"查看我的账户"时调用此工具。

    返回内容：
    - user_id: 用户编号
    - name: 姓名
    - department: 部门
    - role: 角色（viewer/admin）
    - balance: 账户余额

    此工具不接受任何用户标识参数，身份从认证上下文自动获取。
    仅能查询当前已认证用户的信息，严禁用于尝试获取他人数据。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        response.raise_for_status()
        return response.json()


@mcp.tool()
@secure_api_call
async def get_my_department() -> dict:
    """
    获取当前用户所在的部门信息。

    当用户询问"我的部门"、"我在哪个部门"、"部门信息"、"所属部门"或"我是哪个部门的"时调用此工具。

    返回内容：
    - user_id: 用户编号
    - name: 姓名
    - department: 部门名称

    此工具仅返回部门相关数据，不包含余额、角色等其他信息。
    如需完整信息，请使用 get_my_info 工具。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        response.raise_for_status()
        user_data = response.json()
        # 过滤只返回部门相关信息
        return {
            "user_id": user_data.get("user_id"),
            "name": user_data.get("name"),
            "department": user_data.get("department")
        }


@mcp.tool()
@secure_api_call
async def get_my_balance() -> dict:
    """
    获取当前用户的账户余额。

    当用户询问"我的余额"、"我还有多少钱"、"账户余额"、"财务状况"、"多少钱"或"余额查询"时调用此工具。

    返回内容：
    - user_id: 用户编号
    - name: 姓名
    - balance: 账户余额（数值）

    此工具不接受任何用户标识参数，身份从认证上下文自动获取。
    仅能查询当前已认证用户的余额，严禁用于尝试获取他人数据。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        response.raise_for_status()
        user_data = response.json()
        # 过滤只返回余额相关信息
        return {
            "user_id": user_data.get("user_id"),
            "name": user_data.get("name"),
            "balance": user_data.get("balance", 0)
        }


@mcp.tool()
@secure_api_call
async def check_my_permission() -> dict:
    """
    检查当前用户的权限和角色。

    当用户询问"我的权限"、"我能做什么"、"角色信息"、"我的角色"、"有什么权限"或"权限查询"时调用此工具。

    返回内容：
    - user_id: 用户编号
    - name: 姓名
    - department: 部门
    - role: 角色（viewer=普通用户，admin=管理员）

    角色说明：
    - viewer: 普通用户，仅能查询自己的数据
    - admin: 管理员，可调用 list_all_users 查询所有用户

    此工具不接受任何用户标识参数，身份从认证上下文自动获取。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        response.raise_for_status()
        user_data = response.json()
        # 过滤只返回权限相关信息
        return {
            "user_id": user_data.get("user_id"),
            "name": user_data.get("name"),
            "department": user_data.get("department"),
            "role": user_data.get("role")
        }


@mcp.tool()
@secure_api_call
async def list_all_users() -> dict:
    """
    【管理员权限工具】查询所有用户的基本信息列表。

    仅限 admin 角色的用户才能调用此工具。
    当管理员需要查看"所有用户"、"用户列表"、"有多少用户"、"全部用户"或"用户统计"时调用。

    返回内容：
    - total: 用户总数
    - users: 用户列表，每个用户包含：
        - user_id: 用户编号
        - name: 姓名
        - department: 部门
        - role: 角色

    不包含 balance（余额）字段，保护用户财务隐私。

    权限检查由后台 API 执行，非管理员调用将返回 403 错误。
    如不确定自己的角色，请先调用 check_my_permission 工具查询。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/admin/{user_id}/users")
        if response.status_code >= 400:
            return response.json()
        return response.json()


# ==================== 财务相关工具 ====================

@mcp.tool()
@secure_api_call
async def get_finance_dictionary() -> dict:
    """
    获取财务指标元数据字典。

    当用户询问"有哪些财务指标"、"能查什么数据"、"指标列表"、"财务科目"
    或"支持查询哪些数据"时调用此工具。

    返回内容：
    - metrics: 指标列表，每项包含：
        - standard_name: 标准字段名（用于查询）
        - display_name: 中文显示名
        - category: 指标分类（如"盈利能力"、"风险指标"）
        - unit: 计量单位
        - description: 含义说明
        - synonyms: 同义词/别名列表
    - dimensions: 支持的查询维度

    使用建议：
    1. 查询具体指标前，先调用此工具确认指标名称
    2. 根据用户输入的关键词，在 synonyms 中查找匹配项
    3. 找到匹配后，使用 standard_name 调用 query_financial_metrics

    此工具为只读查询，不接受任何参数。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/finance/dictionary",
            headers={"X-User-ID": user_id}
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
@secure_api_call
async def query_financial_metrics(
    metric: str,
    year: int = None,
    quarter: int = None,
    month: int = None,
    granularity: str = "yearly"
) -> dict:
    """
    查询财务指标数据。

    当用户询问具体财务指标数值时调用此工具，如"去年的净利润"、
    "一季度的不良率"、"资产负债情况"。

    参数说明：
    | 参数 | 类型 | 默认值 | 说明 |
    |------|------|--------|------|
    | metric | str | 必需 | 指标名，必须是字典中的 standard_name |
    | year | int | None | 年份（如 2025），不指定则返回最近数据 |
    | quarter | int | None | 季度（1-4），指定后按季度查询 |
    | month | int | None | 月份（1-12），指定后按月查询 |
    | granularity | str | "yearly" | 聚合粒度：yearly/quarterly/monthly |

    常用查询场景示例：
    ┌─────────────────────────────────────────────────────────────────┐
    │ 用户问题                        │ 参数设置                      │
    ├─────────────────────────────────────────────────────────────────┤
    │ "去年的净利润"                  │ metric="NET_PROFIT",           │
    │                                 │ year=2025                     │
    ├─────────────────────────────────────────────────────────────────┤
    │ "一季度的不良率"                 │ metric="NPL_RATIO",           │
    │                                 │ year=2025, quarter=1          │
    ├─────────────────────────────────────────────────────────────────┤
    │ "最近三年的净利息收入"           │ metric="NET_INTEREST_INCOME", │
    │                                 │ year 不指定, granularity=      │
    │                                 │ "yearly"                      │
    ├─────────────────────────────────────────────────────────────────┤
    │ "各季度的资产负债总额"           │ metric="TOTAL_ASSETS",        │
    │                                 │ granularity="quarterly"       │
    └─────────────────────────────────────────────────────────────────┘

    安全约束：
    - 此工具仅能查询当前用户所属机构的数据
    - 不接受任何机构标识参数，机构代码自动过滤
    - 只能查询字典中定义的指标

    如不确定指标名称，请先调用 get_finance_dictionary 工具获取字典。
    """
    user_id = current_user_id.get()

    params = {
        "metric": metric,
        "granularity": granularity
    }
    if year:
        params["year"] = year
    if quarter:
        params["quarter"] = quarter
    if month:
        params["month"] = month

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/finance/query",
            params=params,
            headers={"X-User-ID": user_id}
        )
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