"""
财务指标字典配置

由业务专家维护，技术门槛低。
"""

# 用户-机构映射（RLS 行级安全）
USER_BRANCH_MAPPING = {
    "000000001": "BR001",  # 张三 -> 某分行
    "000000002": "BR001",  # 李四 -> 某分行
    "000000003": "BR002",  # 王五 -> 另一分行
    "000000004": "BR001",  # 赵六 -> 某分行
    "000000005": "BR002",  # 钱七 -> 另一分行
}

# 财务指标字典
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


# ==================== 模拟数据 ====================
# 用于原型测试，返回丰富的模拟数据

# BR001 机构数据
BR001_DATA = {
    "NET_PROFIT": {
        2023: {"yearly": 98000.00, "quarterly": [22000, 24000, 26000, 26000]},
        2024: {"yearly": 112000.00, "quarterly": [25000, 28000, 30000, 29000]},
        2025: {"yearly": 125000.00, "quarterly": [30000, 32000, 33000, 30000]},
        2026: {"yearly": 138000.00, "quarterly": [32000, 35000, None, None]},
    },
    "NET_INTEREST_INCOME": {
        2023: {"yearly": 450000.00, "quarterly": [105000, 112000, 118000, 115000]},
        2024: {"yearly": 485000.00, "quarterly": [115000, 122000, 128000, 120000]},
        2025: {"yearly": 520000.00, "quarterly": [125000, 132000, 138000, 125000]},
        2026: {"yearly": 555000.00, "quarterly": [135000, 142000, None, None]},
    },
    "TOTAL_ASSETS": {
        2023: {"yearly": 8500000.00, "quarterly": [8200000, 8350000, 8450000, 8500000]},
        2024: {"yearly": 9200000.00, "quarterly": [8700000, 8900000, 9100000, 9200000]},
        2025: {"yearly": 9800000.00, "quarterly": [9300000, 9500000, 9700000, 9800000]},
        2026: {"yearly": 10500000.00, "quarterly": [10000000, 10300000, None, None]},
    },
    "TOTAL_LIABILITIES": {
        2023: {"yearly": 7800000.00, "quarterly": [7500000, 7650000, 7750000, 7800000]},
        2024: {"yearly": 8400000.00, "quarterly": [8000000, 8150000, 8300000, 8400000]},
        2025: {"yearly": 9000000.00, "quarterly": [8600000, 8750000, 8900000, 9000000]},
        2026: {"yearly": 9650000.00, "quarterly": [9200000, 9450000, None, None]},
    },
    "NPL_RATIO": {
        2023: {"yearly": 1.85, "quarterly": [1.90, 1.88, 1.82, 1.85]},
        2024: {"yearly": 1.72, "quarterly": [1.80, 1.78, 1.70, 1.72]},
        2025: {"yearly": 1.58, "quarterly": [1.65, 1.62, 1.55, 1.58]},
        2026: {"yearly": 1.45, "quarterly": [1.52, 1.48, None, None]},
    },
    "CAR_RATIO": {
        2023: {"yearly": 14.2, "quarterly": [14.0, 14.1, 14.2, 14.2]},
        2024: {"yearly": 14.8, "quarterly": [14.3, 14.5, 14.7, 14.8]},
        2025: {"yearly": 15.2, "quarterly": [14.9, 15.0, 15.1, 15.2]},
        2026: {"yearly": 15.6, "quarterly": [15.3, 15.5, None, None]},
    },
    "LOAN_BALANCE": {
        2023: {"yearly": 5200000.00, "quarterly": [5000000, 5100000, 5150000, 5200000]},
        2024: {"yearly": 5800000.00, "quarterly": [5350000, 5500000, 5650000, 5800000]},
        2025: {"yearly": 6400000.00, "quarterly": [5950000, 6150000, 6300000, 6400000]},
        2026: {"yearly": 7000000.00, "quarterly": [6600000, 6850000, None, None]},
    },
    "DEPOSIT_BALANCE": {
        2023: {"yearly": 6800000.00, "quarterly": [6500000, 6650000, 6750000, 6800000]},
        2024: {"yearly": 7500000.00, "quarterly": [7000000, 7200000, 7380000, 7500000]},
        2025: {"yearly": 8200000.00, "quarterly": [7650000, 7900000, 8080000, 8200000]},
        2026: {"yearly": 8900000.00, "quarterly": [8350000, 8650000, None, None]},
    },
}

