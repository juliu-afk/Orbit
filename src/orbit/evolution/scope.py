"""SCOPE 双流记忆 (Phase G2).

对标: SCOPE (arXiv 2512.15374)——Self-evolving Context Optimization via Prompt Evolution
WHY: 当前原则库是单层的，无战术/战略区分。
     SCOPE 分两层:
       - 战术层 (Tactical): 任务特定规则，内存级，任务结束即过期
       - 战略层 (Strategic): 跨任务规则，持久化，自动去重合并
     战略层从战术层自动提炼——高频出现的战术规则升级为战略。

设计:
  - 战术记忆: dict[task_id, list[str]]——per-task 临时规则
  - 战略记忆: SQLite——持久化，去重，效用评分
  - 升级阈值: 同一战术规则在 ≥3 个不同任务中出现 → 升级为战略
  - 自动合并: 语义相似度 > 0.8 → 合并，保留高效用版本
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import structlog

logger = structlog.get_logger("orbit.evolution.scope")


@dataclass
class TacticalRule:
    """战术规则——per-task 临时记忆。"""
    rule: str           # 规则内容
    task_id: str = ""   # 来源任务
    created_at: float = field(default_factory=time.time)


@dataclass
class StrategicRule:
    """战略规则——跨任务持久记忆。"""
    id: str = ""
    rule: str = ""
    utility: float = 0.5
    times_applied: int = 0
    times_succeeded: int = 0
    source_count: int = 0  # 从多少个不同任务提炼而来
    created_at: float = field(default_factory=time.time)


class ScopeMemory:
    """SCOPE 双流记忆——战术+战略自动升级。

    用法:
        scope = ScopeMemory(":memory:")
        scope.add_tactical("task_1", "此API限流10次/分钟")
        scope.add_tactical("task_2", "此API限流10次/分钟")
        scope.add_tactical("task_3", "此API限流10次/分钟")
        # 第3次自动升级为战略规则
        rules = scope.get_strategic("API限流")  # → ["此API限流10次/分钟"]
    """

    # 升级阈值：同一规则在 N 个不同任务中出现
    UPGRADE_THRESHOLD = 3
    # 语义去重阈值
    DEDUP_THRESHOLD = 0.75

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS strategic_rules (
        id TEXT PRIMARY KEY,
        rule TEXT NOT NULL,
        utility REAL NOT NULL DEFAULT 0.5,
        times_applied INTEGER NOT NULL DEFAULT 0,
        times_succeeded INTEGER NOT NULL DEFAULT 0,
        source_count INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sr_utility ON strategic_rules(utility DESC);

    CREATE TABLE IF NOT EXISTS tactical_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        rule TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_tr_task ON tactical_rules(task_id);
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()
        # 内存缓存——战术规则计数（rule_hash → set of task_ids）
        self._tactical_counts: dict[str, set[str]] = {}

    def add_tactical(self, task_id: str, rule: str) -> None:
        """添加一条战术规则——per-task 临时记忆。"""
        rule = rule.strip()
        if not rule:
            return
        self._db.execute(
            "INSERT INTO tactical_rules (task_id, rule, created_at) VALUES (?,?,?)",
            (task_id, rule, time.time()),
        )
        self._db.commit()

        # 计数——是否达到升级阈值
        key = self._rule_hash(rule)
        if key not in self._tactical_counts:
            self._tactical_counts[key] = set()
        self._tactical_counts[key].add(task_id)

        if len(self._tactical_counts[key]) >= self.UPGRADE_THRESHOLD:
            self._upgrade_to_strategic(rule, len(self._tactical_counts[key]))

    def add_strategic(self, rule: str, utility: float = 0.5) -> StrategicRule | None:
        """直接添加战略规则——自动去重。"""
        rule = rule.strip()
        if not rule:
            return None
        existing = self.get_strategic_all()
        for old in existing:
            if SequenceMatcher(None, rule, old.rule).ratio() > self.DEDUP_THRESHOLD:
                # 合并——取高效用版本
                if utility > old.utility:
                    self._db.execute(
                        "UPDATE strategic_rules SET rule=?, utility=?, source_count=source_count+1 WHERE id=?",
                        (rule, utility, old.id),
                    )
                    self._db.commit()
                return None
        sid = hashlib.sha256(rule.encode()).hexdigest()[:16]
        self._db.execute(
            "INSERT INTO strategic_rules (id, rule, utility, created_at) VALUES (?,?,?,?)",
            (sid, rule, utility, time.time()),
        )
        self._db.commit()
        return StrategicRule(id=sid, rule=rule, utility=utility)

    def get_strategic(self, query: str, limit: int = 10) -> list[StrategicRule]:
        """按查询检索战略规则——语义匹配。"""
        rows = self._db.execute(
            "SELECT * FROM strategic_rules WHERE utility > 0 ORDER BY utility DESC LIMIT 100"
        ).fetchall()
        scored: list[tuple[float, StrategicRule]] = []
        for row in rows:
            rule = self._to_strategic(row)
            sim = SequenceMatcher(None, query.lower(), rule.rule.lower()).ratio()
            if sim > 0.3 or rule.utility > 0.7:
                scored.append((sim + rule.utility, rule))
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:limit]]

    def get_strategic_all(self) -> list[StrategicRule]:
        rows = self._db.execute(
            "SELECT * FROM strategic_rules ORDER BY utility DESC LIMIT 200"
        ).fetchall()
        return [self._to_strategic(r) for r in rows]

    def feedback(self, rule_id: str, success: bool) -> None:
        delta = 0.1 if success else -0.05
        self._db.execute(
            """UPDATE strategic_rules SET
               times_applied=times_applied+1,
               times_succeeded=times_succeeded+?,
               utility=MAX(0,MIN(1,utility+?))
               WHERE id=?""",
            (1 if success else 0, delta, rule_id),
        )
        self._db.commit()

    def get_tactical_for_task(self, task_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT rule FROM tactical_rules WHERE task_id=? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()
        return [r["rule"] for r in rows]

    def cleanup_tactical(self, task_id: str) -> None:
        """清理任务的战术规则——任务结束时调用。"""
        self._db.execute("DELETE FROM tactical_rules WHERE task_id=?", (task_id,))
        self._db.commit()

    def _upgrade_to_strategic(self, rule: str, source_count: int) -> None:
        """战术规则升级为战略规则。"""
        self.add_strategic(rule, utility=0.5 + source_count * 0.05)
        logger.info("scope_upgrade", rule=rule[:80], source_count=source_count)

    def _rule_hash(self, rule: str) -> str:
        return hashlib.sha256(rule.lower().strip().encode()).hexdigest()[:12]

    def _to_strategic(self, row: sqlite3.Row) -> StrategicRule:
        return StrategicRule(
            id=row["id"], rule=row["rule"], utility=row["utility"],
            times_applied=row["times_applied"], times_succeeded=row["times_succeeded"],
            source_count=row["source_count"], created_at=row["created_at"],
        )

    def close(self) -> None:
        self._db.close()
