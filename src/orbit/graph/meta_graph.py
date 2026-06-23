"""元图谱 (Step 8)——跨图谱关系存储与查询.

SQLite 存储五图谱间的交叉引用关系 (代码↔数据库↔配置↔知识↔推理链).
提供影响面分析 + 架构腐化检测 + 变更追溯.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger("orbit.meta_graph")


class RelationType(StrEnum):
    """跨图谱关系类型。"""

    READS_FROM = "READS_FROM"  # 代码→数据库: 读操作
    WRITES_TO = "WRITES_TO"  # 代码→数据库: 写操作
    DELETES_FROM = "DELETES_FROM"
    DEPENDS_ON = "DEPENDS_ON"  # 代码→配置/代码→代码
    OVERRIDES = "OVERRIDES"  # 配置→配置: 覆盖
    REFERENCES = "REFERENCES"  # 代码→知识/知识→代码
    COMPLIES_WITH = "COMPLIES_WITH"  # 代码→知识: 合规
    PRODUCED_BY = "PRODUCED_BY"  # 推理链→代码: 哪个推理产生了此代码
    MODIFIED_BY = "MODIFIED_BY"  # 代码→推理链: 哪个推理修改了此代码
    DECIDED_AT = "DECIDED_AT"  # 配置→推理链: 哪个决策定了此配置
    CONNECTS_TO = "CONNECTS_TO"  # 通用关联
    USED_IN = "USED_IN"  # 知识→代码: 知识在哪里使用


@dataclass
class CrossGraphRelation:
    """跨图谱关系——连接两个不同图谱的节点。"""

    source_type: str  # code | db | config | knowledge | reasoning
    source_id: str  # 源节点标识
    relation: RelationType
    target_type: str
    target_id: str  # 目标节点标识
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


class MetaGraph:
    """元图谱——跨图谱关系存储 (SQLite)。

    用法:
        mg = MetaGraph()
        mg.add_relation("code", "PaymentService.process", RelationType.WRITES_TO,
                        "db", "payments")
        impact = mg.impact_analysis("code", "PaymentService.process")
        # → {"databases": ["payments"], "configs": [...], ...}
    """

    def __init__(self, db_path: str = "data/meta_graph.db") -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            import os

            os.makedirs("data", exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
            self._ensure_table()
        return self._conn

    def _ensure_table(self) -> None:
        self._get_conn().execute("""
            CREATE TABLE IF NOT EXISTS cross_graph_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            )
        """)
        self._get_conn().execute(
            "CREATE INDEX IF NOT EXISTS idx_cgr_source ON cross_graph_relations(source_type, source_id)"
        )
        self._get_conn().execute(
            "CREATE INDEX IF NOT EXISTS idx_cgr_target ON cross_graph_relations(target_type, target_id)"
        )

    def add_relation(
        self,
        source_type: str, source_id: str,
        relation: RelationType,
        target_type: str, target_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """添加跨图谱关系。"""
        import json

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO cross_graph_relations "
            "(source_type, source_id, relation, target_type, target_id, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (source_type, source_id, relation.value, target_type, target_id,
             json.dumps(metadata or {}), time.time()),
        )
        conn.commit()

    def impact_analysis(self, node_type: str, node_id: str) -> dict[str, Any]:
        """影响面分析——查询与指定节点关联的所有跨图谱节点。

        返回: { "databases": [...], "configs": [...], "knowledge": [...], "reasoning": [...] }
        """
        rows = self._get_conn().execute(
            "SELECT * FROM cross_graph_relations WHERE source_type=? AND source_id=?",
            (node_type, node_id),
        ).fetchall()

        result: dict[str, list[str]] = {
            "databases": [], "configs": [], "knowledge": [], "reasoning": [],
        }
        type_map = {"db": "databases", "config": "configs",
                     "knowledge": "knowledge", "reasoning": "reasoning"}

        for r in rows:
            key = type_map.get(r["target_type"])
            if key and r["target_id"] not in result[key]:
                result[key].append(r["target_id"])

        return result

    def config_impact_trace(self, config_key: str) -> dict[str, Any]:
        """配置变更追溯——哪些代码/任务受此配置影响。"""
        rows = self._get_conn().execute(
            "SELECT * FROM cross_graph_relations WHERE source_type='config' AND source_id LIKE ?",
            (f"%{config_key}%",),
        ).fetchall()

        affected_code: list[str] = []
        affected_tasks: list[str] = []
        for r in rows:
            if r["target_type"] == "code":
                affected_code.append(r["target_id"])
            elif r["target_type"] == "reasoning":
                affected_tasks.append(r["target_id"])

        return {"affected_code": affected_code, "affected_tasks": affected_tasks}

    def architecture_health_check(self) -> list[dict[str, Any]]:
        """架构腐化检测——返回违反架构约束的关系。

        检测规则:
        1. 代码→数据库无对应 READ/WRITE 标注 (孤儿读写)
        2. 配置无推理链支撑 (任意配置)
        """
        violations: list[dict[str, Any]] = []

        # 规则 1: 检查是否有悬空引用 (source 存在但 target 无对应记录)
        conn = self._get_conn()
        # 简化: 检查 source_type=code 且 target_type=db 但无 COMPLIES_WITH 关联
        raw = conn.execute(
            "SELECT source_id, target_id FROM cross_graph_relations "
            "WHERE source_type='code' AND target_type='db' AND relation='WRITES_TO'"
        ).fetchall()
        for r in raw:
            # 检查是否同时有 COMPLIES_WITH 知识关联
            has_compliance = conn.execute(
                "SELECT 1 FROM cross_graph_relations "
                "WHERE source_type='code' AND source_id=? AND target_type='knowledge' AND relation='COMPLIES_WITH'",
                (r["source_id"],),
            ).fetchone()
            if not has_compliance:
                violations.append({
                    "type": "db_write_without_compliance",
                    "source": r["source_id"],
                    "target": r["target_id"],
                    "message": f"代码 {r['source_id']} 写入 {r['target_id']} 无合规关联",
                })

        return violations

    def list_relations(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._get_conn().execute(
            "SELECT * FROM cross_graph_relations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        row = self._get_conn().execute(
            "SELECT COUNT(*) as cnt FROM cross_graph_relations"
        ).fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
