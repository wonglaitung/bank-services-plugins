# 银行财务数字分身 MVP 实施方案

> **版本**：3.1.0
> **最后更新**：2026-05-27
> **适用范围**：银行财务数据仓库安全接入 MCP

---

## 目录

1. [概述](#1-概述)
2. [后台 API 设计](#2-后台-api-设计)
3. [财务指标字典](#3-财务指标字典)
4. [MCP 工具定义](#4-mcp-工具定义)
5. [安全机制](#5-安全机制)
6. [配置与部署](#6-配置与部署)
7. [Skill 固化查询 SOP](#7-skill-固化查询-sop)
8. [大宽表/数据仓库工具设计](#8-大宽表数据仓库工具设计)

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
| Token 生成工具 | ✅ 直接复用 | AES-256-GCM 加密 |

---

## 2. 后台 API 设计

### 2.1 API 端点清单

| 端点 | 方法 | 说明 | 权限 |
|------|------|------|------|
| `/api/finance/dictionary` | GET | 获取财务指标元数据字典 | 所有用户 |
| `/api/finance/query` | GET | 查询财务指标数据 | 所有用户（RLS） |
| `/api/users/me` | GET | 获取当前用户信息 | 所有用户 |
| `/api/users/balance` | GET | 获取当前用户余额 | 所有用户 |
| `/api/admin/users` | GET | 查询所有用户列表 | 仅管理员 |

### 2.2 字典端点

**请求示例**：

```bash
GET /api/finance/dictionary
```

**响应示例**：

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
    },
    {
      "standard_name": "NET_INTEREST_INCOME",
      "display_name": "净利息收入",
      "category": "盈利能力",
      "unit": "万元",
      "description": "利息收入减去利息支出",
      "synonyms": ["利息收入", "息差收入", "净利息"],
      "formula": "利息收入 - 利息支出"
    }
  ],
  "dimensions": [
    {"name": "year", "display_name": "年份", "type": "int"},
    {"name": "quarter", "display_name": "季度", "type": "int", "range": "1-4"},
    {"name": "month", "display_name": "月份", "type": "int", "range": "1-12"},
    {"name": "granularity", "display_name": "聚合粒度", "type": "enum", "values": ["yearly", "quarterly", "monthly"]}
  ]
}
```

### 2.3 查询端点

**请求示例**：

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

**响应示例**：

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

### 2.4 后台 API 核心代码

```python
# backend_api/main.py

from fastapi import FastAPI, HTTPException, Header
from .config.dictionary import FINANCE_DICTIONARY, ALLOWED_METRICS

app = FastAPI(title="财务后台 API")

# 用户-机构映射（RLS）
USER_BRANCH_MAPPING = {
    "000000001": "BR001",
    "000000002": "BR001",
    "000000003": "BR002",
}


@app.get("/api/finance/dictionary")
async def get_finance_dictionary():
    """获取财务指标元数据字典（静态返回）"""
    return FINANCE_DICTIONARY


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

### 2.5 用户信息端点

```python
@app.get("/api/users/me")
async def get_my_info(x_user_id: str = Header(None, alias="X-User-ID")):
    """获取当前用户完整信息"""
    user = USERS_DB.get(x_user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return user


@app.get("/api/users/balance")
async def get_my_balance(x_user_id: str = Header(None, alias="X-User-ID")):
    """获取当前用户账户余额（精简返回）"""
    user = USERS_DB.get(x_user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "balance": user["balance"]
    }
```

### 2.6 管理员端点

```python
from functools import wraps

def require_admin(func):
    """管理员权限装饰器"""
    @wraps(func)
    async def wrapper(*args, x_user_id: str = Header(None, alias="X-User-ID"), **kwargs):
        user = USERS_DB.get(x_user_id)
        if not user or user.get("role") != "admin":
            raise HTTPException(403, "需要管理员权限")
        return await func(*args, x_user_id=x_user_id, **kwargs)
    return wrapper


@app.get("/api/admin/users")
@require_admin
async def list_all_users(x_user_id: str = Header(None, alias="X-User-ID")):
    """
    【管理员权限】查询所有用户列表

    不包含 balance 字段，保护用户财务隐私
    """
    return {
        "total": len(USERS_DB),
        "users": [
            {
                "user_id": u["user_id"],
                "name": u["name"],
                "department": u["department"],
                "role": u["role"]
            }
            for u in USERS_DB.values()
        ]
    }
```

---

## 3. 财务指标字典

### 3.1 字典结构

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

### 3.2 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `standard_name` | str | 标准字段名（用于 API 查询） |
| `display_name` | str | 中文显示名 |
| `category` | str | 指标分类（盈利能力/风险指标/业务指标/规模指标） |
| `unit` | str | 计量单位 |
| `description` | str | 含义说明 |
| `synonyms` | list | 同义词/别名列表（用于语义匹配） |
| `formula` | str | 计算公式 |

---

## 4. MCP 工具定义

### 4.1 工具清单

| 工具名 | 用途 | 权限 |
|--------|------|------|
| `get_finance_dictionary` | 获取财务指标字典 | 所有用户 |
| `query_financial_metrics` | 查询财务指标数据 | 所有用户（RLS） |
| `get_my_info` | 获取当前用户完整信息 | 所有用户 |
| `get_my_balance` | 获取当前用户余额 | 所有用户 |
| `get_my_department` | 获取当前用户部门 | 所有用户 |
| `check_my_permission` | 查询当前用户权限 | 所有用户 |
| `list_all_users` | 查询所有用户列表 | 仅管理员 |

### 4.2 核心工具代码

```python
# mcp_remote/main.py

from contextvars import ContextVar
from mcp.server.fastmcp import FastMCP

current_user_id: ContextVar[str] = ContextVar("current_user_id")
mcp = FastMCP("FinanceService")


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

### 4.3 用户信息工具

```python
@mcp.tool()
async def get_my_info() -> dict:
    """
    获取当前用户的完整个人信息。

    当用户询问"我的信息"、"我是谁"、"我的资料"、"个人信息"或"查看我的账户"时调用此工具。

    返回内容：
    - user_id: 用户编号
    - name: 姓名
    - department: 部门
    - role: 角色(viewer/admin)
    - balance: 账户余额

    此工具不接受任何用户标识参数，身份从认证上下文自动获取。
    仅能查询当前已认证用户的信息，严禁用于尝试获取他人数据。
    """
    user_id = current_user_id.get()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/users/me",
            headers={"X-User-ID": user_id}
        )
        return response.json()


@mcp.tool()
async def get_my_balance() -> dict:
    """
    获取当前用户的账户余额。

    当用户询问"我的余额"、"我还有多少钱"、"账户余额"、"财务状况"、
    "多少钱"或"余额查询"时调用此工具。

    返回内容：
    - user_id: 用户编号
    - name: 姓名
    - balance: 账户余额(数值)

    此工具不接受任何用户标识参数，身份从认证上下文自动获取。
    仅能查询当前已认证用户的余额，严禁用于尝试获取他人数据。
    """
    user_id = current_user_id.get()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/users/balance",
            headers={"X-User-ID": user_id}
        )
        return response.json()


@mcp.tool()
async def get_my_department() -> dict:
    """
    获取当前用户所在的部门信息。

    当用户询问"我的部门"、"我在哪个部门"、"部门信息"、"所属部门"
    或"我是哪个部门的"时调用此工具。

    返回内容：
    - user_id: 用户编号
    - name: 姓名
    - department: 部门名称

    此工具仅返回部门相关数据，不包含余额、角色等其他信息。
    如需完整信息，请使用 get_my_info 工具。
    """
    user_id = current_user_id.get()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/users/department",
            headers={"X-User-ID": user_id}
        )
        return response.json()


@mcp.tool()
async def check_my_permission() -> dict:
    """
    检查当前用户的权限和角色。

    当用户询问"我的权限"、"我能做什么"、"角色信息"、"我的角色"、
    "有什么权限"或"权限查询"时调用此工具。

    返回内容：
    - user_id: 用户编号
    - name: 姓名
    - department: 部门
    - role: 角色(viewer=普通用户,admin=管理员)

    角色说明：
    - viewer: 普通用户，仅能查询自己的数据
    - admin: 管理员，可调用 list_all_users 查询所有用户

    此工具不接受任何用户标识参数，身份从认证上下文自动获取。
    """
    user_id = current_user_id.get()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/users/permission",
            headers={"X-User-ID": user_id}
        )
        return response.json()
```

### 4.4 管理员工具

```python
@mcp.tool()
async def list_all_users() -> dict:
    """
    【管理员权限工具】查询所有用户的基本信息列表。

    仅限 admin 角色的用户才能调用此工具。
    当管理员需要查看"所有用户"、"用户列表"、"有多少用户"、"全部用户"或"用户统计"时调用。

    返回内容：
    - total: 用户总数
    - users: 用户列表，每个用户包含：
        - user_id: 用户编号
        - name: 姓名
        - department: 部门
        - role: 角色

    不包含 balance(余额)字段，保护用户财务隐私。

    权限检查由后台 API 执行，非管理员调用将返回 403 错误。
    如不确定自己的角色，请先调用 check_my_permission 工具查询。
    """
    user_id = current_user_id.get()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/admin/users",
            headers={"X-User-ID": user_id}
        )
        return response.json()
