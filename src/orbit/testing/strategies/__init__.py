"""测试生成策略 —— 路径敏感 / 变异引导 / 意图驱动 / 属性测试 / AB 对比。

Phase 1: 意图驱动（intention_driven）
Phase 2: 路径敏感（path_sensitive）+ 属性测试（property_based）
Phase 3: 变异引导（mutation_guided）+ AB 对比（ab_runner）
"""

from __future__ import annotations
