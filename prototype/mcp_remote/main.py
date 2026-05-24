"""
远端 MCP 服务

提供真正的 MCP 服务，定义所有 Tools。
从 HTTP Header 获取用户编号，用于数据查询。

关键安全原则：
- Tools 不接受 user_id 参数
- 用户编号从 Header 获取，由本地代理注入
- 所有数据查询强制使用当前用户编号
"""

import os
import logging
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from mcp.server.fastmcp import FastMCP

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
EXPECTED_TOKEN = os.environ.get("EXPECTED_TOKEN", "prototype-token")


# ==================== 认证中间件 ====================

async def verify_request(request: Request) -> str:
    """
    验证请求并返回用户编号

    从 HTTP Header 提取 Token 和用户编号，验证合法性。

    Returns:
        验证通过的用户编号

    Raises:
        HTTPException: 认证失败
    """
    # 提取 Header
    auth_header = request.headers.get("Authorization", "")
    user_id = request.headers.get("X-User-ID", "")

    # 验证 Token
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
    if token != EXPECTED_TOKEN:
        logger.warning(f"Token 验证失败: {token[:10]}...")
        raise HTTPException(401, "Token 无效")

    # 验证用户编号格式（必须为9位数字）
    if not user_id or not user_id.isdigit() or len(user_id) != 9:
        logger.warning(f"用户编号格式错误: {user_id}")
        raise HTTPException(400, "用户编号必须为9位数字")

    logger.info(f"用户认证成功: {user_id}")
    return user_id


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

    1. 验证认证信息
    2. 注入用户上下文
    3. 根据 method 调用对应的 MCP 方法
    """
    try:
        # 验证认证
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

        else:
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
