"""Mode File System —— grill-me 交互协议层.

WHY 独立模块: Agent 行为从 Python 源码解耦到 YAML 配置。
10 行 markdown 可以定义的行为模式，不需要 1000 行 Python 类。

用法:
    from orbit.modes.loader import ModeLoader
    loader = ModeLoader()
    mode = loader.load("clarify")          # → ModeConfig
    ref = loader.load_reference("clarify", "question-tree.md")  # → str
"""

from orbit.modes.schemas import BehaviorConfig, ModeConfig, QuestionStrategy
from orbit.modes.loader import ModeLoader, ModeLoadError
# V15.2+Unknown: 测验生成器（Fable 5 方法论）
from orbit.modes.quiz_generator import QuizGenerator, QuizQuestion, QuizResult

__all__ = [
    "ModeLoader", "ModeLoadError",
    "ModeConfig", "BehaviorConfig", "QuestionStrategy",
    "QuizGenerator", "QuizQuestion", "QuizResult",
]