# BR002 机构数据（不同数据，用于测试 RLS）
BR002_DATA = {
    "NET_PROFIT": {
        2023: {"yearly": 75000.00, "quarterly": [16000, 18000, 20000, 21000]},
        2024: {"yearly": 88000.00, "quarterly": [19000, 22000, 24000, 23000]},
        2025: {"yearly": 102000.00, "quarterly": [24000, 26000, 27000, 25000]},
        2026: {"yearly": 115000.00, "quarterly": [27000, 29000, None, None]},
    },
    "NET_INTEREST_INCOME": {
        2023: {"yearly": 320000.00, "quarterly": [75000, 80000, 85000, 80000]},
        2024: {"yearly": 350000.00, "quarterly": [82000, 88000, 92000, 88000]},
        2025: {"yearly": 380000.00, "quarterly": [90000, 96000, 100000, 94000]},
        2026: {"yearly": 410000.00, "quarterly": [98000, 104000, None, None]},
    },
    "TOTAL_ASSETS": {
        2023: {"yearly": 6200000.00, "quarterly": [5900000, 6050000, 6150000, 6200000]},
        2024: {"yearly": 6800000.00, "quarterly": [6400000, 6600000, 6700000, 6800000]},
        2025: {"yearly": 7200000.00, "quarterly": [6900000, 7050000, 7150000, 7200000]},
        2026: {"yearly": 7600000.00, "quarterly": [7300000, 7500000, None, None]},
    },
    "TOTAL_LIABILITIES": {
        2023: {"yearly": 5600000.00, "quarterly": [5300000, 5450000, 5550000, 5600000]},
        2024: {"yearly": 6100000.00, "quarterly": [5750000, 5920000, 6030000, 6100000]},
        2025: {"yearly": 6500000.00, "quarterly": [6200000, 6350000, 6450000, 6500000]},
        2026: {"yearly": 6900000.00, "quarterly": [6650000, 6800000, None, None]},
    },
    "NPL_RATIO": {
        2023: {"yearly": 2.15, "quarterly": [2.20, 2.18, 2.12, 2.15]},
        2024: {"yearly": 1.98, "quarterly": [2.05, 2.02, 1.95, 1.98]},
        2025: {"yearly": 1.82, "quarterly": [1.90, 1.88, 1.78, 1.82]},
        2026: {"yearly": 1.68, "quarterly": [1.75, 1.70, None, None]},
    },
    "CAR_RATIO": {
        2023: {"yearly": 13.5, "quarterly": [13.2, 13.3, 13.4, 13.5]},
        2024: {"yearly": 14.0, "quarterly": [13.6, 13.8, 13.9, 14.0]},
        2025: {"yearly": 14.5, "quarterly": [14.1, 14.3, 14.4, 14.5]},
        2026: {"yearly": 14.9, "quarterly": [14.6, 14.8, None, None]},
    },
    "LOAN_BALANCE": {
        2023: {"yearly": 3800000.00, "quarterly": [3600000, 3700000, 3750000, 3800000]},
        2024: {"yearly": 4200000.00, "quarterly": [3950000, 4050000, 4150000, 4200000]},
        2025: {"yearly": 4600000.00, "quarterly": [4350000, 4450000, 4550000, 4600000]},
        2026: {"yearly": 5000000.00, "quarterly": [4750000, 4900000, None, None]},
    },
    "DEPOSIT_BALANCE": {
        2023: {"yearly": 5000000.00, "quarterly": [4800000, 4900000, 4950000, 5000000]},
        2024: {"yearly": 5500000.00, "quarterly": [5150000, 5300000, 5420000, 5500000]},
        2025: {"yearly": 6000000.00, "quarterly": [5650000, 5800000, 5920000, 6000000]},
        2026: {"yearly": 6400000.00, "quarterly": [6100000, 6250000, None, None]},
    },
}

# 机构数据映射
BRANCH_DATA = {
    "BR001": BR001_DATA,
    "BR002": BR002_DATA,
}


def get_metric_unit(metric: str) -> str:
    """获取指标单位"""
    for m in FINANCE_DICTIONARY["metrics"]:
        if m["standard_name"] == metric:
            return m["unit"]
    return ""


def get_metric_display_name(metric: str) -> str:
    """获取指标显示名"""
    for m in FINANCE_DICTIONARY["metrics"]:
        if m["standard_name"] == metric:
            return m["display_name"]
    return metric


