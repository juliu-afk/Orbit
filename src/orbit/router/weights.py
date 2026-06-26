"""可配置的评分权重。

优先级: 环境变量 > 默认值。
环境变量命名: ROUTER_WEIGHT_{DIMENSION}
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ScoreWeights:
    """RouterAgent 评分维度权重。所有值应为 0-100，总和不需要等于 100。"""

    files: int = 30       # 涉及文件数
    change: int = 25      # 修改类型
    risk: int = 25        # 风险等级
    role: int = 15        # Agent 角色
    history: int = 5      # 历史相似任务

    @classmethod
    def from_env(cls) -> ScoreWeights:
        """从环境变量读取权重，未设置则用默认值。"""
        return cls(
            files=int(os.getenv("ROUTER_WEIGHT_FILES", "30")),
            change=int(os.getenv("ROUTER_WEIGHT_CHANGE", "25")),
            risk=int(os.getenv("ROUTER_WEIGHT_RISK", "25")),
            role=int(os.getenv("ROUTER_WEIGHT_ROLE", "15")),
            history=int(os.getenv("ROUTER_WEIGHT_HISTORY", "5")),
        )
