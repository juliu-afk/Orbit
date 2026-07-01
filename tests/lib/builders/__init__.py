"""业务流构建器——链式构建完整链路。

每个 Builder 模拟真实用户操作序列，内置默认 Mock，
一行代码走通全链路。支持链式配置 + 断言方法。
"""

from tests.lib.builders.task_chain import TaskChain

__all__ = [
    "TaskChain",
]
