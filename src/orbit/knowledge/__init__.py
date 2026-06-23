"""Step 3.4a 外挂领域知识图谱——知识存储层。

SQLite 存储，会计本体 + 种子概念数据。
后续 3.4b/c/d 扩展查询引擎/语义检索/MCP 集成。
"""

from orbit.knowledge.store import KnowledgeStore

__all__ = ["KnowledgeStore"]
