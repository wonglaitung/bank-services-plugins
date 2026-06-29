# 银行财务数字分身 MVP 实施方案

> **版本**：4.0.0
> **最后更新**：2026-05-27
> **适用范围**：银行财务数据仓库安全接入 MCP

---

## 目录

1. [概述](#1-概述)
2. [数据模型](#2-数据模型)
3. [后台 API 设计](#3-后台-api-设计)
4. [MCP 工具定义](#4-mcp-工具定义)
5. [安全机制](#5-安全机制)
6. [配置与部署](#6-配置与部署)
7. [设计指南](#7-设计指南)
8. [实施计划](#8-实施计划)

---

## 1. 概述

### 1.1 背景

银行财务数据仓库包含大量敏感数据，需要通过安全的方式将核心财务指标暴露给 AI Agent，实现"财务数字分身"功能。

**架构设计详见**：[MCP 安全认证原型文档](mcp_prototype_sidecar.md)

### 1.2 核心设计理念

```
脑力归 AI，视界归权限
```

- **AI 负责**：语义理解、意图识别、口径对齐
- **权限系统负责**：数据隔离、访问控制、审计追溯

### 1.3 方案目标

| 目标 | 说明 |
|------|------|
| **安全接入** | 符合银行合规要求的只读数据访问 |
| **智能交互** | 利用大模型语义能力解决口径模糊问题 |
| **快速落地** | 复用现有 MCP 原型，零架构重构 |

### 1.4 与现有原型的复用关系

| 原型组件 | 复用情况 | 说明 |
|----------|----------|------|
| `local_proxy/main.py` | ✅ 直接复用 | Token 自动刷新逻辑 |
| `mcp_remote/main.py` | ✅ 扩展复用 | 新增财务工具定义 |
| `backend_api/main.py` | 🔄 重构 | 新增财务 API 路由 |
| Token 生成工具 | ✅ 直接复用 | RSA-OAEP 加密 |

---

## 2. 数据模型

### 2.1 数据层次结构

```
财务数据仓库
├── 财务指标（Metrics）        # 单一数值，如净利润、不良率
├── 财务报表（Reports）        # 结构化报表，如资产负债表
└── 用户数据（Users）          # 用户信息、权限、余额
```

### 2.2 数据流

财务指标查询的完整请求流程：

```
1. 用户提问
   │  "去年的净利润是多少？"
   ▼
2. AI 语义匹配
   │  调用 get_finance_dictionary 获取字典
   │  在 synonyms 中匹配："净利润" → NET_PROFIT
   │  提取时间维度："去年" → year=2025
   ▼
3. MCP 工具调用
   │  query_financial_metrics(metric="NET_PROFIT", year=2025)
   │
   │  本地代理自动注入加密 Token（含 user_id）
   │  POST /mcp → 远端 MCP 服务
   ▼
4. 远端 MCP 服务
   │  解密 Token → 提取 user_id="000000001"
   │  注入 ContextVar: current_user_id
   │  调用后台 API
   ▼
5. 后台 API
   │  GET /api/finance/query?metric=NET_PROFIT&year=2025
   │  Header: X-User-ID: 000000001
   │
   │  白名单验证 ✓
   │  RLS 过滤：branch_id=BR001
   │  执行参数化查询
   ▼
6. 数据返回
   │  {
   │    "metric": "NET_PROFIT",
   │    "data": [{"period": "2025", "value": 125000.0}]
   │  }
   ▼
7. AI 格式化输出
      📊 2025年净利润：125,000 万元
```

**关键节点说明**：

| 步骤 | 关键操作 | 安全措施 |
|------|----------|----------|
| 2 | 语义匹配（synonyms） | 字典白名单 |
| 3 | Token 自动注入 | 本地代理无法解密 |
| 4 | Token 解密验证 | RSA-OAEP + 有效期 |
| 5 | RLS 行级安全 | 强制过滤 branch_id |

### 2.3 财务指标字典

财务指标字典是系统的核心元数据，用于：
- AI 语义匹配（用户输入 → 标准指标名）
- API 白名单验证
- 查询参数校验

```python
# backend_api/config/dictionary.py

FINANCE_DICTIONARY = {
    "metrics": [
        # 盈利能力
        {
            "standard_name": "NET_PROFIT",
            "display_name": "净利润",
            "category": "盈利能力",
            "unit": "万元",
            "description": "扣除所有成本、税费后的利润总额",
            "synonyms": ["纯利润", "税后利润", "利润总额"],
            "formula": "营业收入 - 营业成本 - 税费"
        },
        {
            "standard_name": "NET_INTEREST_INCOME",
            "display_name": "净利息收入",
            "category": "盈利能力",
            "unit": "万元",
            "description": "利息收入减去利息支出",
            "synonyms": ["利息收入", "息差收入", "净利息"],
            "formula": "利息收入 - 利息支出"
        },

        # 规模指标
        {
            "standard_name": "TOTAL_ASSETS",
            "display_name": "资产总额",
            "category": "规模指标",
            "unit": "万元",
            "description": "银行全部资产的总和",
            "synonyms": ["总资产", "资产负债表资产", "资产规模"],
            "formula": "各项资产之和"
        },
        {
            "standard_name": "TOTAL_LIABILITIES",
            "display_name": "负债总额",
            "category": "规模指标",
            "unit": "万元",
            "description": "银行全部负债的总和",
            "synonyms": ["总负债", "负债规模"],
            "formula": "各项负债之和"
        },

        # 风险指标
        {
            "standard_name": "NPL_RATIO",
            "display_name": "不良贷款率",
            "category": "风险指标",
            "unit": "%",
            "description": "不良贷款余额占贷款总额的比例",
            "synonyms": ["不良率", "不良贷款率", "NPL"],
            "formula": "不良贷款余额 / 贷款总额 × 100%"
        },
        {
            "standard_name": "CAR_RATIO",
            "display_name": "资本充足率",
            "category": "风险指标",
            "unit": "%",
            "description": "资本总额与加权风险资产的比例",
            "synonyms": ["资本充足率", "CAR"],
            "formula": "资本总额 / 风险加权资产 × 100%"
        },

        # 业务指标
        {
            "standard_name": "LOAN_BALANCE",
            "display_name": "贷款余额",
            "category": "业务指标",
            "unit": "万元",
            "description": "各项贷款的期末余额",
            "synonyms": ["贷款总额", "贷款规模"],
            "formula": "各项贷款之和"
        },
        {
            "standard_name": "DEPOSIT_BALANCE",
            "display_name": "存款余额",
            "category": "业务指标",
            "unit": "万元",
            "description": "各项存款的期末余额",
            "synonyms": ["存款总额", "存款规模"],
            "formula": "各项存款之和"
        },
    ],
    "dimensions": [
        {"name": "year", "display_name": "年份", "type": "int", "required": False},
        {"name": "quarter", "display_name": "季度", "type": "int", "range": "1-4"},
        {"name": "month", "display_name": "月份", "type": "int", "range": "1-12"},
        {"name": "granularity", "display_name": "聚合粒度", "type": "enum", "values": ["yearly", "quarterly", "monthly"]}
    ]
}

ALLOWED_METRICS = {m["standard_name"] for m in FINANCE_DICTIONARY["metrics"]}
```

### 2.4 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `standard_name` | str | 标准字段名（用于 API 查询） |
| `display_name` | str | 中文显示名 |
| `category` | str | 指标分类（盈利能力/风险指标/业务指标/规模指标） |
| `unit` | str | 计量单位 |
| `description` | str | 含义说明 |
| `synonyms` | list | 同义词/别名列表（用于语义匹配） |
| `formula` | str | 计算公式 |

### 2.5 用户数据模型

```python
# 用户-机构映射（RLS）
USER_BRANCH_MAPPING = {
    "000000001": "BR001",
    "000000002": "BR001",
    "000000003": "BR002",
}

# 用户数据
USERS_DB = {
    "000000001": {
        "user_id": "000000001",
        "name": "张三",
        "department": "财务部",
        "role": "admin",
        "balance": 100000.00
    },
    # ...
}
```

---

## 3. 后台 API 设计

### 3.1 API 端点总览

| 分类 | 端点 | 方法 | 说明 | 权限 |
|------|------|------|------|------|
| **字典** | `/api/finance/dictionary` | GET | 获取财务指标元数据字典 | 所有用户 |
| **指标查询** | `/api/finance/query` | GET | 查询财务指标数据 | 所有用户（RLS） |

**其他端点**（用户信息、管理员等）详见 [MCP 安全认证原型文档](mcp_prototype_sidecar.md)。

### 3.2 字典端点

**请求**：

```bash
GET /api/finance/dictionary
```

**响应**：

```json
{
  "metrics": [
    {
      "standard_name": "NET_PROFIT",
      "display_name": "净利润",
      "category": "盈利能力",
      "unit": "万元",
      "description": "扣除所有成本、税费后的利润总额",
      "synonyms": ["纯利润", "税后利润", "利润总额"],
      "formula": "营业收入 - 营业成本 - 税费"
    }
  ],
  "dimensions": [
    {"name": "year", "display_name": "年份", "type": "int"},
    {"name": "quarter", "display_name": "季度", "type": "int", "range": "1-4"}
  ]
}
```

### 3.3 指标查询端点

**请求**：

```bash
GET /api/finance/query?metric=NET_PROFIT&year=2025&granularity=yearly
X-User-ID: 000000001
```

**参数说明**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `metric` | str | ✅ | 指标名，必须是字典中的 `standard_name` |
| `year` | int | ❌ | 年份，不指定则返回最近数据 |
| `quarter` | int | ❌ | 季度（1-4），指定后按季度查询 |
| `month` | int | ❌ | 月份（1-12），指定后按月查询 |
| `granularity` | str | ❌ | 聚合粒度：yearly/quarterly/monthly，默认 yearly |

**响应**：

```json
{
  "metric": "NET_PROFIT",
  "metric_name": "净利润",
  "unit": "万元",
  "branch_id": "BR001",
  "granularity": "yearly",
  "data": [
    {"period": "2025", "value": 125000.0},
    {"period": "2024", "value": 112000.0},
    {"period": "2023", "value": 98000.0}
  ],
  "query_time": "2026-05-27T01:45:39.142574+00:00"
}
```

### 3.4 核心代码实现

```python
# backend_api/main.py

from fastapi import FastAPI, HTTPException, Header
from .config.dictionary import FINANCE_DICTIONARY, ALLOWED_METRICS

app = FastAPI(title="财务后台 API")


# ==================== 字典端点 ====================

@app.get("/api/finance/dictionary")
async def get_finance_dictionary():
    """获取财务指标元数据字典（静态返回）"""
    return FINANCE_DICTIONARY


# ==================== 指标查询端点 ====================

@app.get("/api/finance/query")
async def query_finance_metrics(
    metric: str,
    year: int = None,
    quarter: int = None,
    month: int = None,
    granularity: str = "yearly",
    x_user_id: str = Header(None, alias="X-User-ID")
):
    """
    查询财务指标数据

    安全措施：白名单验证 + RLS 行级安全 + 参数化查询
    """
    # 1. 验证用户编号
    if not x_user_id or not x_user_id.isdigit() or len(x_user_id) != 9:
        raise HTTPException(400, "用户编号格式错误")

    # 2. 白名单验证
    if metric not in ALLOWED_METRICS:
        raise HTTPException(400, f"不支持的指标: {metric}")

    # 3. 参数范围验证
    if quarter and not (1 <= quarter <= 4):
        raise HTTPException(400, "季度参数范围: 1-4")
    if month and not (1 <= month <= 12):
        raise HTTPException(400, "月份参数范围: 1-12")

    # 4. RLS：获取机构代码
    branch_id = USER_BRANCH_MAPPING.get(x_user_id, "BR000")

    # 5. 执行参数化查询（强制过滤 branch_id）
    results = await execute_finance_query(metric, branch_id, year, quarter, month)

    return {
        "metric": metric,
        "branch_id": branch_id,
        "data": results
    }
```

**其他端点**（用户信息、管理员等）详见 [MCP 安全认证原型文档](mcp_prototype_sidecar.md)。

---

## 4. MCP 工具定义

### 4.1 工具清单

| 分类 | 工具名 | 用途 | 权限 |
|------|--------|------|------|
| **字典** | `get_finance_dictionary` | 获取财务指标字典 | 所有用户 |
| **指标查询** | `query_financial_metrics` | 查询财务指标数据 | 所有用户（RLS） |

**其他工具**（用户信息、管理员等）详见 [MCP 安全认证原型文档](mcp_prototype_sidecar.md)。

### 4.2 核心工具实现

```python
# mcp_remote/main.py

from contextvars import ContextVar
from mcp.server.fastmcp import FastMCP

current_user_id: ContextVar[str] = ContextVar("current_user_id")
mcp = FastMCP("FinanceService")


# ==================== 字典工具 ====================

@mcp.tool()
async def get_finance_dictionary() -> dict:
    """
    获取财务指标元数据字典。

    当用户询问"有哪些财务指标"、"能查什么数据"、"指标列表"、"财务科目"
    或"支持查询哪些数据"时调用此工具。

    返回内容：
    - metrics: 指标列表，每项包含 standard_name、display_name、category、unit、description、synonyms
    - dimensions: 支持的查询维度

    使用建议：
    1. 查询具体指标前，先调用此工具确认指标名称
    2. 根据用户输入的关键词，在 synonyms 中查找匹配项
    3. 找到匹配后，使用 standard_name 调用 query_financial_metrics

    此工具为只读查询，不接受任何参数。
    """
    user_id = current_user_id.get()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/finance/dictionary",
            headers={"X-User-ID": user_id}
        )
        return response.json()


# ==================== 指标查询工具 ====================

@mcp.tool()
async def query_financial_metrics(
    metric: str,
    year: int = None,
    quarter: int = None,
    month: int = None,
    granularity: str = "yearly"
) -> dict:
    """
    查询财务指标数据。

    当用户询问具体财务指标数值时调用此工具，如"去年的净利润"、
    "一季度的不良率"、"资产负债情况"。

    参数说明：
    | 参数 | 类型 | 默认值 | 说明 |
    |------|------|--------|------|
    | metric | str | 必需 | 指标名，必须是字典中的 standard_name |
    | year | int | None | 年份(如 2025)，不指定则返回最近数据 |
    | quarter | int | None | 季度(1-4)，指定后按季度查询 |
    | month | int | None | 月份(1-12)，指定后按月查询 |
    | granularity | str | "yearly" | 聚合粒度:yearly/quarterly/monthly |

    常用查询场景示例：
    ┌─────────────────────────────────────────────────────────────────┐
    │ 用户问题                        │ 参数设置                      │
    ├─────────────────────────────────────────────────────────────────┤
    │ "去年的净利润"                  │ metric="NET_PROFIT",           │
    │                                 │ year=2025                     │
    ├─────────────────────────────────────────────────────────────────┤
    │ "一季度的不良率"                 │ metric="NPL_RATIO",           │
    │                                 │ year=2025, quarter=1          │
    ├─────────────────────────────────────────────────────────────────┤
    │ "最近三年的净利息收入"           │ metric="NET_INTEREST_INCOME", │
    │                                 │ year 不指定, granularity=      │
    │                                 │ "yearly"                      │
    ├─────────────────────────────────────────────────────────────────┤
    │ "各季度的资产负债总额"           │ metric="TOTAL_ASSETS",        │
    │                                 │ granularity="quarterly"       │
    └─────────────────────────────────────────────────────────────────┘

    安全约束：
    - 此工具仅能查询当前用户所属机构的数据
    - 不接受任何机构标识参数，机构代码自动过滤
    - 只能查询字典中定义的指标

    如不确定指标名称，请先调用 get_finance_dictionary 工具获取字典。
    """
    user_id = current_user_id.get()
    params = {"metric": metric, "granularity": granularity}
    if year:
        params["year"] = year
    if quarter:
        params["quarter"] = quarter
    if month:
        params["month"] = month

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/finance/query",
            params=params,
            headers={"X-User-ID": user_id}
        )
        return response.json()
```

**其他工具**（用户信息、管理员等）详见 [MCP 安全认证原型文档](mcp_prototype_sidecar.md)。

---

## 5. 安全机制

### 5.1 安全措施汇总

| 安全措施 | 实现位置 | 说明 |
|----------|----------|------|
| **Token 加密** | 远端 MCP 服务 | RSA-OAEP 加密，本地代理无法解密 |
| **IDOR 防护** | MCP 工具层 | user_id 从 Token 提取，不接受参数 |
| **白名单验证** | 后台 API | 只允许字典中定义的指标 |
| **RLS 行级安全** | 后台 API | 强制过滤 branch_id |
| **参数化查询** | 后台 API | 防止 SQL 注入 |
| **权限校验** | 后台 API | 管理员端点检查 role |

### 5.2 数据流安全

```
1. 用户请求
   │
   ▼
2. 本地代理：读取 Refresh Token → 获取 Access Token → 注入 Header
   │  （本地代理无法解密 Token 内容）
   ▼
3. 远端 MCP 服务：解密 Token → 提取 user_id → 注入 ContextVar
   │  （user_id 从加密 Token 提取，无法伪造）
   ▼
4. MCP 工具：从上下文获取 user_id → 调用后台 API
   │  （工具不接受 user_id 参数，防止越权）
   ▼
5. 后台 API：验证 user_id → RLS 过滤 → 返回数据
   │  （强制过滤 branch_id，确保数据隔离）
   ▼
6. 返回结果
```

**详细安全设计见**：[MCP 安全方案文档](mcp_security_authentication.md)

---

## 6. 配置与部署

### 6.1 目录结构

```
prototype/
├── local_proxy/
│   └── main.py                  # 本地 MCP 代理 (Stdio)
├── mcp_remote/
│   └── main.py                  # MCP Server (端口 8001)
├── backend_api/
│   ├── main.py                  # FastAPI 后台服务 (端口 8000)
│   ├── config/dictionary.py     # 财务指标字典配置
│   └── users.json               # 用户数据（原型）
└── tools/
    └── generate_token.py        # Token 生成工具
```

### 6.2 Claude Code 配置

```json
// .mcp.json
{
  "mcpServers": {
    "finance-proxy": {
      "command": "python",
      "args": ["/data/bank-services-plugins/prototype/local_proxy/main.py"],
      "env": {
        "REMOTE_MCP_URL": "http://localhost:8001",
        "MCP_REFRESH_TOKEN": "<使用 generate_token.py 生成>"
      }
    }
  }
}
```

### 6.3 环境变量

| 变量名 | 说明 | 组件 |
|--------|------|------|
| `MCP_REFRESH_TOKEN` | Refresh Token | 本地代理 |
| `REMOTE_MCP_URL` | 远端 MCP 地址 | 本地代理 |
| `RSA_PRIVATE_KEY` | RSA 私钥（PEM 格式） | 远端服务 |
| `BACKEND_API_URL` | 后台 API 地址 | 远端服务 |

### 6.4 Token 生成

```bash
# 生成 RSA 密钥对（首次使用）
python prototype/tools/generate_token.py --generate-key

# 生成 Token（Refresh Token 有效 7 天）
python prototype/tools/generate_token.py --user-id 000000001 --refresh-expires 7
```

### 6.5 启动服务

```bash
# 1. 启动后台 API (端口 8000)
python prototype/backend_api/main.py

# 2. 启动远端 MCP 服务 (端口 8001)
export RSA_PRIVATE_KEY="$(cat prototype/tools/private_key.pem)"
python prototype/mcp_remote/main.py

# 3. 重启 Claude Code（本地代理自动启动）
```

### 6.6 验证

```bash
# 健康检查
curl http://localhost:8000/health
curl http://localhost:8001/health

# 测试字典端点
curl http://localhost:8000/api/finance/dictionary

# 测试 MCP 工具（需要 Token）
TOKEN="<使用 generate_token.py 生成>"
curl -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

---

## 7. 设计指南

### 7.1 Skill 固化查询 SOP

AI Agent 的系统提示词由厂商控制，用户无法自定义。通过 Claude Code 的 **Skill 机制**，将财务查询的 SOP 固化到 SKILL.md 文档中。

**目录结构**：

```
.claude/skills/finance-query/
└── SKILL.md                    # 唯一必需文件
```

**SKILL.md 内容**：

```markdown
# 财务数据查询 Skill

## 功能描述

帮助用户查询银行财务数据，自动完成语义匹配和数据格式化。

## 使用场景

- "去年的净利润是多少？"
- "一季度的不良贷款率"
- "最近三年的资产总额变化"

## 执行流程

### 步骤 1：获取指标字典

调用 MCP 工具 `get_finance_dictionary`，获取所有支持的指标列表。

### 步骤 2：语义匹配

根据用户输入的关键词，在字典的 synonyms 字段中查找匹配项：

| 用户输入 | standard_name |
|----------|---------------|
| "纯利润" | NET_PROFIT |
| "不良率" | NPL_RATIO |
| "总资产" | TOTAL_ASSETS |

**匹配策略**：精确匹配 → 模糊匹配（相似度 > 0.8）→ 提示可用指标

### 步骤 3：调用查询工具

使用匹配到的 `standard_name` 调用 `query_financial_metrics` 工具。

### 步骤 4：格式化输出

📊 财务指标查询结果

**指标**：净利润（NET_PROFIT）
**单位**：万元

| 时期 | 数值 |
|------|------|
| 2025 | 125,000.00 |

### 步骤 5：异常处理

无法匹配时，提示用户可用的指标列表（按分类分组）。

## 注意事项

- 仅支持查询，不支持修改数据
- 所有查询自动应用 RLS 行级安全过滤
- 查询结果仅显示当前用户所属机构的数据
```

### 7.2 大宽表/数据仓库工具设计

数据仓库大宽表通常包含**大量字段**（50-100+ 列），与简单业务场景不同，需要专门的设计策略。

#### 7.2.1 核心挑战

| 挑战 | 说明 |
|------|------|
| **字段过多** | 不可能为每个字段创建单独工具 |
| **查询维度多样** | 用户可能按时间、部门、地区、产品等多维度查询 |
| **聚合需求** | 用户可能需要汇总、统计、排名 |
| **模型认知负担** | 工具描述太长会超出上下文，太短则覆盖不全 |

#### 7.2.2 推荐方案：按业务域拆分工具

**不要为每个字段创建工具**，而是按业务域/查询场景拆分：

```python
# ❌ 错误：每个字段一个工具（字段太多）
@mcp.tool()
async def get_sales_amount() -> dict: ...
@mcp.tool()
async def get_sales_quantity() -> dict: ...
# ... 50+ 个工具

# ✅ 正确：按业务域拆分
@mcp.tool()
async def query_sales_summary(
    dimension: str,      # 维度：region/product/time
    metrics: list[str],  # 指标：amount/quantity/profit
    filters: dict        # 筛选条件
) -> dict:
    """
    查询销售汇总数据。

    当用户询问"销售额"、"销量"、"销售统计"、"按地区/产品销售"时调用。

    支持维度：
    - region: 按地区
    - product: 按产品
    - time: 按时间（日/月/年）

    支持指标：
    - amount: 销售金额
    - quantity: 销售数量
    - profit: 利润

    示例：
    - "各地区的销售额" → dimension="region", metrics=["amount"]
    - "各产品的销量和利润" → dimension="product", metrics=["quantity", "profit"]
    """
```

#### 7.2.3 元数据工具设计

提供**动态获取字段信息**的工具，而非在描述中静态枚举所有字段：

```python
@mcp.tool()
async def list_tables() -> dict:
    """
    获取数据仓库可用表列表。

    当用户不确定有哪些数据表时调用。
    返回表名、描述、字段数量。
    """
    pass


@mcp.tool()
async def describe_table(table: str) -> dict:
    """
    获取表的字段元数据。

    当用户需要了解表结构时调用。
    返回字段名、类型、描述、是否可筛选、是否可分组。

    示例返回：
    {
        "table": "sales_fact",
        "fields": [
            {"name": "sales_amount", "type": "decimal", "desc": "销售金额", "filterable": true},
            {"name": "quantity", "type": "int", "desc": "销售数量", "filterable": true},
            {"name": "region", "type": "string", "desc": "地区", "groupable": true}
        ]
    }
    """
    pass
```

#### 7.2.4 示例驱动的描述

大宽表字段多，**用示例代替完整枚举**：

```python
@mcp.tool()
async def query_sales_data(
    metrics: list[str],
    dimensions: list[str] = None,
    filters: dict = None
) -> dict:
    """
    查询销售数据。

    当用户询问销售相关问题时调用。

    常用查询场景示例：
    ┌─────────────────────────────────────────────────────────────┐
    │ 用户问题                        │ 参数设置                    │
    ├─────────────────────────────────────────────────────────────┤
    │ "各地区销售额"                  │ metrics=["sales_amount"],   │
    │                                 │ dimensions=["region"]       │
    ├─────────────────────────────────────────────────────────────┤
    │ "2024年各产品销量和利润"         │ metrics=["quantity","profit"]│
    │                                 │ dimensions=["product"],     │
    │                                 │ filters={"year": 2024}      │
    ├─────────────────────────────────────────────────────────────┤
    │ "华东区最近一个月各渠道销售"      │ metrics=["sales_amount"],   │
    │                                 │ dimensions=["channel"],     │
    │                                 │ filters={"region": "华东"}  │
    └─────────────────────────────────────────────────────────────┘

    完整字段列表请调用 describe_table("sales_fact") 获取。
    """
```

#### 7.2.5 分页和性能说明

大宽表查询可能返回大量数据，**必须在描述中说明分页机制**：

```python
@mcp.tool()
async def query_fact_table(
    table: str,
    select_fields: list[str],
    filters: dict = None,
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    查询数据仓库事实表。

    返回数据限制：
    - 默认返回前 100 行
    - 最大 1000 行（limit 参数上限）
    - 如需更多数据，使用 offset 分页
    - 查询超时时间：30 秒

    返回格式：
    {
        "data": [...],           # 数据行
        "total": 5000,           # 总行数
        "limit": 100,            # 当前限制
        "offset": 0,             # 当前偏移
        "has_more": true         # 是否有更多数据
    }
    """
```

#### 7.2.6 聚合查询工具

提供专门的聚合查询工具，避免返回大量明细数据：

```python
@mcp.tool()
async def query_aggregation(
    table: str,
    metric: str,
    aggregation: str,  # sum, avg, max, min, count
    dimensions: list[str] = None,
    filters: dict = None
) -> dict:
    """
    查询数据仓库聚合结果。

    当用户需要查询汇总值时调用，如"总销售额"、"平均利润"。

    支持的聚合函数：
    - sum: 求和
    - avg: 平均值
    - max: 最大值
    - min: 最小值
    - count: 计数

    示例：
    - "总销售额是多少" → metric="sales_amount", aggregation="sum"
    - "平均利润率" → metric="margin", aggregation="avg"
    - "各地区的总销售额" → metric="sales_amount", aggregation="sum", dimensions=["region"]
    """
    pass
```

#### 7.2.7 推荐工具组合

| 工具类型 | 工具名称 | 用途 |
|----------|----------|------|
| **元数据查询** | `list_tables` | 获取可用表列表 |
| **元数据查询** | `describe_table` | 获取表字段元数据 |
| **明细查询** | `query_fact_table` | 查询明细数据（带分页） |
| **汇总查询** | `query_metrics` | 按维度汇总指标 |
| **聚合查询** | `query_aggregation` | 单值聚合（sum/avg/max/min） |

#### 7.2.8 检查清单

| # | 检查项 | 是否通过 |
|---|--------|----------|
| 1 | 是否按业务域拆分工具，而非按字段？ | ☐ |
| 2 | 是否提供了 `list_tables` / `describe_table` 元数据工具？ | ☐ |
| 3 | 是否用示例说明参数用法，而非完整枚举字段？ | ☐ |
| 4 | 是否说明了分页机制和返回行数限制？ | ☐ |
| 5 | 是否说明了查询超时时间？ | ☐ |
| 6 | 是否标注了只读/可写权限？ | ☐ |
| 7 | 是否提供了常见查询场景示例？ | ☐ |
| 8 | 参数是否支持灵活筛选（而非固定字段）？ | ☐ |

---

## 8. 实施计划

### 8.1 第一阶段：三大财务报表

MVP 第一阶段将实现三大财务报表（资产负债表、利润表、现金流量表）的查询功能。

#### 8.1.1 报表特点分析

| 报表 | 特点 | 典型字段数 | 查询场景 |
|------|------|-----------|----------|
| **资产负债表** | 时点数据，结构化强 | 50-100 项 | 查某日/某月末的资产、负债、所有者权益 |
| **利润表** | 期间数据，需对比 | 30-50 项 | 查某季/某年的收入、成本、利润 |
| **现金流量表** | 期间数据，三类活动 | 40-60 项 | 查经营/投资/筹资现金流 |

#### 8.1.2 设计方案

**推荐方案**：为每个报表创建独立工具，而非统一查询工具。

**理由**：
- 用户意图清晰（"查资产负债表"直接匹配对应工具）
- 每个报表的参数语义不同（时点 vs 期间）
- 符合财务人员的认知习惯

#### 8.1.3 新增 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/finance/balance-sheet` | GET | 查询资产负债表 |
| `/api/finance/income-statement` | GET | 查询利润表 |
| `/api/finance/cash-flow-statement` | GET | 查询现金流量表 |
| `/api/finance/report-items` | GET | 获取报表科目列表 |

#### 8.1.4 新增 MCP 工具

| 工具名 | 用途 | 关键参数 |
|--------|------|----------|
| `get_balance_sheet` | 资产负债表 | `as_of_date`（截止日期） |
| `get_income_statement` | 利润表 | `year`, `quarter`, `compare_with`（同比/环比） |
| `get_cash_flow_statement` | 现金流量表 | `year`, `quarter`, `activity_type`（活动类型） |
| `get_finance_report_items` | 报表科目元数据 | `report_type` |

#### 8.1.5 数据库表结构

```sql
-- 资产负债表
CREATE TABLE balance_sheet (
    id SERIAL PRIMARY KEY,
    branch_id VARCHAR(10) NOT NULL,
    as_of_date DATE NOT NULL,
    item_name VARCHAR(100) NOT NULL,
    item_value DECIMAL(18,2),
    category VARCHAR(50) NOT NULL,       -- 资产/负债/所有者权益
    sub_category VARCHAR(50),
    display_order INT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 利润表
CREATE TABLE income_statement (
    id SERIAL PRIMARY KEY,
    branch_id VARCHAR(10) NOT NULL,
    year INT NOT NULL,
    quarter INT,
    item_name VARCHAR(100) NOT NULL,
    item_value DECIMAL(18,2),
    category VARCHAR(50) NOT NULL,       -- 营业收入/营业成本/利润
    display_order INT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 现金流量表
CREATE TABLE cash_flow_statement (
    id SERIAL PRIMARY KEY,
    branch_id VARCHAR(10) NOT NULL,
    year INT NOT NULL,
    quarter INT,
    item_name VARCHAR(100) NOT NULL,
    item_value DECIMAL(18,2),
    activity_type VARCHAR(20) NOT NULL,  -- operating/investing/financing
    display_order INT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_balance_sheet_branch_date ON balance_sheet(branch_id, as_of_date);
CREATE INDEX idx_income_statement_branch_year ON income_statement(branch_id, year, quarter);
CREATE INDEX idx_cash_flow_branch_year ON cash_flow_statement(branch_id, year, quarter);
```

#### 8.1.6 实施检查清单

| # | 检查项 | 状态 |
|---|--------|------|
| 1 | 后台 API：资产负债表端点 | 📝 |
| 2 | 后台 API：利润表端点 | 📝 |
| 3 | 后台 API：现金流量表端点 | 📝 |
| 4 | 后台 API：报表科目端点 | 📝 |
| 5 | MCP 工具：get_balance_sheet | 📝 |
| 6 | MCP 工具：get_income_statement | 📝 |
| 7 | MCP 工具：get_cash_flow_statement | 📝 |
| 8 | MCP 工具：get_finance_report_items | 📝 |
| 9 | 字典扩展：reports 部分 | 📝 |
| 10 | 数据库表创建与数据导入 | 📝 |

---

## 9. 参考资料

- [MCP 安全认证原型文档](mcp_prototype_sidecar.md) - 架构设计详解
- [MCP 安全方案文档](mcp_security_authentication.md) - 安全机制详解
- [MCP 工具描述最佳实践](mcp_tool_description_best_practices.md) - 工具描述规范
- [MCP 官方文档](https://modelcontextprotocol.io/)
