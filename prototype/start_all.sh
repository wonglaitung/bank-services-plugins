#!/bin/bash

# MCP 安全认证原型启动脚本

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "MCP 安全认证原型 - Sidecar 模式"
echo "=========================================="

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3，请先安装 Python 3"
    exit 1
fi

# 安装依赖
echo ""
echo "[1/3] 安装依赖..."

echo "  - 安装后台 API 依赖..."
pip install -q -r "$SCRIPT_DIR/backend_api/requirements.txt"

echo "  - 安装远端 MCP 服务依赖..."
pip install -q -r "$SCRIPT_DIR/mcp_remote/requirements.txt"

echo "  - 安装本地代理依赖..."
pip install -q -r "$SCRIPT_DIR/local_proxy/requirements.txt"

# 启动服务
echo ""
echo "[2/3] 启动服务..."

# 停止可能存在的旧进程
pkill -f "python.*backend_api/main.py" 2>/dev/null || true
pkill -f "python.*mcp_remote/main.py" 2>/dev/null || true

sleep 1

# 启动后台 API
echo "  - 启动后台 API (端口 8000)..."
cd "$SCRIPT_DIR/backend_api"
nohup python main.py > /tmp/backend_api.log 2>&1 &
BACKEND_PID=$!
echo "    PID: $BACKEND_PID"

# 等待后台 API 启动
sleep 2

# 检查后台 API 是否启动成功
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "错误: 后台 API 启动失败，请检查日志: /tmp/backend_api.log"
    exit 1
fi

# 启动远端 MCP 服务
echo "  - 启动远端 MCP 服务 (端口 8001)..."
cd "$SCRIPT_DIR/mcp_remote"

# 读取密钥文件（如果存在）
TOKEN_KEY_ENV=""
KEY_FILE="$SCRIPT_DIR/tools/.token_key"
if [ -f "$KEY_FILE" ]; then
    TOKEN_KEY_B64=$(base64 -w 0 "$KEY_FILE")
    TOKEN_KEY_ENV="TOKEN_KEY=$TOKEN_KEY_B64"
    echo "    使用密钥文件: $KEY_FILE"
else
    echo "    警告: 未找到密钥文件，使用测试密钥"
    echo "    请先运行: python $SCRIPT_DIR/tools/generate_token.py --generate-key"
fi

# 启动服务（带或不带密钥）
if [ -n "$TOKEN_KEY_ENV" ]; then
    nohup env "$TOKEN_KEY_ENV" python main.py > /tmp/mcp_remote.log 2>&1 &
else
    nohup python main.py > /tmp/mcp_remote.log 2>&1 &
fi
REMOTE_PID=$!
echo "    PID: $REMOTE_PID"

# 等待远端服务启动
sleep 2

# 检查远端服务是否启动成功
if ! curl -s http://localhost:8001/health > /dev/null 2>&1; then
    echo "错误: 远端 MCP 服务启动失败，请检查日志: /tmp/mcp_remote.log"
    exit 1
fi

# 保存 PID
echo "$BACKEND_PID" > /tmp/backend_api.pid
echo "$REMOTE_PID" > /tmp/mcp_remote.pid

echo ""
echo "[3/3] 服务已启动:"
echo ""
echo "  后台 API:      http://localhost:8000"
echo "  远端 MCP 服务: http://localhost:8001"
echo ""
echo "  日志文件:"
echo "    /tmp/backend_api.log"
echo "    /tmp/mcp_remote.log"
echo ""
echo "=========================================="
echo ""
echo "下一步: 在 Claude Code 配置中添加本地代理:"
echo ""
echo '{'
echo '  "mcpServers": {'
echo '    "finance-proxy": {'
echo '      "command": "python",'
echo '      "args": ["'"$SCRIPT_DIR"'/local_proxy/main.py"],'
echo '      "env": {'
echo '        "REMOTE_MCP_URL": "http://localhost:8001",'
echo '        "MCP_AUTH_TOKEN": "<使用 tools/generate_token.py 生成>"'
echo '      }'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "生成 Token 命令:"
echo "  python $SCRIPT_DIR/tools/generate_token.py --user-id 000000001 --expires 8"
echo ""
echo "=========================================="
