"""ANCHOR 对齐护栏 (Phase C2).

对标: ANCHOR 框架——在自进化的各个阶段模拟人类监督并注入反馈

WHY 对齐护栏必须先于自进化:
  Alignment Tipping Process (ATP) 研究揭示——Agent 自进化可能触发对齐崩溃:
    自我利益探索 → 高奖励偏差 → 行为漂移 → 模仿策略扩散 → 集体性错位。
  ANCHOR 护栏在进化的每个阶段注入人工监督检查点——有限监督即可显著缓解安全退化。

设计:
  - 检查点: 蒸馏前 / 蒸馏后 / 策略应用前 / 策略应用后
  - 人工监督: HITL 确认高风险原则 + 效用分数审核 + 自动否决阈值
  - 自动护栏: 关键词黑名单、效用分数上限、类别过滤
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from enum import StrEnum


class AnchorCheckpoint(StrEnum):
    """ANCHOR 检查点——自进化流程中的监督节点。"""
    BEFORE_DISTILL = "before_distill"       # 蒸馏前——轨迹是否适合提炼？
    AFTER_DISTILL = "after_distill"         # 蒸馏后——新原则是否安全？
    BEFORE_APPLY = "before_apply"           # 应用前——此原则是否适合当前场景？
    AFTER_APPLY = "after_apply"             # 应用后——效果如何？需要调整吗？


class SupervisionVerdict(StrEnum):
    APPROVED = "approved"        # 通过
    REJECTED = "rejected"        # 拒绝
    NEEDS_REVIEW = "needs_review"  # 需要人工审查
    MODIFIED = "modified"        # 修改后通过


@dataclass
class SupervisionResult:
    """一次监督审查的结果。"""
    checkpoint: AnchorCheckpoint
    verdict: SupervisionVerdict
    reason: str = ""
    modified_content: str = ""   # 如果 verdict=MODIFIED，这是修改后的内容
    reviewer: str = ""           # "auto" / "human:username"
    timestamp: float = field(default_factory=time.time)


class AnchorGuard:
    """ANCHOR 对齐护栏——在自进化流水线的每个检查点注入监督。

    用法:
        guard = AnchorGuard("anchor.db")

        # 检查点 1: 蒸馏前
        result = guard.check(AnchorCheckpoint.BEFORE_DISTILL, traj_data)
        if result.verdict == SupervisionVerdict.REJECTED:
            continue  # 跳过此轨迹

        # 检查点 2: 蒸馏后——新原则是否安全？
        result = guard.check(AnchorCheckpoint.AFTER_DISTILL, principle)
        if result.verdict == SupervisionVerdict.NEEDS_REVIEW:
            await hitl_manager.request_intervention(...)
    """

    # 自动拒绝的关键词——这些原则不应该被 Agent 学习
    REJECT_KEYWORDS: set[str] = {
        "绕过", "跳过", "忽略", "伪造",
        "hide", "bypass", "skip", "ignore",
        "无视规则", "假装", "冒充", "exploit",
    }

    REJECT_PATTERNS: list[str] = [
        "不要验证", "跳过检查", "忽略错误", "伪造数据",
        "欺骗", "hide from", "pretend", "fake",
        "skip validation", "ignore error",
    ]

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS anchor_supervisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        checkpoint TEXT NOT NULL,
        verdict TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        modified_content TEXT NOT NULL DEFAULT '',
        reviewer TEXT NOT NULL DEFAULT 'auto',
        context TEXT NOT NULL DEFAULT '{}',
        timestamp REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_anchor_checkpoint ON anchor_supervisions(checkpoint);
    CREATE INDEX IF NOT EXISTS idx_anchor_verdict ON anchor_supervisions(verdict);
    CREATE INDEX IF NOT EXISTS idx_anchor_timestamp ON anchor_supervisions(timestamp);

    CREATE TABLE IF NOT EXISTS anchor_rejected_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_type TEXT NOT NULL,
        item_content TEXT NOT NULL,
        reject_reason TEXT NOT NULL,
        timestamp REAL NOT NULL
    );
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()
        self._stats = {
            "total_checks": 0, "approved": 0, "rejected": 0,
            "needs_review": 0, "modified": 0,
        }

    # ── 检查点 ────────────────────────────────────────

    def check_before_distill(self, traj_data: dict) -> SupervisionResult:
        """蒸馏前检查——轨迹是否适合提炼？"""
        traj = traj_data.get("trajectory", traj_data)
        goal = traj.get("goal", "")
        steps = traj_data.get("steps", [])

        # 自动拒绝: 轨迹步数太少（<3 步无学习价值）
        if len(steps) < 3:
            return self._record(
                AnchorCheckpoint.BEFORE_DISTILL,
                SupervisionVerdict.REJECTED,
                reason="轨迹步数太少 (<3)，无学习价值",
                context={"goal": goal, "steps_count": len(steps)},
            )

        # 自动拒绝: 轨迹被人工终止（aborted）
        if traj.get("final_outcome") == "aborted":
            return self._record(
                AnchorCheckpoint.BEFORE_DISTILL,
                SupervisionVerdict.REJECTED,
                reason="轨迹被人为终止，不应提炼",
                context={"goal": goal, "outcome": "aborted"},
            )

        return self._record(
            AnchorCheckpoint.BEFORE_DISTILL,
            SupervisionVerdict.APPROVED,
            reason="轨迹适合提炼",
            context={"goal": goal},
        )

    def check_after_distill(self, principle_text: str) -> SupervisionResult:
        """蒸馏后检查——新提炼的原则是否安全？

        检查顺序: 危险关键词(REJECTED) > 危险模式(REJECTED) > 否定式(NEEDS_REVIEW) > 通过(APPROVED)
        """
        # 优先级 1: 危险关键词 → 自动拒绝
        for kw in self.REJECT_KEYWORDS:
            if kw.lower() in principle_text.lower():
                return self._record(
                    AnchorCheckpoint.AFTER_DISTILL,
                    SupervisionVerdict.REJECTED,
                    reason=f"原则含危险关键词: '{kw}'",
                )

        # 优先级 2: 危险模式 → 自动拒绝
        for pattern in self.REJECT_PATTERNS:
            if pattern.lower() in principle_text.lower():
                return self._record(
                    AnchorCheckpoint.AFTER_DISTILL,
                    SupervisionVerdict.REJECTED,
                    reason=f"原则匹配危险模式: '{pattern}'",
                )

        # 优先级 3: "不要"/"禁止" 开头 → 需要人工审查
        if any(principle_text.strip().startswith(w) for w in ["不要", "禁止", "绝不", "永远不"]):
            return self._record(
                AnchorCheckpoint.AFTER_DISTILL,
                SupervisionVerdict.NEEDS_REVIEW,
                reason="高风险否定式原则——需人工确认",
            )

        # 优先级 4: 通过
        return self._record(
            AnchorCheckpoint.AFTER_DISTILL,
            SupervisionVerdict.APPROVED,
            reason="原则安全，自动通过",
        )

    def check_before_apply(self, principle_text: str, current_goal: str) -> SupervisionResult:
        """应用前检查——此原则是否适合当前场景？"""
        # 检查原则类别与当前目标的匹配度
        category_from_goal = self._infer_category(current_goal)
        principle_category = self._infer_category(principle_text)

        if category_from_goal != principle_category and principle_category != "通用":
            # 类别不匹配——仍然可以应用但标记为 NEEDS_REVIEW
            return self._record(
                AnchorCheckpoint.BEFORE_APPLY,
                SupervisionVerdict.NEEDS_REVIEW,
                reason=f"原则类别({principle_category})与目标类别({category_from_goal})不匹配",
                context={"principle": principle_text[:200], "goal": current_goal[:200]},
            )

        return self._record(
            AnchorCheckpoint.BEFORE_APPLY,
            SupervisionVerdict.APPROVED,
            reason="原则适用当前场景",
            context={"principle": principle_text[:200], "goal": current_goal[:200]},
        )

    # ── 统计 ──────────────────────────────────────────

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    def get_rejected_items(self, limit: int = 20) -> list[dict]:
        """获取被拒绝的项目列表（供审查）。"""
        rows = self._db.execute(
            "SELECT * FROM anchor_rejected_items ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._db.close()

    # ── 内部 ──────────────────────────────────────────

    def _record(
        self, checkpoint: AnchorCheckpoint, verdict: SupervisionVerdict,
        reason: str = "", context: dict | None = None,
    ) -> SupervisionResult:
        """记录一次监督结果。"""
        self._stats["total_checks"] += 1
        self._stats[verdict.value] = self._stats.get(verdict.value, 0) + 1

        # 持久化到 SQLite
        import json
        self._db.execute(
            """INSERT INTO anchor_supervisions
               (checkpoint, verdict, reason, reviewer, context, timestamp)
               VALUES (?,?,?,?,?,?)""",
            (checkpoint.value, verdict.value, reason, "auto",
             json.dumps(context or {}, ensure_ascii=False), time.time()),
        )

        # 被拒绝的项目单独记录——供后续审查
        if verdict == SupervisionVerdict.REJECTED:
            self._db.execute(
                """INSERT INTO anchor_rejected_items
                   (item_type, item_content, reject_reason, timestamp)
                   VALUES (?,?,?,?)""",
                (checkpoint.value, reason[:200], reason, time.time()),
            )

        self._db.commit()
        return SupervisionResult(
            checkpoint=checkpoint, verdict=verdict, reason=reason,
            reviewer="auto",
        )

    def _infer_category(self, text: str) -> str:
        if any(kw in text for kw in ["审计", "audit", "底稿", "函证"]):
            return "审计"
        if any(kw in text for kw in ["测试", "test", "pytest"]):
            return "测试"
        if any(kw in text for kw in ["编码", "实现", "修复", "bug"]):
            return "编码"
        return "通用"
