# MCP 安全认证原型 - Sidecar 模式

本原型用于验证 MCP 安全认证方案的核心流程，采用侧车（Sidecar）模式。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           用户本地机器                                   │
│                                                                         │
│  Claude Code ──Stdio──▶ 本地代理 ──HTTPS──▶ 远端 MCP 服务               │
│                              │                      │                   │
│                              │ 读取环境变量          │ 解密 Token        │
│                              │ MCP_REFRESH_TOKEN    │ 获取 user_id      │
│                              │                      │ 验证有效期        │
│                              │ 自动刷新             │                   │
│                              │ Access Token         │                   │
└─────────────────────────────────────────────────────────────────────────┘
                                                       │
                                                       ▼
                                                 后台 API (数据查询)
```

**关键特性**：
- 用户身份封装在**加密 Token** 中，本地代理无法查看
- Token 包含 `user_id` 和 `expires_at`，由远端服务解密验证
- 使用 **Access Token + Refresh Token** 机制
- Access Token 15 分钟有效，过期自动刷新
- Refresh Token 7 天有效，支持吊销

## 快速开始

### 1. 生成密钥和 Token

```bash
cd prototype

# 生成密钥（首次使用）
python tools/generate_token.py --generate-key

# 查看密钥（配置到远端服务环境变量）
python tools/generate_token.py --show-key

# 生成 Token 对（Refresh Token 有效 7 天）
python tools/generate_token.py --user-id 000000001 --refresh-expires 7
# 输出: MCP_REFRESH_TOKEN=xxx
```

### 2. 启动服务

```bash
# 配置密钥环境变量
export TOKEN_KEY="<上一步 show-key 输出的密钥>"

# 方式一：使用启动脚本（推荐）
./start_all.sh

# 方式二：手动启动
python backend_api/main.py &      # 端口 8000
python mcp_remote/main.py &       # 端口 8001
```

### 3. 配置 Claude Code

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "finance-proxy": {
      "command": "python",
      "args": ["/absolute/path/to/prototype/local_proxy/main.py"],
      "env": {
        "REMOTE_MCP_URL": "http://localhost:8001",
        "MCP_REFRESH_TOKEN": "<上一步生成的 Refresh Token>"
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
  "role": "viewer"
}
```

## Token 机制

### Access Token

- **有效期**：15 分钟
- **用途**：调用 MCP API
- **自动刷新**：本地代理检测过期后自动调用 `/auth/refresh`
- **无需吊销**：有效期短，自动失效

### Refresh Token

- **有效期**：可配置（默认 7 天）
- **用途**：获取新 Access Token
- **存储位置**：用户 `.mcp.json` 配置文件
- **支持吊销**：管理员可调用 `/auth/revoke` 吊销

## 可用工具

| 工具名 | 说明 |
|--------|------|
| `get_my_info` | 获取当前用户的完整信息 |
| `get_my_department` | 获取当前用户所在部门 |
| `get_my_balance` | 获取当前用户账户余额 |
| `check_my_permission` | 检查当前用户权限 |

**安全特性**：所有工具不接受 `user_id` 参数，用户身份从 Token 自动获取。

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
| `MCP_REFRESH_TOKEN` | Refresh Token（推荐） | ✅ |
| `MCP_AUTH_TOKEN` | 传统 Token（兼容旧配置） | ⚠️ |

### 远端 MCP 服务

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BACKEND_API_URL` | 后台 API 地址 | `http://localhost:8000` |
| `TOKEN_KEY` | AES-256 密钥（Base64） | 测试密钥 |

## Token 工具

`tools/generate_token.py` 提供 Token 生成功能：

```bash
# 生成密钥
python tools/generate_token.py --generate-key

# 查看密钥
python tools/generate_token.py --show-key

# 生成 Token 对
python tools/generate_token.py --user-id 000000001 --refresh-expires 7
# --refresh-expires 单位：天，默认 7 天
```

**密钥文件位置**：`tools/.token_key`
**Token 清单位置**：`tools/token_records.json`
**吊销黑名单位置**：`tools/revoked_tokens.json`

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/auth/refresh` | POST | 使用 Refresh Token 获取新 Access Token |
| `/auth/revoke` | POST | 吊销 Refresh Token |
| `/mcp` | POST | MCP JSON-RPC 请求 |
| `/health` | GET | 健康检查 |

### 吊销 Token

```bash
# 查看 Token 清单找到 jti
cat prototype/tools/token_records.json

# 调用吊销接口
curl -X POST http://localhost:8001/auth/revoke \
  -H "Content-Type: application/json" \
  -d '{"jti": "abc123"}'
```

## 验证安全机制

| 验证项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| Token 解密 | 使用正确密钥启动服务 | 返回用户信息 |
| Token 过期 | 等待 Token 过期后调用 | 自动刷新成功 |
| Token 无效 | 使用错误的 Token | 返回 401 "Token 格式错误" |
| Token 吊销 | 吊销后使用 Refresh Token | 返回 401 "Token 已被吊销" |
| IDOR 防护 | 请求他人数据 | 返回当前用户数据 |

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
│   └── requirements.txt
├── local_proxy/             # 本地代理
│   ├── main.py
│   └── requirements.txt
└── tools/                   # 工具
    ├── generate_token.py    # Token 生成工具
    ├── .token_key           # 密钥文件
    ├── token_records.json   # Token 清单
    └── revoked_tokens.json  # 吊销黑名单
```

## 安全改进对比

| 对比项 | 原方案 | 新方案 |
|--------|--------|--------|
| Token 有效期 | 8 小时 | 15 分钟（Access）/ 7 天（Refresh） |
| 盗用风险窗口 | 8 小时 | 15 分钟 |
| Token 吊销 | 不支持 | ✅ 支持（Refresh Token 黑名单） |
| 自动刷新 | 不支持 | ✅ 支持 |
| Token 清单 | 无 | ✅ 服务器记录 |

## 详细文档

参见：`docs/mcp_prototype_sidecar.md`

## 实现说明

### 本地代理 (local_proxy)

本地代理作为真正的 MCP Server 实现，使用 `mcp.server.Server` 类：
- 通过 stdio 与 Claude Code 通信
- 从远端服务动态获取工具列表
- 自动刷新 Access Token
- 支持 MCP 协议握手和初始化流程

### 远端 MCP 服务 (mcp_remote)

远端服务提供真正的 MCP 服务功能：
- 定义所有 Tools（`get_my_info`、`get_my_department`、`get_my_balance`、`check_my_permission`）
- 从加密 Token 解密获取用户编号
- 提供 `/auth/refresh` 端点刷新 Token
- 提供 `/auth/revoke` 端点吊销 Token
- 正确处理 MCP notification 消息（不返回响应）

### 安全机制

- **Token 封装**：用户身份封装在加密 Token 中，本地代理无法查看
- **有效期验证**：Token 包含 `expires_at`，由远端服务验证
- **IDOR 防护**：所有工具不接受 `user_id` 参数，身份从 Token 自动获取
- **审计日志**：所有请求记录用户编号和操作