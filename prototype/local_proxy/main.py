"""
MCP 协议透传代理

本地代理作为 MCP JSON-RPC 协议的透明转发层：
- 接收 Claude Code 的 MCP 请求 (Stdio)
- 在每个请求中自动注入 Token 和用户编号
- 通过 HTTPS 转发到远端 MCP 服务
- 返回远端服务的响应

关键特性：
- Tools 定义在远端服务，本地代理不定义任何工具
- 添加/修改工具只需改远端服务，无需改本地代理
- 用户编号和 Token 从环境变量读取，模型无法修改
"""

import os
import sys
import json
import logging
import httpx
from mcp.server.fastmcp import FastMCP

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr  # 日志输出到 stderr，不影响 stdio 通信
)
logger = logging.getLogger(__name__)


def get_user_context() -> dict:
    """
    从环境变量获取用户上下文

    Returns:
        包含 user_id 和 token 的字典

    Raises:
        ValueError: 配置缺失
    """
    user_id = os.environ.get("MCP_USER_ID")
    token = os.environ.get("MCP_AUTH_TOKEN")
    remote_url = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")

    if not user_id:
        raise ValueError("未配置用户编号，请设置环境变量 MCP_USER_ID")
    if not token:
        raise ValueError("未配置认证令牌，请设置环境变量 MCP_AUTH_TOKEN")

    return {
        "user_id": user_id,
        "token": token,
        "remote_url": remote_url
    }


def validate_user_context(ctx: dict):
    """验证用户上下文格式"""
    user_id = ctx["user_id"]
    if not user_id.isdigit() or len(user_id) != 9:
        raise ValueError(f"用户编号格式错误，必须为9位数字: {user_id}")

    logger.info(f"用户上下文已加载: user_id={user_id}")


# 创建代理（不定义任何工具，纯转发）
mcp = FastMCP("MCPProxy")


# 注册请求处理钩子
@mcp.hook("before_request")
async def inject_and_forward(request: dict) -> dict:
    """
    拦截 MCP 请求，注入认证信息后转发到远端服务

    Args:
        request: MCP JSON-RPC 请求

    Returns:
        远端服务的响应
    """
    try:
        # 获取用户上下文
        ctx = get_user_context()

        # 记录请求日志
        method = request.get("method", "unknown")
        request_id = request.get("id", "?")
        logger.info(f"转发 MCP 请求: method={method}, id={request_id}")

        # 转发请求到远端，注入认证 Header
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ctx['remote_url']}/mcp",
                json=request,  # 透传原始 MCP 请求
                headers={
                    "Authorization": f"Bearer {ctx['token']}",
                    "X-User-ID": ctx["user_id"],
                    "Content-Type": "application/json"
                }
            )

            # 检查响应状态
            if response.status_code != 200:
                logger.error(f"远端服务错误: status={response.status_code}")
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": f"远端服务错误: {response.status_code}"},
                    "id": request_id
                }

            return response.json()

    except httpx.ConnectError as e:
        logger.error(f"无法连接远端服务: {e}")
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": "无法连接远端服务"},
            "id": request.get("id")
        }
    except Exception as e:
        logger.error(f"转发请求失败: {e}")
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"内部错误: {str(e)}"},
            "id": request.get("id")
        }


def main():
    """主入口"""
    try:
        # 验证配置
        ctx = get_user_context()
        validate_user_context(ctx)

        logger.info(f"MCP 代理启动，目标: {ctx['remote_url']}")

        # 使用 Stdio 协议运行
        mcp.run(transport="stdio")

    except ValueError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()