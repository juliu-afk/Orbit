"""会计领域本体——10 个核心概念 + 种子数据。

来源优先级：国际准则(CAS/IFRS) > 国家法规 > 行业规范 > 地方规章 > 企业内部
source_uri 格式：{来源类型}://{来源标识}/{条目ID}
"""

from typing import TypedDict


class Concept(TypedDict):
    """知识图谱概念条目。"""

    domain: str
    concept: str
    name_zh: str
    definition: str
    formula: str
    source_uri: str
    source_level: int


# 会计领域 10 个核心概念（中国企业会计准则 + IFRS）
ACCOUNTING_CONCEPTS: list[Concept] = [
    {
        "domain": "accounting",
        "concept": "CurrentRatio",
        "name_zh": "流动比率",
        "definition": "流动资产除以流动负债，衡量企业短期偿债能力。",
        "formula": "流动资产 / 流动负债",
        "source_uri": "standard://cas/cas_30_ratio_analysis",
        "source_level": 2,
    },
    {
        "domain": "accounting",
        "concept": "QuickRatio",
        "name_zh": "速动比率",
        "definition": "速动资产（流动资产 - 存货）除以流动负债，更严格地衡量短期偿债能力。",
        "formula": "(流动资产 - 存货) / 流动负债",
        "source_uri": "standard://cas/cas_30_ratio_analysis",
        "source_level": 2,
    },
    {
        "domain": "accounting",
        "concept": "DebtToEquity",
        "name_zh": "资产负债率",
        "definition": "负债总额除以所有者权益总额，衡量企业财务杠杆。",
        "formula": "负债总额 / 所有者权益总额",
        "source_uri": "standard://ifrs/ifrs_framework_4",
        "source_level": 1,
    },
    {
        "domain": "accounting",
        "concept": "GrossProfitMargin",
        "name_zh": "毛利率",
        "definition": "毛利（营业收入 - 营业成本）除以营业收入，衡量产品或服务的盈利能力。",
        "formula": "(营业收入 - 营业成本) / 营业收入 × 100%",
        "source_uri": "standard://cas/cas_30_income_statement",
        "source_level": 2,
    },
    {
        "domain": "accounting",
        "concept": "ROE",
        "name_zh": "净资产收益率",
        "definition": "净利润除以平均净资产，衡量股东权益的回报水平。",
        "formula": "净利润 / 平均净资产 × 100%",
        "source_uri": "standard://cas/cas_30_profitability",
        "source_level": 2,
    },
    {
        "domain": "accounting",
        "concept": "InventoryTurnover",
        "name_zh": "存货周转率",
        "definition": "营业成本除以平均存货余额，衡量企业存货管理效率。",
        "formula": "营业成本 / 平均存货余额",
        "source_uri": "standard://cas/cas_1_inventory",
        "source_level": 2,
    },
    {
        "domain": "accounting",
        "concept": "EBITDA",
        "name_zh": "息税折旧摊销前利润",
        "definition": "净利润 + 所得税费用 + 利息费用 + 折旧与摊销。衡量企业经营盈利能力，排除资本结构和税务差异。",
        "formula": "净利润 + 所得税 + 利息费用 + 折旧 + 摊销",
        "source_uri": "standard://ifrs/ifrs_non_gaap_measures",
        "source_level": 1,
    },
    {
        "domain": "accounting",
        "concept": "AccrualBasis",
        "name_zh": "权责发生制",
        "definition": "收入和费用在实际发生时确认，而非现金收付时。企业会计基本假设之一。",
        "formula": "",
        "source_uri": "standard://cas/cas_basic_assumptions",
        "source_level": 2,
    },
    {
        "domain": "accounting",
        "concept": "DoubleEntry",
        "name_zh": "复式记账",
        "definition": "每一笔经济业务都以相等金额在至少两个账户中同时登记，有借必有贷、借贷必相等。",
        "formula": "资产 = 负债 + 所有者权益",
        "source_uri": "standard://ifrs/ifrs_conceptual_framework",
        "source_level": 1,
    },
    {
        "domain": "accounting",
        "concept": "TrialBalance",
        "name_zh": "试算平衡",
        "definition": "将所有总账账户的借方余额和贷方余额分别汇总，验证借贷总额是否相等以检查记账正确性。",
        "formula": "∑借方余额 = ∑贷方余额",
        "source_uri": "standard://cas/cas_30_trial_balance",
        "source_level": 2,
    },
]
