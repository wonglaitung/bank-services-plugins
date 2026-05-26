# 银行财务数字分身 MVP 实施方案

> **版本**：2.0.0
> **最后更新**：2026-05-26
> **适用范围**：银行财务数据仓库安全接入 MCP
> **关键更新**：重构文档架构，与 mcp_prototype_sidecar.md 保持一致

---

## 目录

1. [概述](#1-概述)
2. [架构设计](#2-架构设计)
3. [组件职责](#3-组件职责)
4. [数据流](#4-数据流)
5. [实现细节](#5-实现细节)
6. [配置说明](#6-配置说明)
7. [验证步骤](#7-验证步骤)
8. [Skill 固化查询 SOP](#8-skill-固化查询-sop)
9. [项目分阶段演进路线](#9-项目分阶段演进路线)
10. [实施检查清单](#10-实施检查清单)

---

## 1. 概述

### 1.1 背景

银行财务数据仓库包含大量敏感数据，需要通过安全的方式将核心财务指标暴露给 AI Agent（如 OpenClaw），实现"财务数字分身"功能。

本方案复用现有 **MCP 安全认证原型**，采用 **侧车（Sidecar）模式** 或 **本地网关（Local Gateway）模式**。

这种架构在金融行业处理高敏感数据时是最佳实践，将 MCP 服务器拆分为两个部分，有效隔离"业务逻辑"与"安全校验"。

### 1.2 为什么需要 Sidecar 模式？

传统 MCP 架构存在以下问题：

| 问题 | 说明 |
|------|------|
| **Token 存储风险** | Token 硬编码在配置文件中，容易泄露 |
| **用户编号可控** | 如果工具接受 `user_id` 参数，模型可能被诱导查询他人数据 |
| **无法分层审计** | 模型调用和实际数据查询混在一起 |
| **扩展不灵活** | 每次修改工具都需要重新部署整个服务 |

Sidecar 模式解决了这些问题：

| 优势 | 说明 |
|------|------|
| **Tools 自动发现** | Claude Code 可以自动发现远端服务的所有工具 |
| **安全隔离** | 用户编号和 Token 在本地代理注入，模型无法修改 |
| **灵活扩展** | 添加/修改工具只需改远端服务，无需改本地代理 |
| **透明转发** | 本地代理不感知具体业务，只负责认证注入 |
| **分层审计** | 本地代理记录请求日志，远端记录业务日志 |

### 1.3 Token 机制

采用 **Access Token + Refresh Token** 双 Token 机制：

| Token 类型 | 有效期 | 用途 | 存储 |
|------------|--------|------|------|
| **Access Token** | 15 分钟 | 调用 MCP API | 内存（自动刷新） |
| **Refresh Token** | 7 天（可配置） | 获取新 Access Token | `.mcp.json` 配置 |

**安全优势**：
- Access Token 有效期短，即使泄露风险有限
- Refresh Token 支持吊销，泄露后可立即止损
- 本地代理自动刷新，用户无感知

### 1.4 方案目标

通过 **Sidecar 模式 + AI 语义对齐**，以最低成本实现：

1. **安全接入**：符合银行合规要求的只读数据访问
2. **智能交互**：利用大模型语义能力解决口径模糊问题
3. **快速落地**：复用现有 MCP 安全认证原型，零架构重构

### 1.5 核心设计理念

```
脑力归 AI，视界归权限
```

- AI 负责语义理解、意图识别、口径对齐
- 权限系统负责数据隔离、访问控制、审计追溯

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户本地机器                                    │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐                              │
│  │  Claude Code    │      │  本地代理层      │                              │
│  │  (AI Agent)     │      │  (Local Proxy)  │                              │
│  │                 │      │                 │                              │
│  │                 │      │ ┌─────────────┐ │                              │
│  │                 │      │ │ 环境变量读取 │ │                              │
│  │                 │      │ │ • MCP_REFRESH│ │                              │
│  │                 │      │ │   _TOKEN    │ │                              │
│  │                 │      │ └─────────────┘ │                              │
│  │                 │      │                 │                              │
│  │                 │      │ ┌─────────────┐ │                              │
│  │                 │      │ │Token 刷新   │ │                              │
│  │                 │      │ │ • Access    │ │                              │
│  │                 │      │ │   Token缓存 │ │                              │
│  │                 │      │ │ • 自动刷新  │ │                              │
│  │                 │      │ └─────────────┘ │                              │
│  │                 │      │                 │                              │
│  │                 │      │  职责:          │                              │
│  │  MCP 请求       │      │  • 透传协议     │                              │
│  │  (Stdio)        │      │  • 转发 Token   │                              │
│  │  ───────────────────────▶ • 记录日志     │                              │
│  │                 │      │                 │                              │
│  │                 │      │        │        │                              │
│  │                 │      │        │ HTTPS  │                              │
│  │                 │      │        │ +Token │                              │
│  │                 │      │        ▼        │                              │
│  └─────────────────┘      └─────────┬───────┘                              │
│                                     │                                       │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │
                                      │ HTTPS (加密通信)
                                      │ Authorization: Bearer <加密Token>
                                      │ （Token内含 user_id + expires_at）
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              公司服务器                                      │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐      ┌───────────────────┐   │
│  │  MCP 远端服务   │      │  后台 API       │      │  财务数仓          │   │
│  │                 │      │                 │      │                   │   │
│  │  职责:          │      │  职责:          │      │  • 3-5 张核心表   │   │
│  │  • 定义 Tools   │      │  • 字典端点     │      │  • 只读账号        │   │
│  │  • 解密 Token   │◀────▶│  • 查询端点     │──────▶  • 参数化查询      │   │
│  │  • 验证有效期   │      │  • RLS 行级安全 │      │                   │   │
│  │  • 审计日志     │      │  • 业务逻辑     │      │                   │   │
│  │                 │      │                 │      │                   │   │
│  └─────────────────┘      └─────────────────┘      └───────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 MCP 协议透传模式

本地代理作为 MCP 协议的透明转发层：

```
Claude Code ◀──Stdio──▶ 本地代理 ◀──HTTPS──▶ 远端 MCP 服务
    │                        │                      │
    │    MCP 协议 (JSON-RPC)  │     HTTP + Token    │
    │                        │                      │
    │  tools/list ──────────────────────────────────▶ 定义在远端
    │  tools/call ──────────────────────────────────▶ 执行在远端
    │                        │                      │
    │                        │  自动注入:           │
    │                        │  • Authorization     │
    │                        │    (加密Token)       │
```

**关键设计**：
- 本地代理**透传** MCP JSON-RPC 协议，不解析业务内容
- 用户身份封装在**加密 Token** 中，本地代理无法查看
- 远端服务解密 Token 获取 `user_id` 和 `expires_at`
- 修改/添加工具只需改远端服务，**无需改本地代理**

### 2.3 与现有原型的复用关系

| 现有原型组件 | MVP 复用情况 | 说明 |
|--------------|--------------|------|
| `local_proxy/main.py` | ✅ 直接复用 | Token 自动刷新逻辑无需修改 |
| `mcp_remote/main.py` | ✅ 扩展复用 | 新增财务工具定义 |
| `backend_api/main.py` | 🔄 重构 | 新增财务 API 路由 |
| Token 生成工具 | ✅ 直接复用 | 无需修改 |
| 加密/解密模块 | ✅ 直接复用 | AES-256-GCM |

---

## 3. 组件职责

### 3.1 职责划分表

| 组件 | 职责 | 添加 Tools 时是否需要修改 |
|------|------|---------------------------|
| **本地代理** | • 从环境变量读取加密 Token<br>• 透传 MCP JSON-RPC 协议<br>• 在每个请求中自动注入 Authorization Header<br>• 记录本地调用日志 | ❌ **无需修改** |
| **远端 MCP 服务** | • 定义所有 Tools<br>• 解密 Token 获取用户编号和有效期<br>• 验证有效期<br>• 传递 user_id 到后台 API<br>• 记录审计日志 | ✅ **需要修改** |
| **后台 API** | • 提供财务字典端点<br>• 提供财务查询端点<br>• 执行业务逻辑（权限检查、RLS、数据验证等）<br>• 不感知用户身份（由远端服务传递 user_id） | 视业务需求 |

### 3.2 各组件详细职责

#### 本地代理层 (Local Proxy)

```
输入: Claude Code 的 MCP JSON-RPC 请求 (Stdio)
处理:
  1. 读取环境变量 MCP_REFRESH_TOKEN（Refresh Token）
  2. 调用远端 /auth/refresh 获取 Access Token
  3. 缓存 Access Token（有效期 15 分钟）
  4. Access Token 过期时自动刷新
  5. 在 HTTP Header 中添加:
     - Authorization: Bearer <Access Token>
  6. 通过 HTTPS 转发到远端服务
  7. 记录请求日志（可选）
输出: 远端服务的响应
```

#### 远端 MCP 服务

```
输入: 来自本地代理的 HTTPS 请求
处理:
  1. 从 Authorization Header 提取加密 Token
  2. AES-256-GCM 解密 Token
  3. 验证 Token 类型（必须是 Access Token）
  4. 验证有效期（expires_at）
  5. 提取 user_id，验证格式（必须为9位数字）
  6. 将用户编号存入上下文 (ContextVar)
  7. 解析 MCP JSON-RPC 请求
  8. 执行对应的 Tool
  9. Tool 从上下文获取用户编号，调用后台 API
  10. 记录审计日志
输出: Tool 执行结果

关键原则：
- mcp_remote 只传递 user_id，不做业务逻辑判断（如权限检查）
- 业务逻辑（权限验证、数据验证、RLS 等）由 backend_api 负责
- mcp_remote 透传 backend_api 的响应结果
```

**新增端点**：

| 端点 | 用途 |
|------|------|
| `/auth/refresh` | 使用 Refresh Token 获取新 Access Token |
| `/auth/revoke` | 吊销 Refresh Token |

#### 后台 API

```
输入: HTTP 请求 (用户编号在 Header 或 URL 中)
处理:
  1. 验证用户编号格式
  2. 获取机构代码（用于 RLS）
  3. 执行业务逻辑：
     - 字典端点：返回静态财务指标字典
     - 查询端点：参数化查询 + RLS 过滤
  4. 返回结果
输出: 财务数据 JSON
```

### 3.3 职责分离原则

**关键设计**：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         职责分离原则                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  mcp_remote（MCP 服务层）：                                                   │
│  ├── 只负责：Token 解密、身份验证、工具声明、审计日志                           │
│  ├── 只传递 user_id 给 backend_api                                          │
│  └── 不做任何业务逻辑判断（如权限检查、数据验证）                               │
│                                                                             │
│  backend_api（业务逻辑层）：                                                  │
│  ├── 负责：业务逻辑、权限检查、数据验证、RLS 实现                              │
│  ├── 接收 user_id，执行业务判断                                              │
│  └── 返回业务处理结果（成功/失败）                                            │
│                                                                             │
│  优势：                                                                      │
│  • 单一职责：每层只做一件事                                                   │
│  • 易于测试：业务逻辑与认证逻辑分离                                           │
│  • 安全审计：权限检查集中在一处                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据流

### 4.1 完整请求流程

```
1. Claude Code 发起请求
   │
   │  MCP JSON-RPC:
   │  {
   │    "jsonrpc": "2.0",
   │    "method": "tools/call",
   │    "params": {"name": "get_finance_dictionary", "arguments": {}},
   │    "id": 1
   │  }
   │
   ▼
2. 本地代理接收 (Stdio)
   │
   │  读取环境变量:
   │  - MCP_REFRESH_TOKEN = "TOJvJYpY..." (加密Token)
   │
   │  获取 Access Token（自动刷新）:
   │  - 调用 /auth/refresh
   │  - 缓存 Access Token
   │
   │  构造 HTTP 请求:
   │  POST /mcp
   │  Headers:
   │    Authorization: Bearer <Access Token>
   │    Content-Type: application/json
   │  Body: (原始 MCP 请求)
   │
   ▼
3. 远端 MCP 服务接收 (HTTPS)
   │
   │  解密 Token:
   │  - AES-256-GCM 解密
   │  - 提取: user_id = "000000001"
   │  - 提取: expires_at = "2026-05-25T18:00:00Z"
   │  - 验证有效期 ✓
   │  - 验证 user_id 格式 ✓
   │
   │  注入上下文: current_user_id = "000000001"
   │
   │  执行 Tool: get_finance_dictionary()
   │
   ▼
4. Tool 执行
   │
   │  user_id = current_user_id.get()  // "000000001"
   │  调用后台 API: GET http://localhost:8000/api/finance/dictionary
   │  Header: X-User-ID: 000000001
   │
   ▼
5. 后台 API 返回
   │
   │  {
   │    "metrics": [
   │      {"standard_name": "NET_PROFIT", "display_name": "净利润", ...}
   │    ]
   │  }
   │
   ▼
6. 远端服务返回给本地代理
   │
   │  MCP 响应:
   │  {
   │    "jsonrpc": "2.0",
   │    "result": {"metrics": [...]},
   │    "id": 1
   │  }
   │
   ▼
7. 本地代理返回给 Claude Code (Stdio)
   │
   │  透传响应
   │
   ▼
8. Claude Code 显示结果
```

**安全关键点**：
- 用户身份封装在加密 Token 中，本地代理无法查看或修改
- 有效期由 Token 内部控制，无法绕过
- 本地代理只负责转发，不知道当前用户是谁

### 4.2 添加新工具的流程

只需要修改**远端 MCP 服务**：

```python
# mcp_remote/main.py - 添加新工具

@mcp.tool()
@secure_api_call
async def get_finance_dictionary() -> dict:
    """
    获取财务指标元数据字典。

    当用户询问"有哪些财务指标"、"能查什么数据"、"指标列表"、"财务科目"
    或"支持查询哪些数据"时调用此工具。

    返回内容：
    - metrics: 指标列表
    - dimensions: 支持的查询维度

    此工具为只读查询，不接受任何参数。
    """
    user_id = current_user_id.get()  # 从上下文获取用户编号

    # 调用后台 API，透传响应
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/finance/dictionary",
            headers={"X-User-ID": user_id}
        )
        response.raise_for_status()
        return response.json()
```

本地代理**无需任何修改**，Claude Code 会自动发现新工具。

---

## 5. 实现细节

### 5.1 目录结构

```
prototype/
├── README.md                    # 使用说明
├── start_all.sh                 # 启动脚本（启动后台API + 远端服务）
│
├── backend_api/                 # 后台 API
│   ├── main.py                  # FastAPI 后台服务 (端口 8000)
│   ├── routers/
│   │   └── finance.py           # 财务 API 路由
│   ├── config/
│   │   └── dictionary.py        # 静态字典配置
│   ├── middleware/
│   │   └── audit.py             # 审计中间件
│   ├── users.json               # 用户数据（原型）
│   └── requirements.txt         # 依赖: fastapi, uvicorn
│
├── mcp_remote/                  # MCP 远端服务
│   ├── main.py                  # MCP Server (HTTPS, 端口 8001)
│   └── requirements.txt         # 依赖: fastapi, uvicorn, mcp, httpx
│
├── local_proxy/                 # 本地代理层
│   ├── main.py                  # 本地 MCP 代理 (Stdio)
│   └── requirements.txt         # 依赖: mcp, httpx
│
└── tools/
    └── generate_token.py        # Token 生成工具
```

### 5.2 后台 API 代码

**`prototype/backend_api/main.py`**:

```python
"""
后台 API

提供财务字典和查询接口，执行业务逻辑（权限检查、RLS 等）。
用户编号由调用方（远端 MCP 服务）传递。
"""

from fastapi import FastAPI, HTTPException, Header
from typing import Optional
import json
import os

app = FastAPI(title="财务后台 API")

# 加载模拟用户数据
DATA_FILE = os.path.join(os.path.dirname(__file__), "users.json")
with open(DATA_FILE, encoding="utf-8") as f:
    USERS = json.load(f)

# 用户-机构映射
USER_BRANCH_MAPPING = {
    "000000001": "BR001",
    "000000002": "BR001",
    "000000003": "BR002",
}


@app.get("/api/finance/dictionary")
async def get_finance_dictionary():
    """
    获取财务指标元数据字典

    纯静态返回，无需数据库查询。
    """
    from .config.dictionary import FINANCE_DICTIONARY
    return FINANCE_DICTIONARY


@app.get("/api/finance/query")
async def query_finance_metrics(
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
    from .config.dictionary import FINANCE_DICTIONARY, ALLOWED_METRICS

    # 1. 验证用户编号
    if not x_user_id or not x_user_id.isdigit() or len(x_user_id) != 9:
        raise HTTPException(400, "用户编号格式错误")

    # 2. 白名单验证
    if metric not in ALLOWED_METRICS:
        raise HTTPException(400, f"不支持的指标: {metric}")

    # 3. 获取机构代码（RLS）
    branch_id = USER_BRANCH_MAPPING.get(x_user_id, "BR000")

    # 4. 执行参数化查询
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

    安全措施：
    - 参数化查询防止 SQL 注入
    - RLS 强制过滤 branch_id
    """
    # 参数化查询模板
    query = """
        SELECT year, quarter, month, metric_value as value
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

    query += " ORDER BY year DESC, quarter DESC, month DESC LIMIT 1000"

    # TODO: 执行实际数据库查询
    # results = await db.fetch_all(query, params)

    # 模拟返回
    return [{"period": "2025", "value": 125000.00}]


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**`prototype/backend_api/config/dictionary.py`**:

```python
"""
财务指标字典配置

由业务专家维护，技术门槛低。
"""

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

# 指标白名单
ALLOWED_METRICS = {m["standard_name"] for m in FINANCE_DICTIONARY["metrics"]}
```

### 5.3 远端 MCP 服务代码

**关键部分**（完整代码复用 `prototype/mcp_remote/main.py`）：

```python
"""
远端 MCP 服务

提供真正的 MCP 服务，定义所有 Tools。
从加密 Token 中解密获取用户编号，用于数据查询。

关键安全原则：
- Tools 不接受 user_id 参数
- 用户编号从加密 Token 解密获取
- 所有数据查询强制使用当前用户编号

Token 机制：
- Access Token: 15 分钟有效期，用于 API 调用
- Refresh Token: 7 天有效期，用于获取新 Access Token
"""

# ... 导入和配置 ...

# 当前用户上下文（每个请求独立）
current_user_id: ContextVar[str] = ContextVar("current_user_id")

# 创建 MCP 服务
mcp = FastMCP("FinanceService")


# ==================== 安全调用装饰器 ====================

def secure_api_call(func):
    """
    安全 API 调用装饰器

    统一处理 API 调用异常，确保返回格式化的错误信息。
    防止原始异常信息暴露给大模型，避免干扰模型判断。
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            logger.error(f"后端接口调用失败: {e.response.status_code}")
            return {"error": f"后端接口调用失败: HTTP {e.response.status_code}"}
        except httpx.ConnectError as e:
            logger.error(f"无法连接后端服务: {e}")
            return {"error": "无法连接后端服务，请检查服务状态"}
        except httpx.TimeoutException as e:
            logger.error(f"后端服务响应超时: {e}")
            return {"error": "后端服务响应超时"}
        except Exception as e:
            logger.error(f"内部处理错误: {e}")
            return {"error": "内部处理错误，请联系管理员"}
    return wrapper


# ==================== MCP Tools 定义 ====================

@mcp.tool()
@secure_api_call
async def get_finance_dictionary() -> dict:
    """
    获取财务指标元数据字典。

    当用户询问"有哪些财务指标"、"能查什么数据"、"指标列表"、"财务科目"
    或"支持查询哪些数据"时调用此工具。

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

    当用户询问具体财务指标数值时调用此工具，如"去年的净利润"、
    "一季度的不良率"、"资产负债情况"。

    参数说明：
    | 参数 | 类型 | 默认值 | 说明 |
    |------|------|--------|------|
    | metric | str | 必需 | 指标名，必须是字典中的 standard_name |
    | year | int | None | 年份（如 2025），不指定则返回最近数据 |
    | quarter | int | None | 季度（1-4），指定后按季度查询 |
    | month | int | None | 月份（1-12），指定后按月查询 |
    | granularity | str | "yearly" | 聚合粒度：yearly/quarterly/monthly |

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

### 5.4 本地代理代码

**关键设计点**（完整代码复用 `prototype/local_proxy/main.py`）：

| 设计 | 说明 |
|------|------|
| **TokenRefreshManager** | 管理 Refresh Token，自动获取和刷新 Access Token |
| **Access Token 缓存** | 缓存 Access Token，过期前 1 分钟自动刷新 |
| **Server 实例** | 使用 `mcp.server.Server` 创建真正的 MCP 服务器 |
| **list_tools 处理器** | 从远端获取工具列表并转换为 `Tool` 对象 |
| **call_tool 处理器** | 转发工具调用到远端，返回 `TextContent` 结果 |
| **兼容旧配置** | 支持 `MCP_AUTH_TOKEN` 环境变量（传统模式） |

---

## 6. 配置说明

### 6.1 Claude Code 配置

MCP 配置文件位置：

| 位置 | 说明 | 优先级 |
|------|------|--------|
| 项目目录 `.mcp.json` | 项目级别配置，与团队共享 | 高 |
| 用户目录 `~/.claude/mcp.json` | 用户级别配置，仅本机有效 | 中 |

**推荐使用项目级配置**，在项目根目录创建 `.mcp.json` 文件：

```json
{
  "mcpServers": {
    "finance-proxy": {
      "command": "python",
      "args": ["/data/bank-services-plugins/prototype/local_proxy/main.py"],
      "env": {
        "REMOTE_MCP_URL": "http://localhost:8001",
        "MCP_REFRESH_TOKEN": "<使用 prototype/tools/generate_token.py 生成>"
      }
    }
  }
}
```

**注意**：
- `args` 中的路径必须使用**绝对路径**
- `MCP_REFRESH_TOKEN` 使用 `prototype/tools/generate_token.py` 生成
- 用户身份封装在 Refresh Token 中，无需单独配置 `MCP_USER_ID`
- 兼容旧配置：可使用 `MCP_AUTH_TOKEN`（传统模式，无自动刷新）

### 6.2 环境变量说明

| 变量名 | 说明 | 示例 | 必需 |
|--------|------|------|------|
| `REMOTE_MCP_URL` | 远端 MCP 服务地址 | `http://localhost:8001` | ✅ |
| `MCP_REFRESH_TOKEN` | Refresh Token（推荐） | 使用 `generate_token.py` 生成 | ✅ |
| `MCP_AUTH_TOKEN` | 传统 Token（兼容旧配置） | 使用 `generate_token.py` 生成 | ⚠️ |

### 6.3 远端服务配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BACKEND_API_URL` | 后台 API 地址 | `http://localhost:8000` |
| `TOKEN_KEY` | AES-256 加密密钥（Base64） | 测试密钥 |

### 6.4 Token 生成

使用 `prototype/tools/generate_token.py` 生成 Access Token 和 Refresh Token：

```bash
# 生成密钥（首次使用）
python prototype/tools/generate_token.py --generate-key

# 生成 Token 对（Refresh Token 有效 7 天）
python prototype/tools/generate_token.py --user-id 000000001 --refresh-expires 7
```

**参数说明**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--generate-key` | 生成新的 AES-256 密钥 | - |
| `--show-key` | 显示当前密钥（Base64） | - |
| `--user-id` | 用户编号（9位数字） | 必需 |
| `--refresh-expires` | Refresh Token 有效期（**天**） | 7 |

### 6.5 密钥管理

#### 密钥文件位置

密钥存储在：`prototype/tools/.token_key`

```bash
# 查看密钥
python prototype/tools/generate_token.py --show-key
```

#### 密钥配置对照表

| 组件 | 是否需要密钥 | 配置方式 |
|------|--------------|----------|
| `generate_token.py` | ✅ 需要 | 自动读取 `.token_key` 文件 |
| 本地代理 | ❌ 不需要 | 只转发 Token，不解密 |
| 远端服务 | ✅ 需要 | 设置 `TOKEN_KEY` 环境变量 |

```bash
# 启动远端服务时设置密钥
TOKEN_KEY=6Hd+908eMNP0T/4CmFKxdpkHI3HaMrINtej6VCcpx7Y= python prototype/mcp_remote/main.py
```

#### 密钥安全注意事项

| 注意事项 | 说明 |
|----------|------|
| **密钥文件权限** | `.token_key` 应设置为 600（仅所有者可读写） |
| **密钥不要提交** | 添加到 `.gitignore`，避免泄露 |
| **生产环境** | 从安全配置中心或环境变量读取，不使用文件 |
| **密钥轮换** | 定期更换密钥，重新生成所有 Token |

---

## 7. 验证步骤

### 7.1 启动服务

**方式一：使用启动脚本（推荐）**

```bash
# 一键启动所有服务
cd prototype
./start_all.sh
```

**方式二：手动启动**

```bash
# 0. 生成密钥（首次使用）
python prototype/tools/generate_token.py --generate-key

# 1. 启动后台 API (端口 8000)
cd prototype/backend_api
pip install -r requirements.txt
python main.py

# 2. 启动远端 MCP 服务 (端口 8001)
cd prototype/mcp_remote
pip install -r requirements.txt
TOKEN_KEY=$(base64 -w 0 ../tools/.token_key) python main.py

# 3. 配置 Claude Code
# 添加本地代理到 MCP 配置

# 4. 重启 Claude Code
# 本地代理会自动启动
```

### 7.2 服务健康检查

```bash
# 测试后台 API 健康检查
curl -s http://localhost:8000/health
# 预期返回: {"status":"ok"}

# 测试远端 MCP 服务健康检查
curl -s http://localhost:8001/health
# 预期返回: {"status":"ok"}
```

### 7.3 后台 API 测试

```bash
# 测试字典端点
curl -s http://localhost:8000/api/finance/dictionary | python3 -m json.tool

# 测试查询端点
curl -s "http://localhost:8000/api/finance/query?metric=NET_PROFIT&year=2025" \
  -H "X-User-ID: 000000001" | python3 -m json.tool
```

### 7.4 远端 MCP 服务测试

```bash
# 使用加密 Token
TOKEN="<使用 generate_token.py 生成>"

# 测试 tools/list（工具列表）
curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}' | python3 -m json.tool

# 测试 tools/call（工具调用）
curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_finance_dictionary", "arguments": {}}, "id": 2}'
```

### 7.5 验证安全机制

| 验证项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| Token 解密验证 | 使用正确密钥启动远端服务 | Token 正确解密，返回用户信息 |
| Token 过期验证 | 使用过期 Token | 返回 401 "Token 已过期" |
| Token 格式验证 | 使用无效 Base64 Token | 返回 401 "Token 格式错误" |
| 缺少 Token | 不传 Authorization Header | 返回 401 "缺少认证 Token" |
| Tools 自动发现 | 在 Claude Code 中查看可用工具 | 显示远端服务定义的所有工具 |

### 7.6 验证添加工具无需修改代理

1. 在远端服务中添加新工具
2. 重启远端服务
3. 在 Claude Code 中查看工具列表
4. 新工具自动出现，无需修改本地代理

---

## 8. Skill 固化查询 SOP

### 8.1 问题背景

AI Agent（如 OpenClaw）的系统提示词由厂商控制，用户无法自定义。这导致：

| 问题 | 说明 |
|------|------|
| **查询流程不可控** | Agent 可能跳过字典查询直接尝试调用查询工具 |
| **错误处理不一致** | 无法统一引导 Agent 进行友好的异常提示 |
| **语义匹配不稳定** | 不同 Agent 版本对同义词匹配策略可能不同 |

### 8.2 解决方案：Skill 固化 SOP

通过 Claude Code 的 **Skill 机制**，将财务查询的 SOP（标准操作流程）固化到 SKILL.md 文档中。

**核心理念**：Skill 不需要编写 Python 脚本，只需通过 SKILL.md 文档固化流程，实际数据查询通过调用 MCP 工具完成。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Skill 固化 SOP 原理                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  传统方式（不可控）：                                                         │
│  ┌─────────────────┐                                                        │
│  │ AI Agent        │  ← 系统提示词不可修改                                    │
│  │ 自由决策        │  ← 查询流程不稳定                                        │
│  └─────────────────┘                                                        │
│                                                                             │
│  Skill 方式（可控）：                                                         │
│  ┌─────────────────┐      ┌─────────────────┐                              │
│  │ 用户输入        │ ───▶ │ SKILL.md        │                              │
│  │ "查去年的利润"  │      │ (固化 SOP)      │                              │
│  └─────────────────┘      └────────┬────────┘                              │
│                                    │                                        │
│                                    ▼                                        │
│                           ┌─────────────────┐                               │
│                           │ 1. 调用字典工具  │                               │
│                           │ 2. 本地语义匹配  │                               │
│                           │ 3. 调用查询工具  │                               │
│                           │ 4. 格式化输出    │                               │
│                           └─────────────────┘                               │
│                                                                             │
│  核心优势：流程固化、错误处理统一、输出格式标准化                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Skill 目录结构

```
.claude/skills/finance-query/
└── SKILL.md                    # 技能文档（唯一必需文件）
```

**说明**：
- 只需要 SKILL.md 文档即可固化 SOP
- 无需 Python 脚本，数据查询通过 MCP 工具完成
- Claude Code 读取 SKILL.md 后自动按流程执行

### 8.4 SKILL.md 完整内容

```markdown
# 财务数据查询 Skill

## 功能描述

帮助用户查询银行财务数据，自动完成语义匹配和数据格式化。

## 使用场景

当用户需要查询财务指标时，如：
- "去年的净利润是多少？"
- "一季度的不良贷款率"
- "最近三年的资产总额变化"

## 执行流程

### 步骤 1：获取指标字典

调用 MCP 工具 `get_finance_dictionary`，获取所有支持的指标列表。

### 步骤 2：语义匹配

根据用户输入的关键词，在字典的 synonyms 字段中查找匹配项：

| 用户输入 | 匹配字段 | standard_name |
|----------|----------|---------------|
| "纯利润" | synonyms | NET_PROFIT |
| "不良率" | synonyms | NPL_RATIO |
| "总资产" | synonyms | TOTAL_ASSETS |

**匹配策略**：
1. 精确匹配 synonyms 中的任一别名
2. 模糊匹配（相似度 > 0.8）
3. 无法匹配时，提示用户可用的指标列表

### 步骤 3：调用查询工具

使用匹配到的 `standard_name` 调用 `query_financial_metrics` 工具。

### 步骤 4：格式化输出

将返回的数据格式化为易读的报告：

```
📊 财务指标查询结果

指标：净利润（NET_PROFIT）
时间：2025 年
单位：万元

| 时期 | 数值 |
|------|------|
| 2025 | 125,000.00 |

数据来源：财务数仓（自动过滤当前用户所属机构）
查询时间：2026-05-26 10:30:00
```

### 步骤 5：异常处理

**情况 1：指标无法匹配**

```
❌ 无法识别的指标："报销差旅费"

目前支持的财务指标包括：

📈 盈利能力：
  • 净利润（纯利润、税后利润）
  • 净利息收入（息差收入）

📊 规模指标：
  • 资产总额（总资产）

⚠️ 风险指标：
  • 不良贷款率（不良率、NPL）
  • 资本充足率（CAR）

您可以换个说法，例如："去年的净利润是多少？"
```

**情况 2：无数据**

```
⚠️ 查询成功，但未找到数据

查询条件：
  • 指标：净利润
  • 年份：2025
  • 季度：3

可能原因：
  1. 当前机构暂无该时期数据
  2. 数据尚未入库

建议：尝试查询其他时间段或指标
```

## 调用方式

### 命令行

```bash
# 交互式查询
/finance-query

# 直接传入问题
/finance-query "去年的净利润是多少？"
```

### 自然语言触发

当用户提到财务相关问题时，Claude Code 自动识别并调用此 Skill。

## 注意事项

- 此 Skill 仅支持查询，不支持修改数据
- 所有查询自动应用 RLS 行级安全过滤
- 查询结果仅显示当前用户所属机构的数据
```

### 8.5 Skill 与 MCP 工具的关系

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Skill 与 MCP 工具分层                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Skill 层（业务编排）                                                 │   │
│  │                                                                     │   │
│  │  finance-query Skill (SKILL.md)                                     │   │
│  │  • 接收用户自然语言输入                                              │   │
│  │  • 指引 Claude Code 调用 MCP 工具获取字典和数据                       │   │
│  │  • 本地语义匹配和结果格式化                                          │   │
│  │  • 统一的错误处理和用户引导                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      │ 调用                                 │
│                                      ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ MCP 工具层（原子能力）                                               │   │
│  │                                                                     │   │
│  │  get_finance_dictionary()   query_financial_metrics()              │   │
│  │  • 获取指标字典              • 执行参数化查询                        │   │
│  │  • 纯数据返回                • RLS 安全过滤                          │   │
│  │  • 不含业务逻辑              • 不含业务逻辑                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  分层原则：                                                                  │
│  • MCP 工具提供原子能力，保持简单、可复用                                     │
│  • Skill 通过 SKILL.md 固化流程，处理用户体验                                  │
│  • Skill 无需编写代码，只需文档化流程                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.6 语义匹配关键逻辑

Claude Code 执行 Skill 时，按以下逻辑进行语义匹配：

```python
# 语义匹配伪代码（由 Claude Code 内部执行）

def match_metric(keyword: str, dictionary: dict) -> str | None:
    """
    匹配用户关键词到标准指标名

    Args:
        keyword: 用户输入的关键词（如"纯利润"）
        dictionary: get_finance_dictionary() 返回的字典

    Returns:
        匹配到的 standard_name，未匹配返回 None
    """
    keyword_lower = keyword.lower()

    # 构建同义词索引
    synonym_index = {}
    for metric in dictionary["metrics"]:
        standard_name = metric["standard_name"]
        # 标准名称
        synonym_index[standard_name.lower()] = standard_name
        # 显示名称
        synonym_index[metric["display_name"].lower()] = standard_name
        # 同义词
        for syn in metric.get("synonyms", []):
            synonym_index[syn.lower()] = standard_name

    # 1. 精确匹配
    if keyword_lower in synonym_index:
        return synonym_index[keyword_lower]

    # 2. 模糊匹配（相似度 > 0.8）
    best_match = None
    best_score = 0
    for syn, standard_name in synonym_index.items():
        score = similarity(keyword_lower, syn)  # 如 difflib.SequenceMatcher
        if score > best_score and score >= 0.8:
            best_score = score
            best_match = standard_name

    return best_match
```

### 8.7 输出格式化关键逻辑

```python
# 输出格式化伪代码（由 Claude Code 内部执行）

def format_result(data: dict) -> str:
    """
    格式化查询结果为易读报告

    Args:
        data: query_financial_metrics() 返回的数据

    Returns:
        格式化的 Markdown 文本
    """
    lines = []
    lines.append("📊 财务指标查询结果")
    lines.append("")
    lines.append(f"**指标**：{data['metric_name']}（{data['metric']}）")
    lines.append(f"**单位**：{data['unit']}")
    lines.append(f"**机构**：{data['branch_id']}")
    lines.append("")

    # 数据表格
    rows = data.get("data", [])
    if rows:
        lines.append("| 时期 | 数值 |")
        lines.append("|------|------|")
        for row in rows:
            period = row.get("period", "-")
            value = row.get("value", 0)
            if isinstance(value, (int, float)):
                value_str = f"{value:,.2f}"
            else:
                value_str = str(value)
            lines.append(f"| {period} | {value_str} |")
    else:
        lines.append("*暂无数据*")

    lines.append("")
    lines.append(f"*查询时间：{current_time()}*")

    return "\n".join(lines)
```

### 8.8 Skill 开发检查清单

| # | 检查项 | 说明 |
|---|--------|------|
| 1 | SKILL.md 文档完整 | 包含功能描述、使用场景、执行流程 |
| 2 | 执行流程步骤清晰 | 每步说明调用哪个 MCP 工具 |
| 3 | 异常处理说明完整 | 无法匹配时提供可用指标列表 |
| 4 | 输出格式规范 | 表格清晰、单位明确 |
| 5 | 自然语言触发词明确 | 帮助 Claude Code 识别何时调用 |

---

## 9. 项目分阶段演进路线

### 9.1 演进路线图

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

### 9.2 各阶段里程碑

| 阶段 | 里程碑 | 验收标准 |
|------|--------|----------|
| **MVP** | 打通闭环 | 用户可通过自然语言查询 10+ 个核心指标 |
| **成长期** | 场景封装 | 3+ 个场景化分析工具上线，用户满意度 > 80% |
| **成熟期** | 主动预警 | 异常指标自动推送，准确率 > 90% |

---

## 10. 实施检查清单

### 10.1 技术层面

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
| 10 | finance-query Skill | 📝 待开发 | 开发 |

### 10.2 业务层面

| # | 检查项 | 状态 | 负责人 |
|---|--------|------|--------|
| 1 | 确定 3-5 张核心表 | 📝 待确认 | 业务 |
| 2 | 梳理 10-20 个高频指标 | 📝 待确认 | 业务 |
| 3 | 指标同义词/别名收集 | 📝 待确认 | 业务 |
| 4 | 机构代码与 user_id 映射 | 📝 待确认 | 业务 |
| 5 | 指标计算公式确认 | 📝 待确认 | 业务 |

### 10.3 合规层面

| # | 检查项 | 状态 | 负责人 |
|---|--------|------|--------|
| 1 | 审计日志方案审批 | 📝 待审批 | 合规 |
| 2 | 数据访问权限确认 | 📝 待确认 | 合规 |
| 3 | 只读账号权限审批 | 📝 待审批 | 安全 |

### 10.4 优先级排序

```
P0（阻塞项）：
├── 业务专家提供指标清单（Excel 格式）
└── 确认机构代码与 user_id 映射关系

P1（核心开发）：
├── 实现 get_finance_dictionary 工具
├── 实现 query_financial_metrics 工具
├── Backend RLS 行级安全实现
└── 开发 finance-query Skill（固化 SOP）

P2（增强功能）：
├── 审计日志中间件
├── 错误提示优化
└── 性能监控（查询超时）
```

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
