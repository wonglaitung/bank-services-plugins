"""配置"""

import os

# 远端 MCP 服务地址
REMOTE_MCP_URL = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")

# 用户编号（9位数字）
MCP_USER_ID = os.environ.get("MCP_USER_ID")

# 认证令牌
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN")