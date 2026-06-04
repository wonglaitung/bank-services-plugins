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
      "standard_name": "TOTAL_LIABILITIES",
      "display_name": "负债总额",
      "category": "规模指标",
      "unit": "万元",
      "description": "银行全部负债的总和",
      "synonyms": ["总负债", "负债规模"],
      "formula": "各项负债之和"
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
    },
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

## RLS 行级安全实现

### 设计原则

RLS（Row-Level Security）确保用户只能查询所属机构的数据，**核心原则：机构代码由系统注入，不接受用户参数**。

### 实现机制

```
┌─────────────────────────────────────────────────────────────────┐
│                        请求处理流程                              │
├─────────────────────────────────────────────────────────────────┤
│  1. 远端 MCP 服务解密 Token，提取 user_id                        │
│  2. 通过 X-User-ID Header 传递给后台 API                         │
│  3. 后台 API 查 USER_BRANCH_MAPPING 获取 branch_id               │
│  4. branch_id 作为查询条件强制注入，用户无法覆盖                  │
└─────────────────────────────────────────────────────────────────┘
```

### 用户-机构映射配置

```python
# config/dictionary.py
USER_BRANCH_MAPPING = {
    "000000001": "BR001",  # 张三 -> 某分行
    "000000002": "BR001",  # 李四 -> 某分行
    "000000003": "BR002",  # 王五 -> 另一分行
    "000000004": "BR001",  # 赵六 -> 某分行
    "000000005": "BR002",  # 钱七 -> 另一分行
}
```

### 代码实现

```python
# main.py
@app.get("/api/finance/query")
async def query_finance_metrics(
    metric: str,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    month: Optional[int] = None,
    granularity: str = "yearly",
    x_user_id: str = Header(None, alias="X-User-ID")  # 从 Header 获取
):
    # 1. 验证用户编号格式
    if not x_user_id or not x_user_id.isdigit() or len(x_user_id) != 9:
        raise HTTPException(400, "用户编号格式错误")

    # 2. 白名单验证（防止 SQL 注入）
    if metric not in ALLOWED_METRICS:
        raise HTTPException(400, f"不支持的指标: {metric}")

    # 3. RLS：系统注入 branch_id（用户无法控制）
    branch_id = USER_BRANCH_MAPPING.get(x_user_id, "BR000")

    # 4. 执行查询，branch_id 作为强制过滤条件
    data = get_simulated_data(
        metric=metric,
        branch_id=branch_id,  # 系统注入，非用户输入
        year=year,
        quarter=quarter,
        month=month,
        granularity=granularity
    )
    ...
```

### 安全特性

| 特性 | 说明 |
|------|------|
| **参数隔离** | API 不接受 branch_id 参数，完全杜绝用户伪造 |
| **映射表控制** | 机构归属由后台配置，用户无法篡改 |
| **默认拒绝** | 未配置映射的用户返回空数据或默认机构 |

---

## SQL 查询拼接逻辑

### 参数化查询原则

**所有用户输入必须参数化，禁止字符串拼接 SQL**。

### 白名单验证

用户输入的 `metric`、`granularity` 必须在白名单内：

```python
ALLOWED_METRICS = {
    "NET_PROFIT", "NET_INTEREST_INCOME", "TOTAL_ASSETS",
    "TOTAL_LIABILITIES", "NPL_RATIO", "CAR_RATIO",
    "LOAN_BALANCE", "DEPOSIT_BALANCE"
}

ALLOWED_GRANULARITY = {"yearly", "quarterly", "monthly"}
```

### 动态 SQL 拼接实现

SQL 根据参数动态构建，**WHERE 条件按需添加**，值始终参数化绑定。

```python
def build_query(metric: str, branch_id: str, year: int = None,
                quarter: int = None, month: int = None,
                granularity: str = "yearly") -> tuple[str, list]:
    """
    动态构建 SQL 查询

    Returns:
        (sql, params): SQL 语句和参数列表
    """
    # 基础 SQL（branch_id 始终作为 RLS 条件）
    sql = "SELECT period, value FROM finance_metrics WHERE branch_id = %s"
    params = [branch_id]

    # 白名单字段直接拼接到 SQL（安全，已通过白名单验证）
    sql += " AND metric = %s"
    params.append(metric)

    sql += " AND granularity = %s"
    params.append(granularity)

    # 年份条件
    if year is not None:
        sql += " AND period LIKE %s"
        params.append(f"{year}%")

    # 指定季度（季度粒度时）
    if quarter is not None and granularity == "quarterly":
        sql = sql.replace("AND period LIKE %s", "AND period = %s")
        params[-1] = f"{year}-Q{quarter}"

    # 指定月份（月度粒度时）
    if month is not None and granularity == "monthly":
        sql = sql.replace("AND period LIKE %s", "AND period = %s")
        params[-1] = f"{year}-{month:02d}"

    # 排序和限制
    if year is None:
        # 不指定年份时，返回最近数据
        sql += " ORDER BY period DESC LIMIT 3"
    else:
        sql += " ORDER BY period"

    return sql, params
```

### SQL 模板示例

假设数据存储在 `finance_metrics` 表中，结构如下：

```sql
CREATE TABLE finance_metrics (
    branch_id VARCHAR(10) NOT NULL,
    metric VARCHAR(50) NOT NULL,
    period VARCHAR(10) NOT NULL,      -- 格式: '2026' 或 '2026-Q1' 或 '2026-05'
    granularity VARCHAR(10) NOT NULL, -- yearly/quarterly/monthly
    value DECIMAL(18,2),
    PRIMARY KEY (branch_id, metric, period, granularity)
);

-- 示例数据
INSERT INTO finance_metrics VALUES
('BR001', 'TOTAL_ASSETS', '2026',      'yearly',   10500000.00),
('BR001', 'TOTAL_ASSETS', '2026-Q1',   'quarterly', 10000000.00),
('BR001', 'TOTAL_ASSETS', '2026-05',   'monthly',  10200000.00);
```

#### 场景 1：年度汇总查询

**请求参数：** `metric=TOTAL_ASSETS&year=2026&granularity=yearly`

**动态拼接过程：**
```python
# 初始 SQL
sql = "SELECT period, value FROM finance_metrics WHERE branch_id = %s"
params = ["BR001"]

# 添加 metric（白名单验证后）
sql += " AND metric = %s"
params.append("TOTAL_ASSETS")

# 添加 granularity（白名单验证后）
sql += " AND granularity = %s"
params.append("yearly")

# 添加年份条件
sql += " AND period LIKE %s"
params.append("2026%")

# 添加排序
sql += " ORDER BY period"
```

**最终 SQL：**
```sql
SELECT period, value FROM finance_metrics
WHERE branch_id = %s
  AND metric = %s
  AND granularity = %s
  AND period LIKE %s
ORDER BY period;
```

**参数绑定：**
```python
params = ["BR001", "TOTAL_ASSETS", "yearly", "2026%"]
```

#### 场景 2：季度数据查询

**请求参数：** `metric=NPL_RATIO&year=2026&granularity=quarterly`

**动态拼接过程：**
```python
sql = "SELECT period, value FROM finance_metrics WHERE branch_id = %s"
params = ["BR001"]

sql += " AND metric = %s"
params.append("NPL_RATIO")

sql += " AND granularity = %s"
params.append("quarterly")

sql += " AND period LIKE %s"
params.append("2026%")

sql += " ORDER BY period"
```

**最终 SQL：**
```sql
SELECT period, value FROM finance_metrics
WHERE branch_id = %s
  AND metric = %s
  AND granularity = %s
  AND period LIKE %s
ORDER BY period;
```

**参数绑定：**
```python
params = ["BR001", "NPL_RATIO", "quarterly", "2026%"]
```

**查询结果：** 返回 2026-Q1、2026-Q2 等季度数据

#### 场景 3：指定季度查询

**请求参数：** `metric=NPL_RATIO&year=2026&quarter=1&granularity=quarterly`

**动态拼接过程：**
```python
sql = "SELECT period, value FROM finance_metrics WHERE branch_id = %s"
params = ["BR001"]

sql += " AND metric = %s"
params.append("NPL_RATIO")

sql += " AND granularity = %s"
params.append("quarterly")

# 指定季度：替换 LIKE 为精确匹配
sql += " AND period = %s"
params.append("2026-Q1")
```

**最终 SQL：**
```sql
SELECT period, value FROM finance_metrics
WHERE branch_id = %s
  AND metric = %s
  AND granularity = %s
  AND period = %s;
```

**参数绑定：**
```python
params = ["BR001", "NPL_RATIO", "quarterly", "2026-Q1"]
```

#### 场景 4：月度数据查询

**请求参数：** `metric=TOTAL_ASSETS&year=2026&month=5&granularity=monthly`

**动态拼接过程：**
```python
sql = "SELECT period, value FROM finance_metrics WHERE branch_id = %s"
params = ["BR001"]

sql += " AND metric = %s"
params.append("TOTAL_ASSETS")

sql += " AND granularity = %s"
params.append("monthly")

# 指定月份
sql += " AND period = %s"
params.append("2026-05")
```

**最终 SQL：**
```sql
SELECT period, value FROM finance_metrics
WHERE branch_id = %s
  AND metric = %s
  AND granularity = %s
  AND period = %s;
```

**参数绑定：**
```python
params = ["BR001", "TOTAL_ASSETS", "monthly", "2026-05"]
```

#### 场景 5：不指定年份，返回最近数据

**请求参数：** `metric=TOTAL_ASSETS&granularity=yearly`

**动态拼接过程：**
```python
sql = "SELECT period, value FROM finance_metrics WHERE branch_id = %s"
params = ["BR001"]

sql += " AND metric = %s"
params.append("TOTAL_ASSETS")

sql += " AND granularity = %s"
params.append("yearly")

# 不指定年份：排序取最近3条
sql += " ORDER BY period DESC LIMIT 3"
```

**最终 SQL：**
```sql
SELECT period, value FROM finance_metrics
WHERE branch_id = %s
  AND metric = %s
  AND granularity = %s
ORDER BY period DESC
LIMIT 3;
```

**参数绑定：**
```python
params = ["BR001", "TOTAL_ASSETS", "yearly"]
```

### 安全检查清单

| 检查项 | 实现方式 |
|--------|----------|
| SQL 注入防护 | 参数化查询 + 白名单验证 |
| IDOR 防护 | branch_id 由系统注入，不接受用户参数 |
| 越权访问 | RLS 映射表强制过滤机构数据 |
| 非法参数 | 范围校验（quarter: 1-4, month: 1-12） |

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