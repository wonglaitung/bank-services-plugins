# MCP 安全认证原型 - Sidecar 模式

基于 Sidecar 模式的 MCP 安全认证方案原型，实现用户身份封装、Token 自动刷新和行级数据隔离。

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

**核心特性**：
- 用户身份封装在加密 Token 中，本地代理无法查看
- Access Token 15 分钟有效，过期自动刷新
- Refresh Token 7 天有效，支持吊销
- IDOR 防护：工具不接受 user_id 参数，身份从 Token 自动获取

## 目录结构

```
prototype/
├── README.md                # 本文件
├── start_all.sh             # 启动脚本
├── backend_api/             # 模拟后台 API（业务逻辑、权限验证）
│   ├── main.py
│   ├── users.json
│   └── requirements.txt
├── mcp_remote/              # 远端 MCP 服务（Token 解密、工具定义）
│   ├── main.py
│   └── requirements.txt
├── local_proxy/             # 本地代理（MCP Server、Token 刷新）
│   ├── main.py
│   └── requirements.txt
└── tools/                   # 工具
    ├── generate_token.py    # Token 生成工具
    ├── .token_key           # 密钥文件
    ├── token_records.json   # Token 清单
    └── revoked_tokens.json  # 吊销黑名单
```

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

### 4. 验证调用

在 Claude Code 中输入：

```
请帮我查询我的用户信息
```

预期返回：

```json
{
  "user_id": "000000001",
  "name": "张三",
  "department": "财务部",
  "role": "viewer"
}
```

## 核心概念

### Token 机制

| Token 类型 | 有效期 | 用途 | 存储位置 | 吊销支持 |
|-----------|--------|------|----------|----------|
| Access Token | 15 分钟 | 调用 MCP API | 内存（自动管理） | 无需（自动失效） |
| Refresh Token | 7 天（可配置） | 获取新 Access Token | `.mcp.json` 配置文件 | ✅ 支持 |

**自动刷新流程**：
1. 本地代理检测 Access Token 过期
2. 使用 Refresh Token 调用 `/auth/refresh`
3. 获取新 Access Token，继续请求

### 安全边界

| 组件 | 职责 | 不负责 |
|------|------|--------|
| 本地代理 | Token 刷新、协议转发 | 用户身份解析、业务逻辑 |
| 远端 MCP | Token 解密、user_id 提取 | 权限验证、数据查询 |
| 后台 API | 权限验证、数据隔离、业务逻辑 | Token 处理 |

### 行级安全（RLS）

不同机构用户查询财务数据时，自动过滤为所属机构数据：

| 用户编号 | 机构代码 | 机构说明 |
|----------|----------|----------|
| 000000001 | BR001 | 某分行 |
| 000000002 | BR001 | 某分行 |
| 000000003 | BR002 | 另一分行 |
| 000000004 | BR001 | 某分行 |
| 000000005 | BR002 | 另一分行 |

## 可用工具

### 用户信息工具

| 工具名 | 说明 | 权限要求 |
|--------|------|----------|
| `get_my_info` | 获取当前用户完整信息 | - |
| `get_my_department` | 获取当前用户所在部门 | - |
| `get_my_balance` | 获取当前用户账户余额 | - |
| `check_my_permission` | 检查当前用户权限和角色 | - |
| `list_all_users` | 查询所有用户信息（不含金额） | admin |

### 财务数据工具

| 工具名 | 说明 |
|--------|------|
| `get_finance_dictionary` | 获取财务指标元数据字典（含同义词） |
| `query_financial_metrics` | 查询财务指标数据（支持年/季/月维度） |

**支持的财务指标**：

| 标准名称 | 显示名 | 分类 | 同义词 |
|----------|--------|------|--------|
| `NET_PROFIT` | 净利润 | 盈利能力 | 纯利润、税后利润 |
| `NET_INTEREST_INCOME` | 净利息收入 | 盈利能力 | 利息收入、息差收入 |
| `TOTAL_ASSETS` | 资产总额 | 规模指标 | 总资产、资产规模 |
| `TOTAL_LIABILITIES` | 负债总额 | 规模指标 | 总负债、负债规模 |
| `NPL_RATIO` | 不良贷款率 | 风险指标 | 不良率、NPL |
| `CAR_RATIO` | 资本充足率 | 风险指标 | CAR |
| `LOAN_BALANCE` | 贷款余额 | 业务指标 | 贷款总额、贷款规模 |
| `DEPOSIT_BALANCE` | 存款余额 | 业务指标 | 存款总额、存款规模 |

## 配置参考

### 环境变量

**本地代理**：

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `REMOTE_MCP_URL` | 远端 MCP 服务地址 | ✅ |
| `MCP_REFRESH_TOKEN` | Refresh Token | ✅ |

**远端 MCP 服务**：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BACKEND_API_URL` | 后台 API 地址 | `http://localhost:8000` |
| `TOKEN_KEY` | AES-256 密钥（Base64） | 测试密钥 |

### API 端点

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

## 安全验证清单

| 验证项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| Token 解密 | 使用正确密钥启动服务 | 返回用户信息 |
| Token 过期 | 等待 Access Token 过期后调用 | 自动刷新成功 |
| Token 无效 | 使用错误的 Token | 返回 401 "Token 格式错误" |
| Token 吊销 | 吊销后使用 Refresh Token | 返回 401 "Token 已被吊销" |
| IDOR 防护 | 请求他人数据 | 返回当前用户数据 |
| RLS 隔离 | 不同机构用户查询同一指标 | 返回各自机构数据 |

## 模拟用户数据

| 用户编号 | 姓名 | 部门 | 角色 | 余额 |
|----------|------|------|------|------|
| 000000001 | 张三 | 财务部 | viewer | 125,000 |
| 000000002 | 李四 | 财务部 | admin | 250,000 |
| 000000003 | 王五 | 技术部 | viewer | 88,000 |
| 000000004 | 赵六 | 人事部 | viewer | 150,000 |
| 000000005 | 钱七 | 技术部 | admin | 320,000 |

## 安全改进对比

| 对比项 | 原方案 | 新方案 |
|--------|--------|--------|
| Token 有效期 | 8 小时 | 15 分钟（Access）/ 7 天（Refresh） |
| 盗用风险窗口 | 8 小时 | 15 分钟 |
| Token 吊销 | 不支持 | ✅ 支持（Refresh Token 黑名单） |
| 自动刷新 | 不支持 | ✅ 支持 |
| Token 清单 | 无 | ✅ 服务器记录 |

## 详细文档

- **AI Agent 测试案例**：参见 `prototype/tests/README.md`
- **技术实现细节**：参见 `docs/mcp_prototype_sidecar.md`
