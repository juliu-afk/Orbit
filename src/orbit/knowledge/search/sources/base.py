"""搜索数据源抽象基类 (V15.2).

所有搜索后端实现统一的 SearchSource 接口，
支持健康检查 + 优先级路由 + 自动降级。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RawSearchItem:
    """搜索源返回的原始条目——未排序、未去重。"""

    title: str
    url: str
    snippet: str
    source_name: str
    relevance_score: float = 0.0
    content_markdown: str = ""  # 提取后的正文（可选，延迟加载）


@dataclass
class SearchResult:
    """最终返回的搜索结果——已去重、已排序、含 Markdown 正文。"""

    title: str
    url: str
    snippet: str
    content: str  # Markdown 正文
    source_name: str
    relevance_score: float


class SearchSource(ABC):
    """搜索数据源抽象基类。

    子类实现 search() 和 health_check()。
    priority 越小越优先——调度时按 priority 升序排列。
    """

    name: str = "base"
    priority: int = 100  # 越小越优先

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[RawSearchItem]:
        """执行搜索——返回原始条目列表。"""
        ...

    async def health_check(self) -> bool:
        """健康检查——返回 False 时自动跳过此源。

        默认返回 True。子类覆盖以实现实际探活。
        """
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(priority={self.priority})"
