# 银行财务数字分身 MVP 实施方案

> **版本**：1.0.0
> **最后更新**：2026-05-26
> **适用范围**：银行财务数据仓库安全接入 MCP

---

## 目录

1. [概述](#1-概述)
2. [总体架构设计](#2-总体架构设计)
3. [核心模块与职责划分](#3-核心模块与职责划分)
4. [工具设计与描述规范](#4-工具设计与描述规范)
5. [核心业务流程](#5-核心业务流程)
6. [安全与内控审计](#6-安全与内控审计)
7. [技术实现细节](#7-技术实现细节)
8. [项目分阶段演进路线](#8-项目分阶段演进路线)
9. [实施检查清单](#9-实施检查清单)
10. [下一步行动指南](#10-下一步行动指南)

---

## 1. 概述

### 1.1 背景

银行财务数据仓库包含大量敏感数据，需要通过安全的方式将核心财务指标暴露给 AI Agent（如 OpenClaw），实现"财务数字分身"功能。传统方案面临以下挑战：

| 挑战 | 说明 |
|------|------|
| **合规要求** | 银行严格的数据访问控制，禁止越权查看 |
| **模糊匹配** | 后端难以实现灵活的语义匹配（如"纯利润"→"净利润"） |
| **数据安全** | Token 泄露、IDOR 攻击等风险 |
| **审计追溯** | 所有数据访问需可追溯 |

### 1.2 方案目标

通过 **Sidecar 模式 + AI 语义对齐**，以最低成本实现：

1. **安全接入**：符合银行合规要求的只读数据访问
2. **智能交互**：利用大模型语义能力解决口径模糊问题
3. **快速落地**：复用现有 MCP 安全认证原型，零架构重构

### 1.3 核心设计理念

```
脑力归 AI，视界归权限
```

- AI 负责语义理解、意图识别、口径对齐
- 权限系统负责数据隔离、访问控制、审计追溯

---

## 2. 总体架构设计

### 2.1 四层架构

本方案严格继承 **Sidecar / 本地网关模式**，由四个核心层次组成：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户边界（Agent 层）                            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  OpenClaw AI Agent                                                  │   │
│  │  • 自然语言理解                                                     │   │
│  │  • 意图识别                                                         │   │
│  │  • 语义匹配（字典对齐）                                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ MCP 协议 (Stdio)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              本地边界（Sidecar Proxy 层）                    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Local Proxy                                                        │   │
│  │  • Stdio 连接维持                                                   │   │
│  │  • Access/Refresh Token 动态管理                                    │   │
│  │  • MCP 协议透明透传                                                 │   │
│  │  • 自动注入 Authorization Header                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ HTTPS + 加密 Token
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              网络/安全边界（MCP Remote 层）                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  MCP Remote Server                                                  │   │
│  │  • AES-256-GCM Token 解密                                           │   │
│  │  • 提取 user_id 注入上下文 (ContextVar)                             │   │
│  │  • 工具声明与调用                                                   │   │
│  │  • 请求审计日志                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ HTTP (内网)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据边界（Backend API & 数仓层）                 │
│                                                                             │
│  ┌───────────────────┐      ┌───────────────────┐      ┌───────────────┐ │
│  │  Backend API      │      │  财务数仓          │      │  审计日志      │ │
│  │  • 字典端点        │──────▶  • 3-5 张核心表   │      │  • 访问记录    │ │
│  │  • 查询端点        │      │  • 只读账号        │      │  • 零金额存储  │ │
│  │  • RLS 行级安全    │      │  • 参数化查询      │      │               │ │
│  └───────────────────┘      └───────────────────┘      └───────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 各层职责

| 层级 | 组件 | 核心职责 |
|------|------|----------|
| **用户边界** | OpenClaw Agent | 自然语言交互、语义匹配、意图识别 |
| **本地边界** | Local Proxy | Token 管理、协议透传、安全注入 |
| **网络/安全边界** | MCP Remote | Token 解密、身份注入、工具暴露 |
| **数据边界** | Backend API + 数仓 | 数据查询、权限过滤、审计记录 |

### 2.3 与现有原型的复用关系

| 现有原型组件 | MVP 复用情况 | 说明 |
|--------------|--------------|------|
| `local_proxy/main.py` | ✅ 直接复用 | Token 自动刷新逻辑无需修改 |
| `mcp_remote/main.py` | ✅ 扩展复用 | 新增财务工具定义 |
| `backend_api/main.py` | 🔄 重构 | 改为财务 API 路由 |
| Token 生成工具 | ✅ 直接复用 | 无需修改 |
| 加密/解密模块 | ✅ 直接复用 | AES-256-GCM |

---

## 3. 核心模块与职责划分

### 3.1 Backend API 核心端点设计

为了以最快速度跑通闭环，Backend API 仅需实现 **2 个核心业务路由**：

#### 3.1.1 元数据字典端点 (`/api/finance/dictionary`)

**职责**：将 3~5 张财务表里首批开放的十几个核心指标，硬编码为包含标准字段、显示名称、详细描述及同义词的 JSON 列表，作为大模型的"翻字表"。

**特点**：
- 纯静态返回，无需检索数仓
- 由业务专家维护，技术门槛低
- 支持同义词/别名，便于 AI 语义对齐

**返回格式**：
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
    {"name": "quarter", "display_name": "季度", "type": "int", "range": "1-4"},
    {"name": "branch_id", "display_name": "机构", "type": "string", "note": "自动过滤"}
  ]
}
```

#### 3.1.2 参数化查询端点 (`/api/finance/query`)

**职责**：仅接受字典中定义的 `standard_metric_name`，执行参数化查询。

**安全措施**：
- 白名单验证：只允许查询字典中定义的指标
- RLS 强制过滤：`WHERE branch_id = :branch_id` 硬编码
- 参数化查询：防止 SQL 注入
- 数据聚合：返回统计结果，避免明细数据撑爆上下文

**请求格式**：
```json
{
  "metric": "NET_PROFIT",
  "year": 2025,
  "quarter": 1,
  "granularity": "quarterly"
}
```

**响应格式**：
```json
{
  "metric": "NET_PROFIT",
  "metric_name": "净利润",
  "unit": "万元",
  "data": [
    {"period": "2025-Q1", "value": 125000.00}
  ],
  "query_time": "2026-05-26T10:30:00Z"
}
```

### 3.2 MCP Remote 工具定义

基于字典端点和查询端点，MCP Remote 需要暴露 2 个工具：

| 工具名 | 用途 | 对应端点 |
|--------|------|----------|
| `get_finance_dictionary` | 获取指标字典 | `/api/finance/dictionary` |
| `query_financial_metrics` | 查询财务指标 | `/api/finance/query` |

---

## 4. 工具设计与描述规范

### 4.1 字典查询工具

遵循 `docs/mcp_tool_description_best_practices.md` 的描述规范：

```python
@mcp.tool()
@secure_api_call
async def get_finance_dictionary() -> dict:
    """
    获取财务指标元数据字典。

    当用户询问"有哪些财务指标"、"能查什么数据"、"指标列表"、"财务科目"或"支持查询哪些数据"时调用此工具。

    返回内容：
    - metrics: 指标列表，每项包含：
        - standard_name: 标准字段名（用于查询）
        - display_name: 中文显示名
        - category: 指标分类（如"盈利能力"、"风险指标"）
        - unit: 计量单位
        - description: 含义说明
        - synonyms: 同义词/别名列表
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
        response.raise_for_status()
        return response.json()
```

### 4.2 财务指标查询工具

```python
@mcp.tool()
@secure_api_call
async def query_financial_metrics(
    metric: str,
    year: int = None,
    quarter: int = None,
    month: int = None,
    granularity: str = "yearly"
) -> dict:
    """
    查询财务指标数据。

    当用户询问具体财务指标数值时调用此工具，如"去年的净利润"、"一季度的不良率"、"资产负债情况"。

    参数说明：
    | 参数 | 类型 | 默认值 | 说明 |
    |------|------|--------|------|
    | metric | str | 必需 | 指标名，必须是字典中的 standard_name |
    | year | int | None | 年份（如 2025），不指定则返回最近数据 |
    | quarter | int | None | 季度（1-4），指定后按季度查询 |
    | month | int | None | 月份（1-12），指定后按月查询 |
    | granularity | str | "yearly" | 聚合粒度：yearly/quarterly/monthly |

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

    返回数据限制：单次最多返回 1000 行数据。

    安全约束：
    - 此工具仅能查询当前用户所属机构的数据
    - 不接受任何机构标识参数，机构代码自动过滤
    - 只能查询字典中定义的指标

    如不确定指标名称，请先调用 get_finance_dictionary 工具获取字典。
    """
    user_id = current_user_id.get()

    params = {
        "metric": metric,
        "granularity": granularity
    }
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
        if response.status_code >= 400:
            return response.json()
        return response.json()
```

---

## 5. 核心业务流程

### 5.1 正常查询流程：AI 语义匹配

当用户输入模糊口径（如"纯利润"）时，系统流转逻辑如下：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          正常查询流程                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [用户提问: 帮我查去年的纯利润]                                              │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────┐                                                        │
│  │ OpenClaw Agent  │                                                        │
│  │                 │                                                        │
│  │ 1. 分析意图     │                                                        │
│  │ 2. 需要查字典   │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  调用 get_finance_dictionary()                                              │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Local Proxy                                                        │    │
│  │ • 自动注入加密 Token                                                │    │
│  │ • 透传 MCP 协议                                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ MCP Remote                                                         │    │
│  │ • 解密 Token                                                       │    │
│  │ • 提取 user_id                                                     │    │
│  │ • 注入 ContextVar                                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Backend API                                                        │    │
│  │ • 返回静态字典 JSON                                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                 │
│           ▼                                                                 │
│  返回字典: { metrics: [{ standard_name: "NET_PROFIT", synonyms: ["纯利润"] }] } │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ OpenClaw Agent 本地语义匹配                                         │    │
│  │                                                                     │    │
│  │ 发现 "纯利润" 命中 synonyms                                         │    │
│  │ 对应 standard_name = "NET_PROFIT"                                   │    │
│  │ 年份 = 2025 (去年)                                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                 │
│           ▼                                                                 │
│  调用 query_financial_metrics(metric="NET_PROFIT", year=2025)               │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Backend API                                                        │    │
│  │ • 验证 metric 在白名单                                              │    │
│  │ • 从 user_id 获取 branch_id                                         │    │
│  │ • 执行参数化查询（强制 RLS 过滤）                                    │    │
│  │ • 返回聚合数据                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                 │
│           ▼                                                                 │
│  返回: { metric: "NET_PROFIT", data: [{ period: "2025", value: 125000 }] }  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 异常/无法匹配拦截流程

当用户输入的词在字典里完全找不到时，大模型在前端自动拦截：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          异常拦截流程                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [用户提问: 查一下某某网点的报销差旅费]                                       │
│         │                                                                   │
│         ▼                                                                   │
│  调用 get_finance_dictionary()                                              │
│         │                                                                   │
│         ▼                                                                   │
│  AI 本地匹配: "报销差旅费" 未找到                                            │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ AI 智能拦截与引导                                                   │    │
│  │                                                                     │    │
│  │ "抱歉主管，'报销差旅费'不在当前开放的财务指标范围内。                │    │
│  │                                                                     │    │
│  │ 目前支持的财务指标包括：                                            │    │
│  │ • 净利息收入、净利润（盈利类）                                       │    │
│  │ • 资产负债总额（规模类）                                            │    │
│  │ • 不良率、资本充足率（风险类）                                       │    │
│  │                                                                     │    │
│  │ 您是否想查询以上指标？或者可以换个说法，比如：                        │    │
│  │ • '去年的利润情况'                                                  │    │
│  │ • '一季度的不良率'"                                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  [不向后端发送无效请求，节省资源]                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 安全与内控审计

### 6.1 安全措施总览

| 安全层级 | 措施 | 说明 |
|----------|------|------|
| **传输层** | HTTPS | 加密传输，防止中间人攻击 |
| **认证层** | AES-256-GCM Token | 加密 Token，本地代理无法查看 |
| **授权层** | RLS 行级安全 | SQL 强制过滤 branch_id |
| **数据层** | 只读账号 | 数据库权限限制为 SELECT |
| **审计层** | Read-Audit Log | 所有查询可追溯 |

### 6.2 RLS 行级安全实现

```python
# backend/api/routers/finance.py

# 白名单：只允许查询字典中定义的指标
ALLOWED_METRICS = {
    "NET_PROFIT", "NET_INTEREST_INCOME", "TOTAL_ASSETS",
    "TOTAL_LIABILITIES", "NPL_RATIO", "CAR_RATIO"
}

async def query_financial_data(
    metric: str,
    user_id: str,
    year: int = None,
    quarter: int = None
) -> dict:
    """查询财务数据（带 RLS）"""

    # 1. 白名单验证
    if metric not in ALLOWED_METRICS:
        raise HTTPException(400, f"不支持的指标: {metric}")

    # 2. 从 user_id 获取机构代码（可缓存）
    branch_id = await get_branch_id(user_id)

    # 3. 构建参数化查询
    query = """
        SELECT year, quarter, metric_value as value
        FROM finance_metrics
        WHERE metric_name = %s
          AND branch_id = %s  -- RLS 强制过滤，无法绕过
    """
    params = [metric, branch_id]

    if year:
        query += " AND year = %s"
        params.append(year)

    if quarter:
        query += " AND quarter = %s"
        params.append(quarter)

    # 4. 执行查询（使用只读账号）
    results = await db.execute(query, params)

    return {
        "metric": metric,
        "branch_id": branch_id,  # 返回但不暴露其他机构
        "data": results
    }
```

### 6.3 审计日志设计

#### 6.3.1 日志记录内容

```python
# 审计日志中间件

async def audit_log_middleware(request: Request, call_next):
    """审计日志中间件"""

    # 记录查询请求
    audit_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operator_user_id": request.headers.get("X-User-ID"),
        "target_endpoint": request.url.path,
        "queried_metric": request.query_params.get("metric"),
        "query_params": dict(request.query_params),
        "data_volume_rows": 0,  # 查询后填充
        "response_time_ms": 0
    }

    start_time = time.time()
    response = await call_next(request)
    audit_record["response_time_ms"] = (time.time() - start_time) * 1000

    # 异步写入审计日志（不阻塞响应）
    await write_audit_log(audit_record)

    return response
```

#### 6.3.2 零数据缓存原则

**禁止记录**：
- 查询返回的具体财务金额
- 明细数据内容
- 敏感字段值

**允许记录**：
- 操作者 ID
- 查询时间
- 查询的指标名称
- 数据量（行数）
- 响应时间

```sql
-- 审计日志表结构
CREATE TABLE finance_query_audit (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    operator_user_id VARCHAR(9) NOT NULL,
    operator_branch_id VARCHAR(10),
    target_endpoint VARCHAR(100),
    queried_metric VARCHAR(50),
    query_params JSONB,
    data_volume_rows INTEGER,
    response_time_ms INTEGER
);

-- 注意：不包含任何金额字段
```

### 6.4 数据库只读账号配置

```sql
-- 创建只读账号
CREATE USER finance_readonly WITH PASSWORD 'secure_password';

-- 仅授予特定表的 SELECT 权限
GRANT SELECT ON finance_metrics TO finance_readonly;
GRANT SELECT ON balance_sheet TO finance_readonly;
GRANT SELECT ON income_statement TO finance_readonly;
GRANT SELECT ON risk_indicators TO finance_readonly;
GRANT SELECT ON capital adequacy TO finance_readonly;

-- 禁止任何修改操作
REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM finance_readonly;
```

---

## 7. 技术实现细节

### 7.1 目录结构

```
prototype/
├── local_proxy/
│   └── main.py              # 复用现有实现
├── mcp_remote/
│   └── main.py              # 扩展：新增财务工具
├── backend_api/
│   ├── main.py              # FastAPI 入口
│   ├── routers/
│   │   └── finance.py       # 财务 API 路由
│   ├── models/
│   │   └── finance.py       # 数据模型
│   ├── middleware/
│   │   └── audit.py         # 审计中间件
│   ├── config/
│   │   └── dictionary.py    # 静态字典配置
│   └── requirements.txt
└── tools/
    └── generate_token.py    # 复用现有实现
```

### 7.2 字典配置文件

```python
# backend_api/config/dictionary.py

FINANCE_DICTIONARY = {
    "metrics": [
        {
            "standard_name": "NET_PROFIT",
            "display_name": "净利润",
            "category": "盈利能力",
            "unit": "万元",
            "description": "扣除所有成本、税费后的利润总额",
            "synonyms": ["纯利润", "税后利润", "利润总额", "净利润"],
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
        }
    ],
    "dimensions": [
        {"name": "year", "display_name": "年份", "type": "int", "required": False},
        {"name": "quarter", "display_name": "季度", "type": "int", "range": "1-4"},
        {"name": "month", "display_name": "月份", "type": "int", "range": "1-12"},
        {
            "name": "granularity",
            "display_name": "聚合粒度",
            "type": "enum",
            "values": ["yearly", "quarterly", "monthly"]
        }
    ]
}
```

### 7.3 财务路由实现

```python
# backend_api/routers/finance.py

from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from ..config.dictionary import FINANCE_DICTIONARY

router = APIRouter(prefix="/api/finance", tags=["财务数据"])

# 指标白名单
ALLOWED_METRICS = {m["standard_name"] for m in FINANCE_DICTIONARY["metrics"]}


@router.get("/dictionary")
async def get_dictionary():
    """
    获取财务指标元数据字典

    纯静态返回，无需数据库查询。
    """
    return FINANCE_DICTIONARY


@router.get("/query")
async def query_metrics(
    metric: str,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    granularity: str = "yearly",
    x_user_id: str = Header(None, alias="X-User-ID")
):
    """
    查询财务指标数据

    安全措施：
    1. 白名单验证
    2. RLS 行级安全
    3. 参数化查询
    """
    # 1. 白名单验证
    if metric not in ALLOWED_METRICS:
        raise HTTPException(400, f"不支持的指标: {metric}")

    # 2. 参数校验
    if quarter and (quarter < 1 or quarter > 4):
        raise HTTPException(400, "季度必须在 1-4 之间")

    if month and (month < 1 or month > 12):
        raise HTTPException(400, "月份必须在 1-12 之间")

    # 3. 获取机构代码（RLS）
    branch_id = await get_branch_id(x_user_id)

    # 4. 执行查询
    results = await execute_finance_query(
        metric=metric,
        branch_id=branch_id,
        year=year,
        quarter=quarter,
        month=month,
        granularity=granularity
    )

    # 5. 获取指标元数据
    metric_info = next(
        (m for m in FINANCE_DICTIONARY["metrics"] if m["standard_name"] == metric),
        {}
    )

    return {
        "metric": metric,
        "metric_name": metric_info.get("display_name"),
        "unit": metric_info.get("unit"),
        "branch_id": branch_id,
        "data": results,
        "query_time": datetime.now(timezone.utc).isoformat()
    }


async def get_branch_id(user_id: str) -> str:
    """
    从 user_id 获取机构代码

    实际实现应查询用户表或缓存。
    """
    # TODO: 实现用户-机构映射查询
    # 示例：从数据库或缓存获取
    user_mapping = {
        "000000001": "BR001",  # 张三 -> 某分行
        "000000002": "BR001",
        "000000003": "BR002",
    }
    return user_mapping.get(user_id, "BR000")


async def execute_finance_query(
    metric: str,
    branch_id: str,
    year: Optional[int],
    quarter: Optional[int],
    month: Optional[int],
    granularity: str
) -> list:
    """
    执行财务数据查询（参数化）

    实际实现应使用数据库连接池。
    """
    # 参数化查询模板
    query = """
        SELECT
            year,
            quarter,
            month,
            metric_value as value
        FROM finance_metrics
        WHERE metric_name = %s
          AND branch_id = %s  -- RLS 强制过滤
    """
    params = [metric, branch_id]

    if year:
        query += " AND year = %s"
        params.append(year)

    if quarter:
        query += " AND quarter = %s"
        params.append(quarter)

    if month:
        query += " AND month = %s"
        params.append(month)

    # 限制返回行数
    query += " ORDER BY year DESC, quarter DESC, month DESC LIMIT 1000"

    # TODO: 执行实际数据库查询
    # results = await db.fetch_all(query, params)

    # 模拟返回
    return [
        {"period": "2025", "value": 125000.00}
    ]
```

---

## 8. 项目分阶段演进路线

### 8.1 演进路线图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              演进路线                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  【第 1 阶段：婴儿期 MVP】                                                    │
│  ━━━━━━━━━━━━━━━━━━━━━━                                                     │
│  目标：打通 Read-Only 闭环                                                   │
│  做法：                                                                      │
│  • 硬编码 3-5 张表的十几只核心指标到 /dictionary 端点                          │
│  • 让 AI 当翻译官，通过大白话查数                                             │
│  • 验证安全机制（Token、RLS、审计）                                           │
│  时间：2-3 周                                                                │
│                                                                             │
│                              ▼                                              │
│                                                                             │
│  【第 2 阶段：成长期 场景孵化】                                                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━                                                  │
│  目标：从"被动查数"升级到"高级分析"                                           │
│  做法：                                                                      │
│  • 分析第 1 阶段用户历史聊天记录                                              │
│  • 发现高频查询模式（如利润+不良率联动查询）                                    │
│  • 封装为场景化工具：                                                         │
│    - "资产质量与效益联动分析"                                                 │
│    - "盈利能力同环比分析"                                                     │
│    - "风险预警指标看板"                                                       │
│  时间：1-2 个月                                                              │
│                                                                             │
│                              ▼                                              │
│                                                                             │
│  【第 3 阶段：成熟期 数字分身】                                                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━                                                  │
│  目标：常驻后台的主动"财务哨兵"                                               │
│  做法：                                                                      │
│  • 接入全量数仓                                                               │
│  • AI 定时自动巡检                                                            │
│  • 发现指标异常波动主动推送                                                   │
│  • 生成根因分析报告                                                           │
│  时间：3-6 个月                                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 各阶段里程碑

| 阶段 | 里程碑 | 验收标准 |
|------|--------|----------|
| **MVP** | 打通闭环 | 用户可通过自然语言查询 10+ 个核心指标 |
| **成长期** | 场景封装 | 3+ 个场景化分析工具上线，用户满意度 > 80% |
| **成熟期** | 主动预警 | 异常指标自动推送，准确率 > 90% |

---

## 9. 实施检查清单

### 9.1 技术层面

| # | 检查项 | 状态 | 负责人 |
|---|--------|------|--------|
| 1 | 现有原型 Sidecar 架构复用 | ✅ 可直接复用 | - |
| 2 | Token 机制（Access/Refresh） | ✅ 已实现 | - |
| 3 | IDOR 防护（user_id 上下文） | ✅ 已实现 | - |
| 4 | 字典端点实现 | 📝 待开发 | 后端 |
| 5 | 查询端点实现 | 📝 待开发 | 后端 |
| 6 | RLS 行级安全实现 | 📝 待开发 | 后端 |
| 7 | 审计日志中间件 | 📝 待开发 | 后端 |
| 8 | 数据库只读账号配置 | 📝 待配置 | DBA |
| 9 | MCP Remote 工具定义 | 📝 待开发 | 后端 |

### 9.2 业务层面

| # | 检查项 | 状态 | 负责人 |
|---|--------|------|--------|
| 1 | 确定 3-5 张核心表 | 📝 待确认 | 业务 |
| 2 | 梳理 10-20 个高频指标 | 📝 待确认 | 业务 |
| 3 | 指标同义词/别名收集 | 📝 待确认 | 业务 |
| 4 | 机构代码与 user_id 映射 | 📝 待确认 | 业务 |
| 5 | 指标计算公式确认 | 📝 待确认 | 业务 |

### 9.3 合规层面

| # | 检查项 | 状态 | 负责人 |
|---|--------|------|--------|
| 1 | 审计日志方案审批 | 📝 待审批 | 合规 |
| 2 | 数据访问权限确认 | 📝 待确认 | 合规 |
| 3 | 只读账号权限审批 | 📝 待审批 | 安全 |

---

## 10. 下一步行动指南

### 10.1 优先级排序

```
P0（阻塞项）：
├── 业务专家提供指标清单（Excel 格式）
└── 确认机构代码与 user_id 映射关系

P1（核心开发）：
├── 实现 get_finance_dictionary 工具
├── 实现 query_financial_metrics 工具
└── Backend RLS 行级安全实现

P2（增强功能）：
├── 审计日志中间件
├── 错误提示优化
└── 性能监控（查询超时）
```

### 10.2 指标清单模板

为加快进度，请业务专家按以下模板提供指标清单：

| 标准字段名 | 中文显示名 | 分类 | 单位 | 同义词/别名 | 含义说明 | 计算公式 |
|------------|------------|------|------|-------------|----------|----------|
| NET_PROFIT | 净利润 | 盈利能力 | 万元 | 纯利润、税后利润 | 扣除所有成本后的利润 | 营业收入 - 成本 - 税费 |
| NPL_RATIO | 不良贷款率 | 风险指标 | % | 不良率、NPL | 不良贷款占比 | 不良贷款/贷款总额 |
| ... | ... | ... | ... | ... | ... | ... |

### 10.3 准备就绪后

准备好指标清单后，可立即开始：

1. **生成字典配置** - 将 Excel 转换为 `dictionary.py`
2. **实现字典端点** - 静态返回，无需数据库
3. **实现查询端点** - 参数化查询 + RLS
4. **更新 MCP Remote** - 添加工具定义
5. **端到端测试** - OpenClaw 调试验证

---

## 附录A：术语对照表

| 术语 | 英文 | 说明 |
|------|------|------|
| Sidecar 模式 | Sidecar Pattern | 本地代理架构模式 |
| 本地网关 | Local Gateway | 同 Sidecar，强调网关职责 |
| RLS | Row-Level Security | 数据库行级安全 |
| IDOR | Insecure Direct Object Reference | 越权访问漏洞 |
| MVP | Minimum Viable Product | 最小可行产品 |

---

## 附录B：参考资料

- [MCP 工具描述最佳实践](mcp_tool_description_best_practices.md)
- [MCP 安全认证原型文档](mcp_prototype_sidecar.md)
- [MCP 安全方案文档](mcp_security_authentication.md)
- [MCP 官方文档](https://modelcontextprotocol.io/)
