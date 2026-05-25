"""
MCP 协议透传代理

本地代理作为 MCP Server 实现：
- 接收 Claude Code 的 MCP 请求 (Stdio)
- 使用 Server 实例处理 MCP 协议握手
- 在每个请求中自动注入加密 Token
- 通过 HTTPS 转发到远端 MCP 服务
- 返回远端服务的响应

关键特性：
- Tools 定义在远端服务，本地代理通过 HTTP 获取
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

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr  # 日志输出到 stderr，不影响 stdio 通信
)
logger = logging.getLogger(__name__)


def get_config() -> dict:
    """
    获取配置

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


# ==================== 远端通信 ====================

async def fetch_tools_from_remote(ctx: dict) -> list[Tool]:
    """
    从远端获取工具列表并转换为 Tool 对象

    Args:
        ctx: 配置上下文

    Returns:
        Tool 对象列表
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{ctx['remote_url']}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list"
                },
                headers={
                    "Authorization": f"Bearer {ctx['token']}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code != 200:
                logger.error(f"获取工具列表失败: HTTP {response.status_code}")
                return []

            data = response.json()
            if "error" in data:
                logger.error(f"远端返回错误: {data['error']}")
                return []

            tools_data = data.get("result", {}).get("tools", [])
            logger.info(f"从远端获取 {len(tools_data)} 个工具")

            # 转换为 Tool 对象
            tools = []
            for t in tools_data:
                try:
                    # 移除多余的字段，只保留 Tool 需要的字段
                    tool_dict = {
                        "name": t.get("name"),
                        "description": t.get("description"),
                        "inputSchema": t.get("inputSchema", {"type": "object", "properties": {}})
                    }
                    tools.append(Tool(**tool_dict))
                except Exception as e:
                    logger.warning(f"转换工具失败: {t.get('name')}, {e}")

            return tools

    except Exception as e:
        logger.error(f"获取工具列表异常: {e}")
        return []


async def call_tool_on_remote(name: str, arguments: dict, ctx: dict) -> str:
    """
    在远端调用工具

    Args:
        name: 工具名称
        arguments: 工具参数
        ctx: 配置上下文

    Returns:
        工具执行结果（字符串）
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ctx['remote_url']}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": name,
                        "arguments": arguments
                    }
                },
                headers={
                    "Authorization": f"Bearer {ctx['token']}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code != 200:
                return f"远端服务错误: HTTP {response.status_code}"

            data = response.json()

            if "error" in data:
                error_msg = data["error"].get("message", "未知错误")
                return f"工具执行失败: {error_msg}"

            # 提取结果
            result = data.get("result", {})
            content = result.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                # content 可能是字符串形式的 TextContent 对象
                text_content = content[0]
                if isinstance(text_content, dict):
                    return text_content.get("text", str(result))
                elif isinstance(text_content, str):
                    # 处理字符串形式的 TextContent
                    return text_content
                else:
                    return str(text_content)

            return str(result)

    except httpx.ConnectError as e:
        logger.error(f"无法连接远端服务: {e}")
        return "无法连接远端服务"
    except Exception as e:
        logger.error(f"调用工具异常: {e}")
        return f"调用失败: {str(e)}"


# ==================== MCP 服务器实现 ====================

async def run_server():
    """运行 MCP 服务器"""
    # 获取配置
    ctx = get_config()

    logger.info(f"MCP 代理启动，目标: {ctx['remote_url']}")

    # 预加载工具列表
    remote_tools = await fetch_tools_from_remote(ctx)
    logger.info(f"已加载 {len(remote_tools)} 个工具")

    # 创建 MCP Server 实例
    server = Server("finance-proxy")

    # 注册 list_tools 处理器
    @server.list_tools()
    async def list_tools():
        """返回远端工具列表"""
        # 每次调用时重新获取工具列表（支持动态更新）
        tools = await fetch_tools_from_remote(ctx)
        return tools

    # 注册 call_tool 处理器
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """代理工具调用"""
        logger.info(f"调用工具: {name}, 参数: {arguments}")
        result = await call_tool_on_remote(name, arguments, ctx)
        return [TextContent(type="text", text=result)]

    # 使用 stdio_server 创建传输层
    async with stdio_server() as (read_stream, write_stream):
        logger.info("MCP 服务器已启动，等待连接...")

        # 获取初始化选项
        init_options = server.create_initialization_options()

        # 运行服务器
        await server.run(read_stream, write_stream, init_options)


def main():
    """主入口"""
    import anyio
    try:
        anyio.run(run_server)
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()