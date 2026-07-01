"""中文 PRD 生成器——模拟真实用户需求描述。

按业务场景分类，动态生成符合中国企业语境的结构化需求文本。
"""

from __future__ import annotations

SCENARIOS = {
    "新功能": [
        "实现用户登录功能——支持用户名+密码登录，JWT token，bcrypt哈希",
        "添加商品管理模块——商品的增删改查，支持分类和库存管理",
        "实现报表导出——资产负债表、利润表、现金流量表导出为Excel",
        "添加权限管理——角色创建、权限分配、用户-角色关联",
        "实现审批流程——采购订单审批，支持多级审批和会签",
    ],
    "Bug修复": [
        "修复凭证过账后金额不一致的bug——过账时科目余额未正确更新",
        "修复期初余额上传报错——Excel解析时金额字段类型不匹配",
        "修复月末结转后试算不平衡——收入类科目未完全结转到本年利润",
        "修复附件上传失败——文件大小超过限制时前端无提示直接崩溃",
    ],
    "重构": [
        "重构复式记账引擎——将double_entry.py拆分为验证/过账/红冲三个模块",
        "重构前端状态管理——把凭证表单的本地状态迁移到Pinia store",
        "重构数据库访问层——统一使用async session，消除同步调用",
    ],
    "代码审查": [
        "审查PR#140的MockLLMClient——检查接口兼容性和异常处理",
        "审查发票模块的价税分离逻辑——验证税额计算符合增值税率",
        "审查权限引擎PermissionEngine的5层deny-wins逻辑",
    ],
    "数据分析": [
        "分析本月销售收入趋势——对比上月的增长率，按产品线分类",
        "分析应收账款账龄——识别超过90天的逾期账款，计算坏账准备",
        "分析各部门费用预算执行率——实际vs预算，标红超支部门",
    ],
}


def generate_chinese_prd(scenario: str | None = None, index: int = 0) -> str:
    """生成中文 PRD 文本。

    Args:
        scenario: 业务场景（"新功能"/"Bug修复"/"重构"/"代码审查"/"数据分析"）
                  None→随机选择一个场景
        index: 该场景下的第几条需求（默认第0条）

    Returns:
        Markdown 格式的中文需求描述
    """
    import random

    if scenario is None:
        scenario = random.choice(list(SCENARIOS.keys()))

    items = SCENARIOS.get(scenario, SCENARIOS["新功能"])
    idx = index % len(items)
    description = items[idx]

    prd = f"""## 需求：{description}

### 场景类型
{scenario}

### 验收标准
1. 功能完整——满足需求描述中的所有功能点
2. 错误处理——异常输入有明确的错误提示
3. 测试覆盖——核心逻辑有单元测试，覆盖率 ≥80%

### 约束
- 不引入新的第三方依赖
- 遵循项目现有代码规范
- 金额使用 Decimal，禁止 float/double
"""
    return prd


def generate_batch_prds(count: int = 5) -> list[str]:
    """批量生成 N 个不同场景的 PRD。

    Args:
        count: 生成数量

    Returns:
        PRD 文本列表，每个来自不同场景
    """
    prds = []
    keys = list(SCENARIOS.keys())
    for i in range(count):
        key = keys[i % len(keys)]
        idx = (i // len(keys)) % len(SCENARIOS[key])
        prds.append(generate_chinese_prd(key, idx))
    return prds
