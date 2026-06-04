# 后台 API 接口文档

## 概述

后台 API 提供用户查询和财务数据查询接口，服务端口 **8000**。

**关键特性：**
- **RLS 行级安全** - 用户只能查询所属机构的数据，自动过滤
- **白名单验证** - 只允许查询字典中定义的财务指标
- **IDOR 防护** - 用户身份从 Header 传入，不接受 URL 参数

---

## 端点列表

| 端点 | 方法 | 用途 | 权限 |
|------|------|------|------|
| `/api/finance/dictionary` | GET | 获取财务指标字典 | 无 |
| `/api/finance/query` | GET | 查询财务指标数据 | 已认证用户 |

---

## 1. 获取财务指标字典

```
GET /api/finance/dictionary
```

**用途：** 获取支持的财务指标元数据，用于语义匹配和指标选择

**响应示例：**
```json
{
  "metrics": [
    {
      "standard_name": "NET_PROFIT",
      "display_name": "净利润",
      "category": "盈利能力",
      "unit": "万元",
      "description": "扣除所有成本、税费后的利润总额",
      "synonyms": ["纯利润", "税后利润", "利润总额", "净利润"],
      "formula": "营业收入 - 业成本 - 税费"
    },
    {
      "standard_name": "TOTAL_ASSETS",
      "display_name": "资产总额",
      "category": "规模指标",
      "unit": "万元",
      "description": "银行全部资产的总和",
      "synonyms": ["总资产", "资产负债表资产", "资产规模"],
      "formula": "各项资产之和"
    }
  ],
  "dimensions": [
    {"name": "year", "display_name": "年份", "type": "int", "required": false},
    {"name": "quarter", "display_name": "季度", "type": "int", "range": "1-4"},
    {"name": "month", "display_name": "月份", "type": "int", "range": "1-12"},
    {"name": "granularity", "display_name": "聚合粒度", "type": "enum", "values": ["yearly", "quarterly", "monthly"]}
  ]
}
```

**支持的指标：**

| 指标名 | 显示名 | 分类 | 单位 |
|--------|--------|------|------|
| `NET_PROFIT` | 净利润 | 盈利能力 | 万元 |
| `NET_INTEREST_INCOME` | 净利息收入 | 盈利能力 | 万元 |
| `TOTAL_ASSETS` | 资产总额 | 规模指标 | 万元 |
| `TOTAL_LIABILITIES` | 负债总额 | 规模指标 | 万元 |
| `NPL_RATIO` | 不良贷款率 | 风险指标 | % |
| `CAR_RATIO` | 资本充足率 | 风险指标 | % |
| `LOAN_BALANCE` | 贷款余额 | 业务指标 | 万元 |
| `DEPOSIT_BALANCE` | 存款余额 | 业务指标 | 万元 |

---

## 2. 查询财务指标数据

```
GET /api/finance/query
```

**用途：** 查询具体财务指标数值

**安全机制：**
- **白名单验证** - 只允许查询字典中定义的指标
- **RLS 行级安全** - 强制按用户所属机构过滤数据
- **参数化查询** - 防止 SQL 注入

**请求头：**

| Header | 必需 | 说明 |
|--------|------|------|
| `X-User-ID` | 是 | 9位数字用户编号 |

**查询参数：**

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `metric` | string | 是 | - | 指标名（字典中的 standard_name） |
| `year` | int | 否 | - | 年份（如 2026） |
| `quarter` | int | 否 | - | 季度（1-4） |
| `month` | int | 否 | - | 月份（1-12） |
| `granularity` | string | 否 | yearly | 聚合粒度（yearly/quarterly/monthly） |

**响应示例：**

查询 `TOTAL_ASSETS`，2026年，年度粒度：
```json
{
  "metric": "TOTAL_ASSETS",
  "metric_name": "资产总额",
  "unit": "万元",
  "branch_id": "BR001",
  "granularity": "yearly",
  "data": [
    {"period": "2026", "value": 10500000.0}
  ],
  "query_time": "2026-06-04T02:54:37.884577+00:00"
}
```

查询 `NPL_RATIO`，2026年，季度粒度：
```json
{
  "metric": "NPL_RATIO",
  "metric_name": "不良贷款率",
  "unit": "%",
  "branch_id": "BR001",
  "granularity": "quarterly",
  "data": [
    {"period": "2026-Q1", "value": 1.52},
    {"period": "2026-Q2", "value": 1.48}
  ],
  "query_time": "2026-06-04T02:54:37.884577+00:00"
}
```

**常用查询场景：**

| 场景 | 参数设置 |
|------|----------|
| 查询去年净利润 | `metric=NET_PROFIT&year=2025` |
| 查询一季度不良率 | `metric=NPL_RATIO&year=2026&quarter=1` |
| 查询最近三年资产趋势 | `metric=TOTAL_ASSETS&granularity=yearly`（不指定 year） |
| 查询各季度资产负债 | `metric=TOTAL_ASSETS&granularity=quarterly` |

**错误响应：**

| 状态码 | 说明 |
|--------|------|
| 400 | 用户编号格式错误 |
| 400 | 不支持的指标名 |
| 400 | 季度/月份范围错误 |
| 400 | granularity 值错误 |

---

## 数据范围

**支持的年份：** 2023-2026

**数据可用性说明：**
- 2023-2025 年：全年数据可用
- 2026 年：仅 Q1、Q2 数据可用，Q3、Q4 为 `None`（查询时自动跳过）

**机构数据：**
- `BR001` - 某分行（用户 000000001、000000002、000000004）
- `BR002` - 另一分行（用户 000000003、000000005）

---

## 启动服务

```bash
# 设置密钥环境变量
export TOKEN_KEY=<密钥>

# 启动后台 API（端口 8000）
python prototype/backend_api/main.py
```

---

## 架构说明

后台 API 作为 MCP 安全认证原型的业务逻辑层：

```
Claude Code ──Stdio──▶ 本地代理 ──HTTPS──▶ 远端 MCP 服务 ──▶ 后台 API
                          │                      │              │
                          │ MCP_REFRESH_TOKEN    │ 解密 Token   │ RLS 过滤
                          │ 自动刷新             │ 验证有效期   │ 白名单验证
```

**关键安全措施：**
1. 用户身份封装在加密 Token 中，本地代理无法查看
2. 远端 MCP 服务解密 Token 后，通过 `X-User-ID` Header 传递用户编号
3. 后台 API 强制按 `USER_BRANCH_MAPPING` 过滤机构数据
4. 财务查询不接受任何机构标识参数，防止 IDOR 攻击