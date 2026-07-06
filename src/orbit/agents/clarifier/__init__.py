"""需求澄清 Agent——多轮对话收敛模糊需求为结构化 PRD。

拆分为 4 个文件：
- models.py: StructuredPRD + ValidationResult 数据模型
- constants.py: System Prompt + 校验常量
- agent.py: ClarifierAgent 类
- validators.py: validate_prd + 校验辅助函数
"""

from orbit.agents.clarifier.agent import ClarifierAgent
from orbit.agents.clarifier.models import StructuredPRD, ValidationResult
from orbit.agents.clarifier.validators import validate_prd

__all__ = [
    "ClarifierAgent",
    "StructuredPRD",
    "ValidationResult",
    "validate_prd",
]
