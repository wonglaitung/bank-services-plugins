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

### 用户信息工具

| 工具名 | 说明 |
|--------|------|
| `get_my_info` | 获取当前用户的完整信息 |
| `get_my_department` | 获取当前用户所在部门 |
| `get_my_balance` | 获取当前用户账户余额 |
| `check_my_permission` | 检查当前用户权限 |
| `list_all_users` | 管理员查询所有用户信息（不含金额） |

### 财务数据工具

| 工具名 | 说明 |
|--------|------|
| `get_finance_dictionary` | 获取财务指标元数据字典（包含指标列表和同义词） |
| `query_financial_metrics` | 查询财务指标数据（支持年份、季度、月度维度） |

**安全特性**：
- 所有工具不接受 `user_id` 参数，用户身份从 Token 自动获取
- mcp_remote 只传递 user_id，不做业务逻辑判断（如权限检查）
- 业务逻辑（权限验证、数据验证等）由 backend_api 负责

## 模拟用户数据

| 用户编号 | 姓名 | 部门 | 角色 | 余额 |
|----------|------|------|------|------|
| 000000001 | 张三 | 财务部 | viewer | 125,000 |
| 000000002 | 李四 | 财务部 | admin | 250,000 |
| 000000003 | 王五 | 技术部 | viewer | 88,000 |
| 000000004 | 赵六 | 人事部 | viewer | 150,000 |
| 000000005 | 钱七 | 技术部 | admin | 320,000 |

## 财务指标字典

### 支持的指标

| 标准名称 | 显示名 | 分类 | 单位 | 同义词 |
|----------|--------|------|------|--------|
| `NET_PROFIT` | 净利润 | 盈利能力 | 万元 | 纯利润、税后利润、利润总额 |
| `NET_INTEREST_INCOME` | 净利息收入 | 盈利能力 | 万元 | 利息收入、息差收入、净利息 |
| `TOTAL_ASSETS` | 资产总额 | 规模指标 | 万元 | 总资产、资产负债表资产、资产规模 |
| `TOTAL_LIABILITIES` | 负债总额 | 规模指标 | 万元 | 总负债、负债规模 |
| `NPL_RATIO` | 不良贷款率 | 风险指标 | % | 不良率、NPL |
| `CAR_RATIO` | 资本充足率 | 风险指标 | % | CAR |
| `LOAN_BALANCE` | 贷款余额 | 业务指标 | 万元 | 贷款总额、贷款规模 |
| `DEPOSIT_BALANCE` | 存款余额 | 业务指标 | 万元 | 存款总额、存款规模 |

### 用户-机构映射（RLS）

| 用户编号 | 机构代码 | 机构说明 |
|----------|----------|----------|
| 000000001 | BR001 | 某分行 |
| 000000002 | BR001 | 某分行 |
| 000000003 | BR002 | 另一分行 |
| 000000004 | BR001 | 某分行 |
| 000000005 | BR002 | 另一分行 |

**RLS 说明**：不同机构用户查询财务数据时，自动过滤为所属机构数据，实现数据隔离。

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

## AI Agent 测试案例

以下是在 Claude Code 等 AI Agent 中输入的自然语言测试案例，用于验证财务接口功能。

### 案例 1：查询可用指标

**用户输入**：
```
有哪些财务指标可以查询？
```

**预期响应**：AI 调用 `get_finance_dictionary` 工具，返回 8 个财务指标列表，包括净利润、不良贷款率、资产总额等，并说明每个指标的同义词和单位。

---

### 案例 2：年度净利润查询

**用户输入**：
```
查询去年的净利润
```

**预期响应**：AI 调用 `query_financial_metrics` 工具（metric=NET_PROFIT, year=2025），返回：
```
2025 年净利润为 125,000 万元（BR001 机构）
```

---

### 案例 3：季度数据查询

**用户输入**：
```
今年一季度的不良率是多少？
```

**预期响应**：AI 调用 `query_financial_metrics` 工具（metric=NPL_RATIO, year=2025, quarter=1），返回：
```
2025 年一季度不良贷款率为 1.65%（BR001 机构）
```

---

### 案例 4：同义词匹配

**用户输入**：
```
查一下纯利润
```

**预期响应**：AI 识别"纯利润"是"净利润"的同义词，调用 `query_financial_metrics` 工具返回净利润数据。

---

### 案例 5：跨年趋势分析

