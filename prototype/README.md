# MCP 安全认证原型 - Sidecar 模式

本原型用于验证 MCP 安全认证方案的核心流程，采用侧车（Sidecar）模式。

## 架构概览

```
Claude Code ──Stdio──▶ 本地代理 ──HTTPS──▶ 远端 MCP 服务 ──HTTP──▶ 后台 API
                           │                      │
                           │  注入认证 Header       │  定义 Tools
                           │  • Authorization      │  验证认证
                           │  • X-User-ID          │  调用后台 API
```

## 快速开始

### 1. 安装依赖

```bash
# 后台 API
pip install -r backend_api/requirements.txt

# 远端 MCP 服务
pip install -r mcp_remote/requirements.txt

# 本地代理
pip install -r local_proxy/requirements.txt
```

### 2. 启动服务

```bash
# 方式一：使用启动脚本
./start_all.sh

# 方式二：手动启动
# 启动后台 API (端口 8000)
python backend_api/main.py &

# 启动远端 MCP 服务 (端口 8001)
python mcp_remote/main.py &
```

### 3. 配置 Claude Code

在 Claude Code 的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "finance-proxy": {
      "command": "python",
      "args": ["/absolute/path/to/prototype/local_proxy/main.py"],
      "env": {
        "REMOTE_MCP_URL": "http://localhost:8001",
        "MCP_USER_ID": "000000001",
        "MCP_AUTH_TOKEN": "prototype-token"
      }
    }
  }
}
```

### 4. 测试调用

在 Claude Code 中输入：

```
请帮我查询我的用户信息
```

应返回：

```json
{
  "user_id": "000000001",
  "name": "张三",
  "department": "财务部",
  "role": "viewer",
  "balance": 125000.00
}
```

## 可用工具

| 工具名 | 说明 |
|--------|------|
| `get_my_info` | 获取当前用户的完整信息 |
| `get_my_department` | 获取当前用户所在部门 |
| `get_my_balance` | 获取当前用户账户余额 |
| `check_my_permission` | 检查当前用户权限 |

## 模拟用户数据

| 用户编号 | 姓名 | 部门 | 角色 | 余额 |
|----------|------|------|------|------|
| 000000001 | 张三 | 财务部 | viewer | 125,000 |
| 000000002 | 李四 | 财务部 | admin | 250,000 |
| 000000003 | 王五 | 技术部 | viewer | 88,000 |
| 000000004 | 赵六 | 人事部 | viewer | 150,000 |
| 000000005 | 钱七 | 技术部 | admin | 320,000 |

## 环境变量说明

### 本地代理

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `REMOTE_MCP_URL` | 远端 MCP 服务地址 | ✅ |
| `MCP_USER_ID` | 用户编号（9位数字） | ✅ |
| `MCP_AUTH_TOKEN` | 认证令牌 | ✅ |

### 远端 MCP 服务

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BACKEND_API_URL` | 后台 API 地址 | `http://localhost:8000` |
| `EXPECTED_TOKEN` | 预期的认证令牌 | `prototype-token` |
| `PORT` | 服务端口 | `8001` |

## 验证安全机制

### 测试 Token 验证

修改配置中的 `MCP_AUTH_TOKEN` 为错误值，应返回 401 错误。

### 测试用户编号格式

修改 `MCP_USER_ID` 为非9位数字，本地代理应启动失败。

### 测试添加工具

在远端服务中添加新工具后，重启远端服务，Claude Code 应自动发现新工具，无需修改本地代理。

## 目录结构

```
prototype/
├── README.md                # 本文件
├── start_all.sh             # 启动脚本
├── backend_api/             # 模拟后台 API
│   ├── main.py
│   ├── users.json
│   └── requirements.txt
├── mcp_remote/              # 远端 MCP 服务
│   ├── main.py
│   ├── config.py
│   └── requirements.txt
└── local_proxy/             # 本地代理
    ├── main.py
    ├── config.py
    └── requirements.txt
```

## 详细文档

参见：`docs/mcp_prototype_sidecar.md`
