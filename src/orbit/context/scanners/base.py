"""确定性预扫描器基类 (Phase 2 Token节省).

每个扫描器是纯函数——输入项目路径，输出结构化 dict。
不用 LLM——正则/AST/git 命令直接出结论。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseScanner(ABC):
    """预扫描器基类——确定性分析，无 LLM 调用。

    异常时返回 {"error": "..."}——不影响其他扫描器。
    """

    name: str = ""  # 子类覆盖: "affected_files" / "import_deps" 等
    timeout: float = 5.0  # 超时保护——大型项目扫描不应阻塞

    @abstractmethod
    def scan(self, project_path: str, **kwargs: Any) -> dict[str, Any]:
        """扫描项目——返回结构化 dict。纯函数，无副作用。"""
        ...
