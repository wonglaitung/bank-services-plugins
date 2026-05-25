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
│                              │ MCP_AUTH_TOKEN       │ 获取 user_id      │
│                              │                      │ 验证有效期        │
└─────────────────────────────────────────────────────────────────────────┘
                                                       │
                                                       ▼
                                                 后台 API (数据查询)
```

**关键特性**：
- 用户身份封装在**加密 Token** 中，本地代理无法查看
- Token 包含 `user_id` 和 `expires_at`，由远端服务解密验证
- 有效期由 Token 内部控制，无法绕过

## 快速开始

### 1. 生成密钥和 Token

```bash
cd prototype

# 生成密钥（首次使用）
python tools/generate_token.py --generate-key

# 生成 Token（有效期 8 小时）
python tools/generate_token.py --user-id 000000001 --expires 8
# 输出: MCP_AUTH_TOKEN=xxx
```

### 2. 启动服务

```bash
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
        "MCP_AUTH_TOKEN": "<上一步生成的 Token>"
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
| `MCP_AUTH_TOKEN` | 加密认证令牌（使用 `generate_token.py` 生成） | ✅ |

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

# 生成 Token
python tools/generate_token.py --user-id 000000001 --expires 8
# --expires 单位：小时，默认 8 小时
```

**密钥文件位置**：`tools/.token_key`

## 验证安全机制

| 验证项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| Token 解密 | 使用正确密钥启动服务 | 返回用户信息 |
| Token 过期 | 等待 Token 过期后调用 | 返回 401 "Token 已过期" |
| Token 无效 | 使用错误的 Token | 返回 401 "Token 格式错误" |
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
    └── .token_key           # 密钥文件
```

## 详细文档

参见：`docs/mcp_prototype_sidecar.md`

## 实现说明

### 本地代理 (local_proxy)

本地代理作为真正的 MCP Server 实现，使用 `mcp.server.Server` 类：
- 通过 stdio 与 Claude Code 通信
- 从远端服务动态获取工具列表
- 在每次请求中自动注入加密 Token
- 支持 MCP 协议握手和初始化流程

### 远端 MCP 服务 (mcp_remote)

远端服务提供真正的 MCP 服务功能：
- 定义所有 Tools（`get_my_info`、`get_my_department`、`get_my_balance`、`check_my_permission`）
- 从加密 Token 解密获取用户编号
- 正确处理 MCP notification 消息（不返回响应）
- 对未知方法返回标准 JSON-RPC 错误

### 安全机制

- **Token 封装**：用户身份封装在加密 Token 中，本地代理无法查看
- **有效期验证**：Token 包含 `expires_at`，由远端服务验证
- **IDOR 防护**：所有工具不接受 `user_id` 参数，身份从 Token 自动获取
- **审计日志**：所有请求记录用户编号和操作
