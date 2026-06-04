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
- 使用 Refresh Token 自动获取 Access Token
- Access Token 过期时自动刷新

安全设计：
- 本地代理只知道 Refresh Token，不知道用户身份
- Access Token 15 分钟有效，自动刷新
- 用户身份由远端服务从 Token 解密获取
"""

import os
import sys
import json
import logging
import httpx
from datetime import datetime, timezone, timedelta

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


# ==================== Token 刷新管理 ====================

class TokenRefreshManager:
    """
    管理 Refresh Token，自动获取 Access Token

    流程：
    1. 从环境变量读取 MCP_REFRESH_TOKEN
    2. 调用远端 /auth/refresh 获取 Access Token
    3. Access Token 过期时自动刷新
    """

    def __init__(self, remote_url: str):
        """
        初始化 Token 管理器

        Args:
            remote_url: 远端 MCP 服务地址

        Raises:
            ValueError: 未配置 Refresh Token
        """
        self.remote_url = remote_url
        self.refresh_token = os.environ.get("MCP_REFRESH_TOKEN")
        self.access_token = None
        self.access_token_expires_at = None

        # 兼容旧配置：如果设置了 MCP_AUTH_TOKEN，使用它
        self.legacy_token = os.environ.get("MCP_AUTH_TOKEN")

        if not self.refresh_token and not self.legacy_token:
            raise ValueError(
                "未配置认证令牌，请设置环境变量 MCP_REFRESH_TOKEN 或 MCP_AUTH_TOKEN"
            )

        if self.refresh_token:
            logger.info("使用 Refresh Token 模式（自动刷新）")
        else:
            logger.info("使用传统 Token 模式（无自动刷新）")

    async def get_valid_access_token(self) -> str:
        """
        获取有效的 Access Token

        如果使用传统 Token 模式，直接返回 MCP_AUTH_TOKEN。
        如果使用 Refresh Token 模式，检查 Access Token 是否有效，必要时刷新。

        Returns:
            有效的 Access Token

        Raises:
            Exception: 获取或刷新 Token 失败
        """
        # 传统模式：直接返回 MCP_AUTH_TOKEN
        if self.legacy_token and not self.refresh_token:
            return self.legacy_token

        # Refresh Token 模式
        now = datetime.now(timezone.utc)

        # 检查缓存的 Access Token 是否有效（预留 1 分钟）
        if self.access_token and self.access_token_expires_at:
            if now < self.access_token_expires_at - timedelta(minutes=1):
                return self.access_token

        # 需要刷新
        logger.info("Access Token 即将过期，正在刷新...")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.remote_url}/auth/refresh",
                    json={"refresh_token": self.refresh_token},
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code != 200:
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    error_msg = error_data.get("error", f"HTTP {response.status_code}")
                    logger.error(f"刷新 Token 失败: {error_msg}")
                    raise Exception(f"刷新 Token 失败: {error_msg}")

                data = response.json()
                self.access_token = data.get("access_token")
                expires_in = data.get("expires_in", 900)  # 默认 15 分钟

                self.access_token_expires_at = now + timedelta(seconds=expires_in)
                logger.info(f"Access Token 刷新成功，有效期 {expires_in} 秒")

                return self.access_token

        except httpx.ConnectError as e:
            logger.error(f"无法连接远端服务: {e}")
            raise Exception("无法连接远端服务")
        except json.JSONDecodeError as e:
            logger.error(f"解析响应失败: {e}")
            raise Exception("解析响应失败")
        except Exception as e:
            if "刷新 Token" in str(e) or "无法连接" in str(e):
                raise
            logger.error(f"刷新 Token 异常: {e}")
            raise Exception(f"刷新 Token 异常: {str(e)}")


# ==================== 远端通信 ====================

async def fetch_tools_from_remote(token_manager: TokenRefreshManager) -> list[Tool]:
    """
    从远端获取工具列表并转换为 Tool 对象

    Args:
        token_manager: Token 管理器

    Returns:
        Tool 对象列表
    """
    try:
        # 获取有效 Access Token
        logger.info("[fetch_tools] 开始获取 Access Token...")
        access_token = await token_manager.get_valid_access_token()
        logger.info(f"[fetch_tools] Access Token 获取成功，长度: {len(access_token) if access_token else 0}")

        request_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }
        logger.info(f"[fetch_tools] 发送请求到: {token_manager.remote_url}/mcp")
        logger.info(f"[fetch_tools] 请求内容: {json.dumps(request_payload, ensure_ascii=False)}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{token_manager.remote_url}/mcp",
                json=request_payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
            )

            logger.info(f"[fetch_tools] 响应状态码: {response.status_code}")
            logger.info(f"[fetch_tools] 响应 Headers: {dict(response.headers)}")

            # 记录原始响应内容（截断长内容）
            raw_text = response.text
            if len(raw_text) > 500:
                logger.info(f"[fetch_tools] 响应内容（前500字符）: {raw_text[:500]}...")
            else:
                logger.info(f"[fetch_tools] 响应内容: {raw_text}")

            if response.status_code != 200:
                logger.error(f"[fetch_tools] 获取工具列表失败: HTTP {response.status_code}")
                return []

            data = response.json()
            logger.info(f"[fetch_tools] 解析 JSON 成功，keys: {list(data.keys())}")

            if "error" in data:
                error_info = data["error"]
                logger.error(f"[fetch_tools] 远端返回错误: {error_info}")
                logger.error(f"[fetch_tools] 错误类型: {type(error_info)}, 错误内容: {json.dumps(error_info, ensure_ascii=False)}")
                return []

            result = data.get("result", {})
            logger.info(f"[fetch_tools] result keys: {list(result.keys()) if isinstance(result, dict) else '非字典类型'}")

            tools_data = result.get("tools", [])
            logger.info(f"[fetch_tools] 从远端获取 {len(tools_data)} 个工具")

            if len(tools_data) == 0:
                logger.warning("[fetch_tools] 工具列表为空！检查远端服务是否正确注册了工具")
                logger.warning(f"[fetch_tools] 完整 result 内容: {json.dumps(result, ensure_ascii=False)}")

            # 转换为 Tool 对象
            tools = []
            for t in tools_data:
                try:
                    # 记录每个工具的原始数据
                    logger.info(f"[fetch_tools] 处理工具: {t.get('name')}")
                    logger.info(f"[fetch_tools] 工具原始数据 keys: {list(t.keys())}")

                    # 移除多余的字段，只保留 Tool 需要的字段
                    tool_dict = {
                        "name": t.get("name"),
                        "description": t.get("description"),
                        "inputSchema": t.get("inputSchema", {"type": "object", "properties": {}})
                    }
                    logger.info(f"[fetch_tools] 转换后的工具数据: {json.dumps(tool_dict, ensure_ascii=False, indent=2)}")

                    tool = Tool(**tool_dict)
                    tools.append(tool)
                    logger.info(f"[fetch_tools] 工具 {t.get('name')} 转换成功")
                except Exception as e:
                    logger.warning(f"[fetch_tools] 转换工具失败: {t.get('name')}, 错误: {e}")
                    logger.warning(f"[fetch_tools] 失败工具的原始数据: {json.dumps(t, ensure_ascii=False)}")

            logger.info(f"[fetch_tools] 最终成功转换 {len(tools)} 个工具")
            return tools

    except httpx.ConnectError as e:
        logger.error(f"[fetch_tools] 无法连接远端服务: {e}")
        logger.error(f"[fetch_tools] 目标地址: {token_manager.remote_url}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"[fetch_tools] 解析响应失败: {e}")
        logger.error(f"[fetch_tools] 响应内容可能不是有效 JSON")
        return []
    except Exception as e:
        logger.error(f"[fetch_tools] 获取工具列表异常: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[fetch_tools] 异常堆栈:\n{traceback.format_exc()}")
        return []


async def call_tool_on_remote(name: str, arguments: dict, token_manager: TokenRefreshManager) -> str:
    """
    在远端调用工具

    Args:
        name: 工具名称
        arguments: 工具参数
        token_manager: Token 管理器

    Returns:
        工具执行结果（字符串）
    """
    try:
        # 获取有效 Access Token
        access_token = await token_manager.get_valid_access_token()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{token_manager.remote_url}/mcp",
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
                    "Authorization": f"Bearer {access_token}",
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
    remote_url = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")

    # 创建 Token 管理器
    token_manager = TokenRefreshManager(remote_url)

    logger.info(f"[run_server] MCP 代理启动，目标: {remote_url}")

    # 预加载工具列表
    logger.info("[run_server] ========== 预加载工具列表 ==========")
    remote_tools = await fetch_tools_from_remote(token_manager)
    logger.info(f"[run_server] 已加载 {len(remote_tools)} 个工具")
    if len(remote_tools) == 0:
        logger.error("[run_server] ⚠️ 预加载工具列表为空！请检查远端服务状态")
        logger.error("[run_server] 可能原因:")
        logger.error("[run_server]   1. 远端服务未启动")
        logger.error("[run_server]   2. 远端服务未注册任何工具")
        logger.error("[run_server]   3. Token 无效或已过期")
        logger.error("[run_server]   4. 网络连接问题")
    else:
        for tool in remote_tools:
            logger.info(f"[run_server] 预加载工具: {tool.name}")
    logger.info("[run_server] ========== 预加载完成 ==========")

    # 创建 MCP Server 实例
    server = Server("finance-proxy")

    # 注册 list_tools 处理器
    @server.list_tools()
    async def list_tools():
        """返回远端工具列表"""
        logger.info("[list_tools] ========== list_tools 被调用 ==========")
        logger.info("[list_tools] 开始从远端获取工具列表...")
        # 每次调用时重新获取工具列表（支持动态更新）
        tools = await fetch_tools_from_remote(token_manager)
        logger.info(f"[list_tools] 获取到 {len(tools)} 个工具")
        if len(tools) == 0:
            logger.warning("[list_tools] 返回空列表！这可能导致 agent 无法找到任何工具")
        else:
            for tool in tools:
                logger.info(f"[list_tools] 返回工具: {tool.name}")
        logger.info("[list_tools] ========== list_tools 返回完成 ==========")
        return tools

    # 注册 call_tool 处理器
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """代理工具调用"""
        logger.info(f"调用工具: {name}, 参数: {arguments}")
        result = await call_tool_on_remote(name, arguments, token_manager)
        return [TextContent(type="text", text=result)]

    # 使用 stdio_server 创建传输层
    async with stdio_server() as (read_stream, write_stream):
        logger.info("[run_server] ========== MCP 服务器启动 ==========")
        logger.info("[run_server] stdio 传输层已创建")
        logger.info("[run_server] 等待 Claude Code 连接...")

        # 获取初始化选项
        init_options = server.create_initialization_options()
        logger.info(f"[run_server] 初始化选项: {init_options}")

        # 运行服务器
        logger.info("[run_server] 开始运行 MCP 协议循环...")
        await server.run(read_stream, write_stream, init_options)
        logger.info("[run_server] MCP 服务器已停止")


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
