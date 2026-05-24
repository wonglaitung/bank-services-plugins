"""
MCP 协议透传代理

本地代理作为 MCP JSON-RPC 协议的透明转发层：
- 接收 Claude Code 的 MCP 请求 (Stdio)
- 在每个请求中自动注入加密 Token
- 通过 HTTPS 转发到远端 MCP 服务
- 返回远端服务的响应

关键特性：
- Tools 定义在远端服务，本地代理不定义任何工具
- 用户身份封装在加密 Token 中，本地代理无法查看
- Token 从环境变量读取，模型无法修改

安全设计：
- 本地代理只知道 Token，不知道用户身份
- 用户身份由远端服务从 Token 解密获取
- 有效期由 Token 内部控制，无法绕过
"""

import os
import sys
import json
import logging
import httpx
import anyio

from mcp.shared.message import SessionMessage
import mcp.types as types

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr  # 日志输出到 stderr，不影响 stdio 通信
)
logger = logging.getLogger(__name__)


def get_user_context() -> dict:
    """
    获取用户上下文

    只读取 Token，不解密。用户身份由远端服务解密获取。

    Returns:
        包含 token 和 remote_url 的字典

    Raises:
        ValueError: 配置缺失
    """
    token = os.environ.get("MCP_AUTH_TOKEN")
    remote_url = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")

    if not token:
        raise ValueError("未配置认证令牌，请设置环境变量 MCP_AUTH_TOKEN")

    return {
        "token": token,
        "remote_url": remote_url
    }


async def forward_request(
    request: types.JSONRPCMessage,
    ctx: dict
) -> types.JSONRPCMessage:
    """
    转发 MCP 请求到远端服务

    Args:
        request: MCP JSON-RPC 请求
        ctx: 用户上下文

    Returns:
        远端服务的响应
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ctx['remote_url']}/mcp",
            json=request.root.model_dump(by_alias=True, exclude_none=True),
            headers={
                "Authorization": f"Bearer {ctx['token']}",
                "Content-Type": "application/json"
            }
        )

        if response.status_code != 200:
            logger.error(f"远端服务错误: status={response.status_code}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"远端服务错误: {response.status_code}"},
                "id": request.root.id
            }
            return types.JSONRPCMessage.model_validate(error_response)

        return types.JSONRPCMessage.model_validate(response.json())


async def run_proxy():
    """运行代理主循环"""
    # 获取配置
    ctx = get_user_context()

    logger.info(f"MCP 代理启动，目标: {ctx['remote_url']}")

    # 使用 anyio 进行异步 I/O
    async with anyio.create_task_group() as tg:
        async with await anyio.open_file(sys.stdin.fileno(), "r") as stdin:
            async with await anyio.open_file(sys.stdout.fileno(), "w") as stdout:
                async for line in stdin:
                    try:
                        # 解析 JSON-RPC 消息
                        message = types.JSONRPCMessage.model_validate_json(line)

                        # 记录请求日志
                        method = getattr(message.root, "method", "unknown")
                        request_id = getattr(message.root, "id", "?")
                        logger.info(f"转发 MCP 请求: method={method}, id={request_id}")

                        # 转发请求
                        response = await forward_request(message, ctx)

                        # 发送响应
                        json_str = response.root.model_dump_json(by_alias=True, exclude_none=True)
                        await stdout.write(json_str + "\n")
                        await stdout.flush()

                    except httpx.ConnectError as e:
                        logger.error(f"无法连接远端服务: {e}")
                        error_response = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32603, "message": "无法连接远端服务"},
                            "id": None
                        }
                        await stdout.write(json.dumps(error_response) + "\n")
                        await stdout.flush()

                    except Exception as e:
                        logger.error(f"处理请求失败: {e}")
                        error_response = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32603, "message": f"内部错误: {str(e)}"},
                            "id": None
                        }
                        await stdout.write(json.dumps(error_response) + "\n")
                        await stdout.flush()


def main():
    """主入口"""
    try:
        anyio.run(run_proxy)
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