```

---

## 5. 安全机制

### 5.1 安全措施汇总

| 安全措施 | 实现位置 | 说明 |
|----------|----------|------|
| **Token 加密** | 远端 MCP 服务 | AES-256-GCM 加密，本地代理无法解密 |
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
| `TOKEN_KEY` | AES-256 密钥（Base64） | 远端服务 |
| `BACKEND_API_URL` | 后台 API 地址 | 远端服务 |

### 6.4 Token 生成

```bash
# 生成密钥（首次使用）
python prototype/tools/generate_token.py --generate-key

# 生成 Token（Refresh Token 有效 7 天）
python prototype/tools/generate_token.py --user-id 000000001 --refresh-expires 7
```

### 6.5 启动服务

```bash
# 1. 启动后台 API (端口 8000)
python prototype/backend_api/main.py

# 2. 启动远端 MCP 服务 (端口 8001)
TOKEN_KEY=$(base64 -w 0 prototype/tools/.token_key) python prototype/mcp_remote/main.py

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

## 7. Skill 固化查询 SOP

### 7.1 问题背景

AI Agent 的系统提示词由厂商控制，用户无法自定义，导致：

| 问题 | 说明 |
|------|------|
| 查询流程不可控 | Agent 可能跳过字典查询直接调用查询工具 |
| 错误处理不一致 | 无法统一引导 Agent 进行友好的异常提示 |

