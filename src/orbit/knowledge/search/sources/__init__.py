"""搜索数据源适配器集合 (V15.2)."""

from orbit.knowledge.search.sources.base import RawSearchItem, SearchResult, SearchSource
from orbit.knowledge.search.sources.web import WebSource
from orbit.knowledge.search.sources.code import CodeSource
from orbit.knowledge.search.sources.anysearch import AnySearchAdapter

__all__ = [
    "RawSearchItem",
    "SearchResult",
    "SearchSource",
    "WebSource",
    "CodeSource",
    "AnySearchAdapter",
]
