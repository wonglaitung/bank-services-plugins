"""配置"""

import os

# 后台 API 地址
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8000")

# 预期的 Token
EXPECTED_TOKEN = os.environ.get("EXPECTED_TOKEN", "prototype-token")

# 服务端口
PORT = int(os.environ.get("PORT", "8001"))
