"""Agentic Memory (Phase D5).

对标: Agentic Memory (2025-2026)——记忆直接驱动行动决策

WHY 区别于 EpisodicMemory:
  EpisodicMemory 是事件存储（"发生了什么"）——被动检索。
  AgenticMemory 是行动知识（"遇到 X 时应该做 Y"）——主动驱动决策。

设计:
  - 记忆项: (触发条件, 行动, 结果, 效用分数)
  - 检索: 当前上下文 → 匹配触发条件 → 返回行动建议
  - 反馈: Action 结果 → 更新效用分数 → 强化或削弱记忆
  - 类似于强化学习的 Q-table，但是人类可读的规则形式
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class AgenticMemoryItem:
    """一条行动记忆——"遇到 X 时，做 Y，结果 Z"。"""
    id: str = ""
    trigger: str = ""          # 触发条件描述
    action: str = ""           # 建议的行动
    expected_outcome: str = "" # 预期结果
    utility: float = 0.5       # 效用分数 0-1
    times_triggered: int = 0
    times_succeeded: int = 0
    category: str = ""         # "审计" / "编码" / "测试" / ...
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class AgenticMemory:
    """Agentic Memory——从记忆中驱动行动，而非仅被动检索。

    用法:
        am = AgenticMemory(":memory:")
        am.remember(trigger="应收账款截止性测试", action="先查年末前后5天的发货单",
                     expected_outcome="确认收入是否记录在正确期间", category="审计")
        suggestions = am.suggest("需要做应收账款相关审计程序")
        for item in suggestions:
            print(f"建议: {item.action} (效用: {item.utility})")
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS agentic_memory (
        id TEXT PRIMARY KEY,
        trigger TEXT NOT NULL,
        action TEXT NOT NULL,
        expected_outcome TEXT NOT NULL DEFAULT '',
        utility REAL NOT NULL DEFAULT 0.5,
        times_triggered INTEGER NOT NULL DEFAULT 0,
        times_succeeded INTEGER NOT NULL DEFAULT 0,
        category TEXT NOT NULL DEFAULT '',
        tags TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_am_category ON agentic_memory(category);
    CREATE INDEX IF NOT EXISTS idx_am_utility ON agentic_memory(utility DESC);
    """

    # 语义匹配阈值
    MATCH_THRESHOLD = 0.4

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()

    def remember(
        self, trigger: str, action: str, expected_outcome: str = "",
        category: str = "", utility: float = 0.5, tags: list[str] | None = None,
    ) -> AgenticMemoryItem:
        """记录一条行动记忆。"""
        import hashlib
        mid = hashlib.sha256(f"{trigger}:{action}".encode()).hexdigest()[:16]
        item = AgenticMemoryItem(
            id=mid, trigger=trigger, action=action,
            expected_outcome=expected_outcome, utility=utility,
            category=category, tags=tags or [],
        )
        self._db.execute(
            """INSERT OR REPLACE INTO agentic_memory
               (id, trigger, action, expected_outcome, utility, category, tags, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (item.id, item.trigger, item.action, item.expected_outcome,
             item.utility, item.category,
             json.dumps(item.tags, ensure_ascii=False), item.created_at),
        )
        self._db.commit()
        return item

    def suggest(self, context: str, limit: int = 5, min_utility: float = 0.3) -> list[AgenticMemoryItem]:
        """根据当前上下文建议行动——语义匹配触发条件。

        检索策略:
          1. 精确标签匹配（高优先级）
          2. 语义相似度匹配（中等优先级）
          3. 高效用项兜底
        """
        results: list[tuple[float, AgenticMemoryItem]] = []

        rows = self._db.execute(
            "SELECT * FROM agentic_memory WHERE utility >= ? ORDER BY utility DESC LIMIT 50",
            (min_utility,),
        ).fetchall()

        for row in rows:
            item = self._to_item(row)
            sim = SequenceMatcher(None, context.lower(), item.trigger.lower()).ratio()

            # 标签匹配加分
            tag_bonus = 0.0
            context_lower = context.lower()
            for tag in item.tags:
                if tag.lower() in context_lower:
                    tag_bonus += 0.2

            score = sim + tag_bonus
            if score > self.MATCH_THRESHOLD or item.utility > 0.7:
                results.append((score, item))

        results.sort(key=lambda x: (-x[0], -x[1].utility))
        return [item for _, item in results[:limit]]

    def feedback(self, memory_id: str, success: bool) -> None:
        """反馈——Action 成功→强化，失败→削弱。"""
        delta = 0.1 if success else -0.05
        self._db.execute(
            """UPDATE agentic_memory SET
               times_triggered = times_triggered + 1,
               times_succeeded = times_succeeded + ?,
               utility = MAX(0, MIN(1, utility + ?))
               WHERE id = ?""",
            (1 if success else 0, delta, memory_id),
        )
        self._db.commit()

    def top(self, category: str = "", limit: int = 10) -> list[AgenticMemoryItem]:
        """获取效用最高的记忆——供 system prompt 注入。"""
        if category:
            rows = self._db.execute(
                "SELECT * FROM agentic_memory WHERE category=? AND utility>0 ORDER BY utility DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM agentic_memory WHERE utility>0 ORDER BY utility DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._to_item(r) for r in rows]

    def forget(self, memory_id: str) -> None:
        """删除一条低效用记忆。"""
        self._db.execute("DELETE FROM agentic_memory WHERE id=?", (memory_id,))
        self._db.commit()

    def prune(self, min_utility: float = 0.1) -> int:
        """剪枝——删除效用过低的记忆。"""
        c = self._db.execute(
            "DELETE FROM agentic_memory WHERE utility < ? AND times_triggered > 5",
            (min_utility,),
        )
        self._db.commit()
        return c.rowcount

    def _to_item(self, row: sqlite3.Row) -> AgenticMemoryItem:
        return AgenticMemoryItem(
            id=row["id"], trigger=row["trigger"], action=row["action"],
            expected_outcome=row["expected_outcome"], utility=row["utility"],
            times_triggered=row["times_triggered"],
            times_succeeded=row["times_succeeded"],
            category=row["category"], tags=json.loads(row["tags"]),
            created_at=row["created_at"],
        )

    def close(self) -> None:
        self._db.close()