def get_simulated_data(
    metric: str,
    branch_id: str,
    year: int = None,
    quarter: int = None,
    month: int = None,
    granularity: str = "yearly"
) -> list:
    """
    获取模拟数据

    Args:
        metric: 指标名
        branch_id: 机构代码
        year: 年份（None 返回最近年数据）
        quarter: 季度（1-4）
        month: 月份（1-12）
        granularity: 聚合粒度

    Returns:
        数据列表，每项包含 period 和 value
    """
    # 获取机构数据
    branch_data = BRANCH_DATA.get(branch_id, {})
    metric_data = branch_data.get(metric, {})

    if not metric_data:
        return []

    results = []

    # 指定年份
    if year:
        year_data = metric_data.get(year)
        if not year_data:
            return []

        if granularity == "yearly":
            # 年度汇总
            value = year_data.get("yearly", 0)
            results.append({"period": str(year), "value": value})
        elif granularity == "quarterly":
            # 季度数据
            quarterly = year_data.get("quarterly", [])
            if quarter:
                # 指定季度
                if 1 <= quarter <= 4:
                    idx = quarter - 1
                    if idx < len(quarterly) and quarterly[idx] is not None:
                        results.append({"period": f"{year}-Q{quarter}", "value": quarterly[idx]})
            else:
                # 全年季度（跳过 None 值）
                for i, v in enumerate(quarterly):
                    if v is not None:
                        results.append({"period": f"{year}-Q{i+1}", "value": v})
        elif granularity == "monthly":
            # 月度数据
            if month:
                # 指定月份：根据月份计算所属季度
                q = (month - 1) // 3 + 1
                m_in_q = ((month - 1) % 3) + 1
                quarterly = year_data.get("quarterly", [])
                if q <= len(quarterly) and quarterly[q-1] is not None:
                    q_val = quarterly[q-1]
                    # 将季度值按月份分配（简单模拟：各月略有差异）
                    month_weights = [0.32, 0.34, 0.34]  # 季度内各月权重
                    month_val = q_val * month_weights[m_in_q - 1]
                    results.append({"period": f"{year}-{month:02d}", "value": round(month_val, 2)})
            else:
                # 全年月度数据（跳过 None 季度）
                quarterly = year_data.get("quarterly", [])
                month_weights = [0.32, 0.34, 0.34]  # 季度内各月权重
                for q_idx, q_val in enumerate(quarterly):
                    if q_val is None:
                        continue
                    for m in range(1, 4):
                        month_num = q_idx * 3 + m
                        month_val = q_val * month_weights[m - 1]
                        results.append({
                            "period": f"{year}-{month_num:02d}",
                            "value": round(month_val, 2)
                        })
    else:
        # 不指定年份，返回最近数据
        sorted_years = sorted(metric_data.keys(), reverse=True)

        if granularity == "yearly":
            # 返回最近3年趋势
            for y in sorted_years[:3]:
                year_data = metric_data[y]
                results.append({"period": str(y), "value": year_data.get("yearly", 0)})
        elif granularity == "quarterly":
            # 返回最近年份的季度数据
            if sorted_years:
                latest_year = sorted_years[0]
                year_data = metric_data[latest_year]
                quarterly = year_data.get("quarterly", [])
                if quarter:
                    # 指定季度
                    idx = quarter - 1
                    if idx < len(quarterly) and quarterly[idx] is not None:
                        results.append({"period": f"{latest_year}-Q{quarter}", "value": quarterly[idx]})
                else:
                    # 全部季度（跳过 None 值）
                    for i, v in enumerate(quarterly):
                        if v is not None:
                            results.append({"period": f"{latest_year}-Q{i+1}", "value": v})
        elif granularity == "monthly":
            # 返回最近年份的月度数据
            if sorted_years:
                latest_year = sorted_years[0]
                year_data = metric_data[latest_year]
                quarterly = year_data.get("quarterly", [])
                month_weights = [0.32, 0.34, 0.34]

                if month:
                    # 指定月份
                    q = (month - 1) // 3 + 1
                    m_in_q = ((month - 1) % 3) + 1
                    if q <= len(quarterly) and quarterly[q-1] is not None:
                        q_val = quarterly[q-1]
                        month_val = q_val * month_weights[m_in_q - 1]
                        results.append({"period": f"{latest_year}-{month:02d}", "value": round(month_val, 2)})
                else:
                    # 全部月度（跳过 None 季度）
                    for q_idx, q_val in enumerate(quarterly):
                        if q_val is None:
                            continue
                        for m in range(1, 4):
                            month_num = q_idx * 3 + m
                            month_val = q_val * month_weights[m - 1]
                            results.append({
                                "period": f"{latest_year}-{month_num:02d}",
                                "value": round(month_val, 2)
                            })

    return results
