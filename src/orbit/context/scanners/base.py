"""确定性预扫描器基类 (Phase 2 Token节省). 纯函数，不用LLM。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class BaseScanner(ABC):
    name: str = ""
    timeout: float = 5.0
    @abstractmethod
    def scan(self, project_path: str, **kwargs: Any) -> dict[str, Any]: ...
