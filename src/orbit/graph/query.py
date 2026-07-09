"""统一图谱查询接口（设计文档 §10.4）。

Agent 通过 query_graph(type, ...) 统一入口查询代码/数据库/配置图谱，
不再需要记住三个引擎的不同 API。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import structlog

if TYPE_CHECKING:
    from orbit.graph.engines.code_graph import CodeGraphEngine
    from orbit.graph.engines.config_graph import ConfigGraphEngine
    from orbit.graph.engines.db_graph import DbGraphEngine

logger = structlog.get_logger("orbit.graph.query")

GraphType = Literal["code", "database", "config"]


class GraphQuery:
    """统一图谱查询入口——路由到对应引擎。"""

    def __init__(
        self,
        code_graph: "CodeGraphEngine | None" = None,
        db_graph: "DbGraphEngine | None" = None,
        config_graph: "ConfigGraphEngine | None" = None,
    ) -> None:
        self._code = code_graph
        self._db = db_graph
        self._config = config_graph

    async def query(
        self,
        graph_type: GraphType,
        symbol: str | None = None,
        table: str | None = None,
        key: str | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        """统一图谱查询。

        Args:
            graph_type: "code" | "database" | "config"
            symbol: 代码符号名（仅 graph_type="code"）
            table: 数据库表名（仅 graph_type="database"）
            key: 配置键名（仅 graph_type="config"）
            **filters: 引擎特定过滤参数

        Returns:
            {"found": bool, "data": ..., "type": graph_type}
        """
        if graph_type == "code":
            if self._code is None:
                return {"found": False, "error": "CodeGraph 未初始化"}
            if symbol:
                defs = await self._code.find_definitions_with_positions(symbol)
                return {"found": bool(defs), "data": defs, "type": "code"}
            # 无 symbol → 返回架构概览
            nodes = await self._code.get_all_nodes()
            return {"found": True, "data": {"node_count": len(nodes)}, "type": "code"}

        elif graph_type == "database":
            if self._db is None:
                return {"found": False, "error": "DbGraph 未初始化"}
            if table:
                exists = await self._db.table_exists(table)
                return {"found": exists, "data": {"table": table}, "type": "database"}
            return {"found": False, "error": "请指定 table 参数"}

        elif graph_type == "config":
            if self._config is None:
                return {"found": False, "error": "ConfigGraph 未初始化"}
            if key:
                result = self._config.get_config(key)
                return {"found": result is not None, "data": result, "type": "config"}
            return {"found": False, "error": "请指定 key 参数"}

        return {"found": False, "error": f"未知图谱类型: {graph_type}"}
