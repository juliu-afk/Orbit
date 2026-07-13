"""MMAG 情节与事件记忆层 (Phase B1).

对标: MMAG (Mixed Memory Augmented Generation)——图结构+时序推理的情节记忆

WHY 独立于 MemoryStore:
  MemoryStore 是文件级 CRUD——适合人类阅读，不适合 Agent 推理。
  EpisodicMemory 是图结构存储——关键事件作为节点，关系作为边，
  支持时序推理（"上次审计调整为什么被否定？→ 因为截止性问题 → 这次注意"）。

设计:
  - SQLite 存储（图结构——节点表 + 边表）
  - 每个事件含 timestamp + importance + tags
  - 关系类型: CAUSED_BY, FOLLOWED_BY, RELATED_TO, CONTRADICTS
  - per-task_id 隔离（不跨客户泄漏）
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import structlog

logger = structlog.get_logger("orbit.memory.episodic")


class EventImportance(StrEnum):
    CRITICAL = "critical"   # 导致任务失败/回滚的事件
    HIGH = "high"           # 重要决策点
    MEDIUM = "medium"       # 普通事件
    LOW = "low"             # 背景事件


class RelationType(StrEnum):
    CAUSED_BY = "caused_by"         # A 由 B 导致
    FOLLOWED_BY = "followed_by"     # A 之后是 B（时序）
    RELATED_TO = "related_to"       # A 与 B 相关
    CONTRADICTS = "contradicts"     # A 与 B 矛盾


@dataclass
class EpisodicEvent:
    """情节记忆中的一个事件节点。"""
    id: str = ""
    task_id: str = ""
    agent_role: str = ""
    title: str = ""                    # 一句话摘要
    description: str = ""              # 详细描述
    importance: EventImportance = EventImportance.MEDIUM
    outcome: str = ""                  # "success" / "failure" / "partial"
    tags: list[str] = field(default_factory=list)
    context_snapshot: dict = field(default_factory=dict)  # 当时的上下文快照
    timestamp: float = field(default_factory=time.time)


@dataclass
class EpisodicRelation:
    """两个事件之间的关系边。"""
    source_id: str
    target_id: str
    relation_type: RelationType
    weight: float = 1.0
    description: str = ""


class EpisodicMemory:
    """情节记忆——图结构的事件存储与检索。

    用法:
        em = EpisodicMemory(":memory:")  # 或 "path/to/memory.db"
        event = em.record_event(
            task_id="task_123", title="审计调整被否定",
            description="应收账款坏账调整因截止性问题被否定",
            importance=EventImportance.CRITICAL, outcome="failure",
            tags=["audit", "AR", "cutoff"]
        )
        related = em.find_related(event.id, relation=RelationType.CAUSED_BY)
        timeline = em.get_timeline(task_id="task_123")
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS episodic_events (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        agent_role TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        importance TEXT NOT NULL DEFAULT 'medium',
        outcome TEXT NOT NULL DEFAULT '',
        tags TEXT NOT NULL DEFAULT '[]',
        context_snapshot TEXT NOT NULL DEFAULT '{}',
        timestamp REAL NOT NULL,
        created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
    );
    CREATE INDEX IF NOT EXISTS idx_ep_task ON episodic_events(task_id);
    CREATE INDEX IF NOT EXISTS idx_ep_importance ON episodic_events(importance);
    CREATE INDEX IF NOT EXISTS idx_ep_timestamp ON episodic_events(timestamp);

    CREATE TABLE IF NOT EXISTS episodic_relations (
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        weight REAL NOT NULL DEFAULT 1.0,
        description TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
        PRIMARY KEY (source_id, target_id, relation_type),
        FOREIGN KEY (source_id) REFERENCES episodic_events(id),
        FOREIGN KEY (target_id) REFERENCES episodic_events(id)
    );
    CREATE INDEX IF NOT EXISTS idx_ep_rel_source ON episodic_relations(source_id);
    CREATE INDEX IF NOT EXISTS idx_ep_rel_target ON episodic_relations(target_id);
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()

    # ── 写入 ──────────────────────────────────────────

    def record_event(
        self,
        task_id: str,
        title: str,
        description: str = "",
        agent_role: str = "",
        importance: EventImportance = EventImportance.MEDIUM,
        outcome: str = "",
        tags: list[str] | None = None,
        context_snapshot: dict | None = None,
    ) -> EpisodicEvent:
        """记录一个新事件。"""
        event_id = _make_id(task_id, title)
        event = EpisodicEvent(
            id=event_id, task_id=task_id, agent_role=agent_role,
            title=title, description=description, importance=importance,
            outcome=outcome, tags=tags or [],
            context_snapshot=context_snapshot or {},
        )
        self._db.execute(
            """INSERT OR REPLACE INTO episodic_events
               (id, task_id, agent_role, title, description, importance, outcome, tags, context_snapshot, timestamp)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (event.id, event.task_id, event.agent_role, event.title,
             event.description, event.importance.value, event.outcome,
             json.dumps(event.tags, ensure_ascii=False),
             json.dumps(event.context_snapshot, ensure_ascii=False),
             event.timestamp),
        )
        self._db.commit()
        return event

    def add_relation(
        self, source_id: str, target_id: str,
        relation_type: RelationType, weight: float = 1.0, description: str = "",
    ) -> None:
        """添加两个事件之间的关系边。"""
        self._db.execute(
            """INSERT OR REPLACE INTO episodic_relations
               (source_id, target_id, relation_type, weight, description)
               VALUES (?,?,?,?,?)""",
            (source_id, target_id, relation_type.value, weight, description),
        )
        self._db.commit()

    # ── 读取 ──────────────────────────────────────────

    def get_timeline(self, task_id: str, limit: int = 50) -> list[EpisodicEvent]:
        """获取某个任务的事件时间线——按时间排序。"""
        rows = self._db.execute(
            """SELECT * FROM episodic_events
               WHERE task_id = ? ORDER BY timestamp ASC LIMIT ?""",
            (task_id, limit),
        ).fetchall()
        return [_row_to_event(r) for r in rows]

    def find_related(
        self, event_id: str, relation_type: RelationType | None = None,
    ) -> list[EpisodicEvent]:
        """查找与某事件相关的事件——沿关系边遍历。"""
        if relation_type:
            rows = self._db.execute(
                """SELECT e.* FROM episodic_events e
                   INNER JOIN episodic_relations r ON e.id = r.target_id
                   WHERE r.source_id = ? AND r.relation_type = ?""",
                (event_id, relation_type.value),
            ).fetchall()
        else:
            rows = self._db.execute(
                """SELECT e.* FROM episodic_events e
                   INNER JOIN episodic_relations r ON e.id = r.target_id
                   WHERE r.source_id = ?""",
                (event_id,),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def search_by_tags(self, tags: list[str], limit: int = 20) -> list[EpisodicEvent]:
        """按标签搜索事件——用于经验匹配。"""
        placeholders = " OR ".join(["tags LIKE ?" for _ in tags])
        params = [f"%{t}%" for t in tags]
        rows = self._db.execute(
            f"""SELECT * FROM episodic_events
                WHERE ({placeholders}) ORDER BY timestamp DESC LIMIT ?""",
            [*params, limit],
        ).fetchall()
        return [_row_to_event(r) for r in rows]

    def get_critical_events(self, task_id: str = "") -> list[EpisodicEvent]:
        """获取关键事件——用于反思和经验注入。"""
        if task_id:
            rows = self._db.execute(
                """SELECT * FROM episodic_events
                   WHERE task_id = ? AND importance IN ('critical', 'high')
                   ORDER BY timestamp DESC""",
                (task_id,),
            ).fetchall()
        else:
            rows = self._db.execute(
                """SELECT * FROM episodic_events
                   WHERE importance IN ('critical', 'high')
                   ORDER BY timestamp DESC LIMIT 50""",
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def all(self) -> list[EpisodicEvent]:
        """获取所有事件（调试用）。"""
        rows = self._db.execute("SELECT * FROM episodic_events ORDER BY timestamp DESC LIMIT 100").fetchall()
        return [_row_to_event(r) for r in rows]

    # ── 自动提取 (V15.2) ──────────────────────────────

    async def auto_extract(
        self,
        task_id: str,
        execution_trajectory: list[dict],
        llm_client: object = None,
    ) -> list[EpisodicEvent]:
        """从执行轨迹自动提取关键事件——无需手动调用 record_event()。

        只在以下情况记录事件（避免噪音）：
        - 任务失败/异常 → importance=CRITICAL
        - 不可逆决策（检测 [DECISION] 标记） → importance=HIGH
        - 工具调用失败后成功 → importance=MEDIUM
        - 其他 → 跳过

        Args:
            task_id: 任务 ID
            execution_trajectory: 执行轨迹 [{turn, action, result, error}, ...]
            llm_client: LLM 客户端——传入则用 LLM 提炼标题，None 则用启发式规则

        Returns:
            自动记录的事件列表

        WHY 启发式优先: 大部分关键事件（失败/异常）不需要 LLM 就能检测。
        LLM 仅用于提炼事件标题——失败时回退到规则生成的标题。
        """
        events: list[EpisodicEvent] = []
        agent_role = ""

        for idx, turn in enumerate(execution_trajectory):
            if not isinstance(turn, dict):
                continue

            action = str(turn.get("action", ""))
            result = str(turn.get("result", ""))
            error = str(turn.get("error", ""))
            turn_num = turn.get("turn", 0)

            # 检测失败/异常 → CRITICAL
            if error or "failed" in result.lower() or "exception" in result.lower():
                title = f"任务执行异常 (turn {turn_num})"
                desc = f"Action: {action}\nError: {error or result[:200]}"
                if llm_client:
                    try:
                        title = await self._summarize_event(llm_client, action, error or result)
                    except Exception:
                        pass  # LLM 失败→使用默认标题

                event = self.record_event(
                    task_id=task_id,
                    title=title,
                    description=desc[:500],
                    agent_role=agent_role,
                    importance=EventImportance.CRITICAL,
                    outcome="failure",
                    tags=["auto_extracted", "failure"],
                )
                events.append(event)
                continue

            # 检测 [DECISION] 标记 → HIGH
            if "[DECISION]" in action or "[DECISION]" in result:
                event = self.record_event(
                    task_id=task_id,
                    title=f"设计决策 (turn {turn_num})",
                    description=action[:500],
                    agent_role=agent_role,
                    importance=EventImportance.HIGH,
                    outcome="success" if not error else "failure",
                    tags=["auto_extracted", "decision"],
                )
                events.append(event)
                continue

            # 检测工具调用失败后重试成功 → MEDIUM
            prev_turn = execution_trajectory[idx - 1] if idx > 0 else {}
            prev_error = str(prev_turn.get("error", ""))
            if prev_error and not error and "success" in result.lower():
                raw = execution_trajectory[i - 1]
                event = self.record_event(
                    task_id=task_id,
                    title=f"重试后成功 (turn {turn_num})",
                    description=f"失败: {raw.get('error', '')[:200]}\n重试成功",
                    agent_role=agent_role,
                    importance=EventImportance.MEDIUM,
                    outcome="success",
                    tags=["auto_extracted", "retry"],
                )
                events.append(event)

        logger.info(
            "auto_extract_done",
            task_id=task_id,
            trajectory_length=len(execution_trajectory),
            events_extracted=len(events),
        )
        return events

    async def _summarize_event(
        self, llm_client: object, action: str, result: str
    ) -> str:
        """用 LLM 提炼事件标题——失败时返回默认标题。"""
        prompt = (
            "用一句话（≤20字）总结以下 Agent 执行异常：\n"
            f"操作: {action[:200]}\n"
            f"结果: {result[:200]}\n"
            "异常原因:"
        )
        try:
            response = await llm_client.generate(prompt)
            title = str(response).strip()[:50] if response else ""
            return title or "未命名的执行异常"
        except Exception:
            return "未命名的执行异常"

    def close(self) -> None:
        self._db.close()


def _row_to_event(row: sqlite3.Row) -> EpisodicEvent:
    return EpisodicEvent(
        id=row["id"], task_id=row["task_id"], agent_role=row["agent_role"],
        title=row["title"], description=row["description"],
        importance=EventImportance(row["importance"]), outcome=row["outcome"],
        tags=json.loads(row["tags"]), context_snapshot=json.loads(row["context_snapshot"]),
        timestamp=row["timestamp"],
    )


def _make_id(task_id: str, title: str) -> str:
    import hashlib
    return hashlib.sha256(f"{task_id}:{title}:{time.time()}".encode()).hexdigest()[:16]
