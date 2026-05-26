# 银行财务数字分身 MVP 实施方案

> **版本**：3.0.0
> **最后更新**：2026-05-26
> **适用范围**：银行财务数据仓库安全接入 MCP

---

## 目录

1. [概述](#1-概述)
2. [架构设计](#2-架构设计)
3. [组件职责](#3-组件职责)
4. [实现细节](#4-实现细节)
5. [配置与部署](#5-配置与部署)
6. [Skill 固化查询 SOP](#6-skill-固化查询-sop)
7. [演进路线与检查清单](#7-演进路线与检查清单)

---

## 1. 概述

### 1.1 背景

银行财务数据仓库包含大量敏感数据，需要通过安全的方式将核心财务指标暴露给 AI Agent，实现"财务数字分身"功能。

本方案复用现有 **MCP 安全认证原型**，采用 **Sidecar 模式**，将 MCP 服务器拆分为本地代理和远端服务两部分，有效隔离"业务逻辑"与"安全校验"。

### 1.2 核心设计理念

```
脑力归 AI，视界归权限
```

- **AI 负责**：语义理解、意图识别、口径对齐
- **权限系统负责**：数据隔离、访问控制、审计追溯

### 1.3 Token 机制

采用 **Access Token + Refresh Token** 双 Token 机制：

| Token 类型 | 有效期 | 用途 | 存储 |
|------------|--------|------|------|
| **Access Token** | 15 分钟 | 调用 MCP API | 内存（自动刷新） |
| **Refresh Token** | 7 天（可配置） | 获取新 Access Token | `.mcp.json` 配置 |

**安全优势**：Access Token 有效期短，即使泄露风险有限；Refresh Token 支持吊销。

### 1.4 方案目标

| 目标 | 说明 |
|------|------|
| **安全接入** | 符合银行合规要求的只读数据访问 |
| **智能交互** | 利用大模型语义能力解决口径模糊问题 |
| **快速落地** | 复用现有 MCP 原型，零架构重构 |

### 1.5 与现有原型的复用关系

| 原型组件 | 复用情况 | 说明 |
|----------|----------|------|
| `local_proxy/main.py` | ✅ 直接复用 | Token 自动刷新逻辑 |
| `mcp_remote/main.py` | ✅ 扩展复用 | 新增财务工具定义 |
| `backend_api/main.py` | 🔄 重构 | 新增财务 API 路由 |
| Token 生成工具 | ✅ 直接复用 | AES-256-GCM 加密 |

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户本地机器                                    │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐                              │
│  │  Claude Code    │      │  本地代理        │                              │
│  │  (AI Agent)     │──────▶  (Local Proxy)  │                              │
│  │                 │ Stdio │                 │                              │
│  │                 │       │ • Token 刷新    │                              │
│  │                 │       │ • 协议透传      │                              │
│  └─────────────────┘       └────────┬────────┘                              │
│                                     │                                       │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │ HTTPS + 加密 Token
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              公司服务器                                      │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐      ┌───────────────────┐   │
│  │  MCP 远端服务   │      │  后台 API       │      │  财务数仓          │   │
│  │                 │      │                 │      │                   │   │
│  │  • Token 解密   │◀────▶│  • 字典端点     │──────▶  • 只读账号        │   │
│  │  • 工具定义     │      │  • 查询端点     │      │  • 参数化查询      │   │
│  │  • 身份注入     │      │  • RLS 过滤     │      │                   │   │
│  └─────────────────┘      └─────────────────┘      └───────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 MCP 协议透传模式

```
Claude Code ◀──Stdio──▶ 本地代理 ◀──HTTPS──▶ 远端 MCP 服务
    │                        │                      │
    │  tools/list ──────────────────────────────────▶ 定义在远端
    │  tools/call ──────────────────────────────────▶ 执行在远端
    │                        │                      │
    │                        │  自动注入:           │
    │                        │  Authorization:      │
    │                        │  Bearer <加密Token>  │
```

**关键设计**：
- 本地代理**透传** MCP JSON-RPC 协议，不解析业务内容
- 用户身份封装在**加密 Token** 中，本地代理无法查看
- 修改/添加工具只需改远端服务，**无需改本地代理**

---

## 3. 组件职责

### 3.1 职责划分表

| 组件 | 职责 | 添加工具时 |
|------|------|-----------|
| **本地代理** | 读取 Token、透传协议、自动刷新 | ❌ 无需修改 |
| **远端 MCP 服务** | Token 解密、身份注入、工具定义、审计日志 | ✅ 需要修改 |
| **后台 API** | 业务逻辑、权限检查、RLS、数据查询 | 视需求 |

### 3.2 职责分离原则

```
mcp_remote（MCP 服务层）：
├── 只负责：Token 解密、身份验证、工具声明、审计日志
├── 只传递 user_id 给 backend_api
└── 不做任何业务逻辑判断

backend_api（业务逻辑层）：
├── 负责：业务逻辑、权限检查、数据验证、RLS 实现
├── 接收 user_id，执行业务判断
└── 返回业务处理结果
```

### 3.3 数据流

```
1. Claude Code 发起 MCP 请求
   │
   ▼
2. 本地代理：读取 Refresh Token → 获取 Access Token → 注入 Header
   │
   ▼
3. 远端 MCP 服务：解密 Token → 提取 user_id → 注入 ContextVar
   │
   ▼
4. Tool 执行：从上下文获取 user_id → 调用后台 API
   │
   ▼
5. 后台 API：验证 user_id → 执行 RLS 过滤 → 返回数据
```

---

## 4. 实现细节

### 4.1 目录结构

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

### 4.2 后台 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/finance/dictionary` | GET | 获取财务指标元数据字典（静态） |
| `/api/finance/query` | GET | 查询财务指标数据（参数化 + RLS） |

### 4.3 后台 API 核心代码

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

    # 3. RLS：获取机构代码
    branch_id = USER_BRANCH_MAPPING.get(x_user_id, "BR000")

    # 4. 执行参数化查询（强制过滤 branch_id）
    results = await execute_finance_query(metric, branch_id, year, quarter, month)

    return {
        "metric": metric,
        "branch_id": branch_id,
        "data": results
    }
```

### 4.4 字典配置

```python
# backend_api/config/dictionary.py

FINANCE_DICTIONARY = {
    "metrics": [
        {
            "standard_name": "NET_PROFIT",
            "display_name": "净利润",
            "category": "盈利能力",
            "unit": "万元",
            "synonyms": ["纯利润", "税后利润", "利润总额"],
        },
        {
            "standard_name": "NPL_RATIO",
            "display_name": "不良贷款率",
            "category": "风险指标",
            "unit": "%",
            "synonyms": ["不良率", "NPL"],
        },
        # ... 更多指标
    ],
    "dimensions": [
        {"name": "year", "display_name": "年份", "type": "int"},
        {"name": "quarter", "display_name": "季度", "type": "int", "range": "1-4"},
    ]
}

ALLOWED_METRICS = {m["standard_name"] for m in FINANCE_DICTIONARY["metrics"]}
```

### 4.5 MCP 工具定义

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

    当用户询问"有哪些财务指标"、"能查什么数据"、"指标列表"时调用。

    返回内容：metrics（指标列表）、dimensions（查询维度）

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
    granularity: str = "yearly"
) -> dict:
    """
    查询财务指标数据。

    当用户询问具体财务指标数值时调用，如"去年的净利润"、"一季度的不良率"。

    参数：metric（必需，字典中的 standard_name）、year、quarter、granularity

    安全约束：仅能查询当前用户所属机构的数据，机构代码自动过滤。

    如不确定指标名称，请先调用 get_finance_dictionary 获取字典。
    """
    user_id = current_user_id.get()
    params = {"metric": metric, "granularity": granularity}
    if year:
        params["year"] = year
    if quarter:
        params["quarter"] = quarter

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_API_URL}/api/finance/query",
            params=params,
            headers={"X-User-ID": user_id}
        )
        return response.json()
```

---

## 5. 配置与部署

### 5.1 Claude Code 配置

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

### 5.2 环境变量

| 变量名 | 说明 | 组件 |
|--------|------|------|
| `MCP_REFRESH_TOKEN` | Refresh Token | 本地代理 |
| `REMOTE_MCP_URL` | 远端 MCP 地址 | 本地代理 |
| `TOKEN_KEY` | AES-256 密钥（Base64） | 远端服务 |
| `BACKEND_API_URL` | 后台 API 地址 | 远端服务 |

### 5.3 Token 生成

```bash
# 生成密钥（首次使用）
python prototype/tools/generate_token.py --generate-key

# 生成 Token（Refresh Token 有效 7 天）
python prototype/tools/generate_token.py --user-id 000000001 --refresh-expires 7
```

### 5.4 启动服务

```bash
# 1. 启动后台 API (端口 8000)
python prototype/backend_api/main.py

# 2. 启动远端 MCP 服务 (端口 8001)
TOKEN_KEY=$(base64 -w 0 prototype/tools/.token_key) python prototype/mcp_remote/main.py

# 3. 重启 Claude Code（本地代理自动启动）
```

### 5.5 验证

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

## 6. Skill 固化查询 SOP

### 6.1 问题背景

AI Agent 的系统提示词由厂商控制，用户无法自定义，导致：

| 问题 | 说明 |
|------|------|
| 查询流程不可控 | Agent 可能跳过字典查询直接调用查询工具 |
| 错误处理不一致 | 无法统一引导 Agent 进行友好的异常提示 |

### 6.2 解决方案

通过 Claude Code 的 **Skill 机制**，将财务查询的 SOP 固化到 SKILL.md 文档中。

**核心理念**：Skill 只需 SKILL.md 文档固化流程，无需编写 Python 脚本。

### 6.3 目录结构

```
.claude/skills/finance-query/
└── SKILL.md                    # 唯一必需文件
```

### 6.4 SKILL.md 内容

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

### 6.5 Skill 与 MCP 工具分层

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

## 7. 演进路线与检查清单

### 7.1 三阶段演进

| 阶段 | 目标 | 做法 | 时间 |
|------|------|------|------|
| **MVP** | 打通 Read-Only 闭环 | 硬编码 10+ 核心指标到字典端点 | 2-3 周 |
| **成长期** | 场景化分析工具 | 分析高频查询模式，封装场景工具 | 1-2 月 |
| **成熟期** | 主动预警 | AI 定时巡检，异常主动推送 | 3-6 月 |

### 7.2 技术检查清单

| # | 检查项 | 状态 | 说明 |
|---|--------|------|------|
| 1 | Sidecar 架构 | ✅ | 直接复用原型 |
| 2 | Token 机制 | ✅ | 已实现 |
| 3 | IDOR 防护 | ✅ | user_id 从上下文获取 |
| 4 | 字典端点 | 📝 | 静态返回指标列表 |
| 5 | 查询端点 | 📝 | 参数化查询 + RLS |
| 6 | MCP 工具定义 | 📝 | 2 个财务工具 |
| 7 | finance-query Skill | 📝 | SKILL.md 文档 |

### 7.3 业务检查清单

| # | 检查项 | 状态 | 说明 |
|---|--------|------|------|
| 1 | 核心指标清单 | 📝 | 10-20 个高频指标 |
| 2 | 同义词/别名 | 📝 | 用于语义匹配 |
| 3 | 机构代码映射 | 📝 | user_id → branch_id |

### 7.4 优先级

```
P0（阻塞项）：
├── 业务专家提供指标清单
└── 确认机构代码与 user_id 映射

P1（核心开发）：
├── 实现字典端点
├── 实现查询端点（含 RLS）
├── MCP 工具定义
└── finance-query Skill

P2（增强功能）：
├── 审计日志中间件
└── 性能监控
```

---

## 附录：参考资料

- [MCP 工具描述最佳实践](mcp_tool_description_best_practices.md)
- [MCP 安全认证原型文档](mcp_prototype_sidecar.md)
- [MCP 安全方案文档](mcp_security_authentication.md)
- [MCP 官方文档](https://modelcontextprotocol.io/)