**用户输入**：
```
最近三年的资产总额变化趋势
```

**预期响应**：AI 调用 `query_financial_metrics` 工具（metric=TOTAL_ASSETS, granularity=yearly），返回：
```
资产总额趋势（BR001 机构）：
- 2025 年：9,800,000 万元
- 2024 年：9,200,000 万元
- 2023 年：8,500,000 万元
年均增长约 7.5%
```

---

### 案例 6：多指标对比

**用户输入**：
```
比较一下贷款余额和存款余额
```

**预期响应**：AI 分别调用 `query_financial_metrics` 查询 LOAN_BALANCE 和 DEPOSIT_BALANCE，返回对比数据：
```
2025 年对比（BR001 机构）：
- 贷款余额：6,400,000 万元
- 存款余额：8,200,000 万元
存贷比：78%
```

---

### 案例 7：季度明细查询

**用户输入**：
```
今年各季度的净利息收入
```

**预期响应**：AI 调用 `query_financial_metrics` 工具（metric=NET_INTEREST_INCOME, year=2025, granularity=quarterly），返回：
```
2025 年净利息收入（BR001 机构）：
- Q1：125,000 万元
- Q2：132,000 万元
- Q3：138,000 万元
- Q4：125,000 万元
全年合计：520,000 万元
```

---

### 案例 8：风险指标查询

**用户输入**：
```
今年的资本充足率和不良贷款率
```

**预期响应**：AI 调用两次 `query_financial_metrics` 工具，返回：
```
2025 年风险指标（BR001 机构）：
- 资本充足率：15.2%
- 不良贷款率：1.58%
两项指标均符合监管要求
```

---

### 案例 9：无效指标测试

**用户输入**：
```
查询营业收入
```

**预期响应**：AI 先调用 `get_finance_dictionary` 查找匹配项，发现不在列表中，返回：
```
抱歉，"营业收入"不在支持的指标列表中。
目前支持的盈利能力指标有：
- 净利润（NET_PROFIT）
- 净利息收入（NET_INTEREST_INCOME）
```

---

### 案例 10：RLS 行级安全验证

**切换用户后输入**：
```
查询今年的不良贷款率
```

**预期响应**：不同机构用户返回不同数据：
- BR001 用户（000000001）：返回 1.58%
- BR002 用户（000000003）：返回 1.82%

AI 不感知机构差异，数据隔离由后端自动完成。

---

### 测试案例汇总表

| # | 自然语言输入 | 调用工具 | 验证点 |
|---|-------------|----------|--------|
| 1 | 有哪些财务指标可以查询？ | get_finance_dictionary | 字典返回 |
| 2 | 查询去年的净利润 | query_financial_metrics | 年度查询 |
| 3 | 今年一季度的不良率是多少？ | query_financial_metrics | 季度参数 |
| 4 | 查一下纯利润 | query_financial_metrics | 同义词匹配 |
| 5 | 最近三年的资产总额变化趋势 | query_financial_metrics | 跨年趋势 |
| 6 | 比较一下贷款余额和存款余额 | query_financial_metrics × 2 | 多指标对比 |
| 7 | 今年各季度的净利息收入 | query_financial_metrics | 季度明细 |
| 8 | 今年的资本充足率和不良贷款率 | query_financial_metrics × 2 | 风险指标 |
| 9 | 查询营业收入 | get_finance_dictionary | 无效指标提示 |
| 10 | 查询今年的不良贷款率 | query_financial_metrics | RLS 隔离 |

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
- 定义所有 Tools（`get_my_info`、`get_my_department`、`get_my_balance`、`check_my_permission`、`list_all_users`）
- 从加密 Token 解密获取用户编号
- 透传 backend_api 的响应结果
- 提供 `/auth/refresh` 端点刷新 Token
- 提供 `/auth/revoke` 端点吊销 Token
- 正确处理 MCP notification 消息（不返回响应）

**关键原则**：
- mcp_remote 只传递 user_id，不做业务逻辑判断（如权限检查）
- 业务逻辑由 backend_api 负责

### 安全机制

- **Token 封装**：用户身份封装在加密 Token 中，本地代理无法查看
- **有效期验证**：Token 包含 `expires_at`，由远端服务验证
- **IDOR 防护**：所有工具不接受 `user_id` 参数，身份从 Token 自动获取
- **审计日志**：所有请求记录用户编号和操作