### 7.2 解决方案

通过 Claude Code 的 **Skill 机制**，将财务查询的 SOP 固化到 SKILL.md 文档中。

**核心理念**：Skill 只需 SKILL.md 文档固化流程，无需编写 Python 脚本。

### 7.3 目录结构

```
.claude/skills/finance-query/
└── SKILL.md                    # 唯一必需文件
```

### 7.4 SKILL.md 内容

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

### 7.5 Skill 与 MCP 工具分层

```
┌─────────────────────────────────────────────────────────────────┐
│  Skill 层（业务编排）                                            │
│  finance-query Skill (SKILL.md)                                 │
│  • 接收用户自然语言输入                                          │
│  • 指引 Claude Code 调用 MCP 工具                               │
│  • 本地语义匹配和结果格式化                                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 调用
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  MCP 工具层（原子能力）                                          │
│  get_finance_dictionary()   query_financial_metrics()          │
│  • 获取指标字典              • 执行参数化查询                    │
│  • 纯数据返回                • RLS 安全过滤                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. 大宽表/数据仓库工具设计

### 8.1 核心挑战

数据仓库大宽表通常包含**大量字段**（50-100+ 列），与简单业务场景不同：

| 挑战 | 说明 |
|------|------|
| **字段过多** | 不可能为每个字段创建单独工具 |
| **查询维度多样** | 用户可能按时间、部门、地区、产品等多维度查询 |
| **聚合需求** | 用户可能需要汇总、统计、排名 |
| **模型认知负担** | 工具描述太长会超出上下文，太短则覆盖不全 |

### 8.2 推荐方案：按业务域拆分工具

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

### 8.3 元数据工具设计

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

### 8.4 示例驱动的描述

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
    │                                 │ filters={"region": "华东",  │
    │                                 │          "month": "latest"} │
    └─────────────────────────────────────────────────────────────┘

    完整字段列表请调用 describe_table("sales_fact") 获取。
    """
```

### 8.5 分页和性能说明

大宽表查询可能返回大量数据，**必须在描述中说明分页机制**：

```python
@mcp.tool()
async def query_fact_table(
    table: str,
    select_fields: list[str],
    filters: dict = None,
    limit: int = 100,    # 默认限制
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

### 8.6 聚合查询工具

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

### 8.7 大宽表工具设计模式

推荐的工具组合：

| 工具类型 | 工具名称 | 用途 |
|----------|----------|------|
| **元数据查询** | `list_tables` | 获取可用表列表 |
| **元数据查询** | `describe_table` | 获取表字段元数据 |
| **明细查询** | `query_fact_table` | 查询明细数据（带分页） |
| **汇总查询** | `query_metrics` | 按维度汇总指标 |
| **聚合查询** | `query_aggregation` | 单值聚合（sum/avg/max/min） |

### 8.8 大宽表工具描述检查清单

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

## 9. 参考资料

- [MCP 安全认证原型文档](mcp_prototype_sidecar.md) - 架构设计详解
- [MCP 安全方案文档](mcp_security_authentication.md) - 安全机制详解
- [MCP 工具描述最佳实践](mcp_tool_description_best_practices.md) - 工具描述规范
- [MCP 官方文档](https://modelcontextprotocol.io/)
