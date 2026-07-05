"""离线自蒸馏引擎 (Phase C1).

对标: EvolveR (2025)——首个经验驱动自进化框架

WHY 这是 FDE 方法论的工程化:
  Sankar 的"碎石路→高速公路"循环——FDE 在客户现场建碎石路，总部抽象泛化成高速公路。
  DistillationEngine 是这条循环的自动化版本:
    ① 在线交互 → TrajectoryCollector 记录完整轨迹 (Phase B3)
    ② 离线自蒸馏 → DistillationEngine 从轨迹中提炼可复用策略原则 (本模块)
    ③ 经验库维护 → 基于效用分数剪枝与更新
    ④ 策略应用 → 后续 Agent 自动引用相关原则 (注入 system prompt)

设计:
  - 输入: TrajectoryCollector 导出的训练格式 dict
  - 输出: StrategyPrinciple 列表——语义去重 + 效用评分 + 可检索
  - 不依赖 LLM（规则蒸馏优先）——Phase D 可选 LLM 增强
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class StrategyPrinciple:
    """一条可复用的策略原则——从执行轨迹中蒸馏出来的经验。"""
    id: str = ""
    principle: str = ""             # 原则内容："遇到比较类问题时先分别收集两个对象的信息再下结论"
    source_trajectory_id: str = ""  # 来源轨迹
    category: str = ""              # "审计" / "编码" / "测试" / "沟通" / ...
    utility_score: float = 0.0      # 效用分数——越高越好
    times_applied: int = 0          # 被应用次数
    times_succeeded: int = 0         # 应用后成功次数
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class DistillationEngine:
    """离线自蒸馏引擎——从轨迹到策略原则。

    规则蒸馏（当前）:
      - 从失败轨迹中提取错误模式 → "不要 X"
      - 从成功轨迹中提取成功模式 → "优先 Y"
      - 语义去重（相似度 > 0.8 → 合并）

    LLM 蒸馏（Phase D 可选）:
      - 将多条轨迹喂给 LLM → "总结这 5 条成功经验中的共同模式"

    用法:
        de = DistillationEngine("principles.db")
        # 从单条轨迹蒸馏
        principles = de.distill_from_trajectory(traj_data)
        # 批量蒸馏
        principles = de.batch_distill([traj1, traj2, ...])
        # 检索可用的原则
        relevant = de.search("审计 应收账款")
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS strategy_principles (
        id TEXT PRIMARY KEY,
        principle TEXT NOT NULL,
        source_trajectory_id TEXT NOT NULL DEFAULT '',
        category TEXT NOT NULL DEFAULT '',
        utility_score REAL NOT NULL DEFAULT 0.0,
        times_applied INTEGER NOT NULL DEFAULT 0,
        times_succeeded INTEGER NOT NULL DEFAULT 0,
        tags TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sp_category ON strategy_principles(category);
    CREATE INDEX IF NOT EXISTS idx_sp_score ON strategy_principles(utility_score DESC);
    CREATE TABLE IF NOT EXISTS applied_principles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        principle_id TEXT NOT NULL,
        trajectory_id TEXT NOT NULL,
        outcome TEXT NOT NULL DEFAULT '',
        applied_at REAL NOT NULL DEFAULT (strftime('%s','now')),
        FOREIGN KEY (principle_id) REFERENCES strategy_principles(id)
    );
    """

    # 相似度阈值——超过这个值认为两条原则是重复的
    SIMILARITY_THRESHOLD = 0.75

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()

    # ── 蒸馏 ──────────────────────────────────────────

    def distill_from_trajectory(self, traj_data: dict) -> list[StrategyPrinciple]:
        """从单条轨迹中蒸馏策略原则。

        规则:
          - 如果轨迹失败且有 error_message → 提炼"避免"原则
          - 如果轨迹成功且 quality_score > 0.7 → 提炼"复用"原则
          - 检查重复 → 合并或新增
        """
        principles: list[StrategyPrinciple] = []
        traj = traj_data.get("trajectory", traj_data)
        steps = traj_data.get("steps", [])
        final_outcome = traj.get("final_outcome", "")

        category = self._infer_category(traj.get("goal", ""))

        if final_outcome == "failed":
            # 从失败中提炼"避免"原则
            for step in steps:
                err = step.get("error_message", "")
                if err:
                    p = self._add_principle(
                        principle=f"避免: {err[:200]}",
                        source=traj.get("trajectory_id", ""),
                        category=category, initial_score=0.3,
                        tags=["failure", step.get("outcome", "failed")],
                    )
                    if p:
                        principles.append(p)

        elif final_outcome == "completed":
            qs = traj.get("quality_score", 0)
            if qs > 0.6:
                # 从成功中提炼"复用"原则
                action_pattern = self._extract_action_pattern(steps)
                if action_pattern:
                    p = self._add_principle(
                        principle=f"成功模式: {action_pattern}",
                        source=traj.get("trajectory_id", ""),
                        category=category, initial_score=0.5,
                        tags=["success", "pattern"],
                    )
                    if p:
                        principles.append(p)

        return principles

    def batch_distill(self, trajectories: list[dict]) -> list[StrategyPrinciple]:
        """批量蒸馏——从多条轨迹中提炼。"""
        all_principles: list[StrategyPrinciple] = []
        for t in trajectories:
            ps = self.distill_from_trajectory(t)
            all_principles.extend(ps)
        return all_principles

    # ── 检索 ──────────────────────────────────────────

    def search(self, query: str, limit: int = 10) -> list[StrategyPrinciple]:
        """按关键词搜索策略原则——供 system prompt 注入。"""
        terms = query.split()
        conditions = " OR ".join(
            ["principle LIKE ? OR category LIKE ?" for _ in terms]
        )
        params: list[str] = []
        for t in terms:
            params.extend([f"%{t}%", f"%{t}%"])
        rows = self._db.execute(
            f"""SELECT * FROM strategy_principles
                WHERE ({conditions}) AND utility_score > 0.3
                ORDER BY utility_score DESC LIMIT ?""",
            [*params, limit],
        ).fetchall()
        return [_row_to_principle(r) for r in rows]

    def top_principles(self, limit: int = 20) -> list[StrategyPrinciple]:
        """获取效用最高的原则——注入 system prompt。"""
        rows = self._db.execute(
            "SELECT * FROM strategy_principles WHERE utility_score > 0 ORDER BY utility_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_principle(r) for r in rows]

    def apply_feedback(self, principle_id: str, success: bool) -> None:
        """应用反馈——成功+效用，失败-效用。"""
        delta = 0.1 if success else -0.05
        self._db.execute(
            """UPDATE strategy_principles SET
               times_applied = times_applied + 1,
               times_succeeded = times_succeeded + ?,
               utility_score = MAX(0, MIN(1, utility_score + ?))
               WHERE id = ?""",
            (1 if success else 0, delta, principle_id),
        )
        self._db.commit()

    def prune(self, min_score: float = 0.15, min_applied: int = 3) -> int:
        """剪枝——删除效用低且很少被应用的原则。"""
        cursor = self._db.execute(
            """DELETE FROM strategy_principles
               WHERE utility_score < ? AND times_applied < ?""",
            (min_score, min_applied),
        )
        self._db.commit()
        return cursor.rowcount

    # ── 内部 ──────────────────────────────────────────

    def _add_principle(
        self, principle: str, source: str, category: str,
        initial_score: float = 0.5, tags: list[str] | None = None,
    ) -> StrategyPrinciple | None:
        """添加一条原则——检查重复后新增或合并。"""
        # 检查是否与已有原则重复
        existing = self.top_principles(100)
        for old in existing:
            sim = SequenceMatcher(None, principle, old.principle).ratio()
            if sim > self.SIMILARITY_THRESHOLD:
                # 合并：平均分数，增加来源引用
                new_score = (old.utility_score + initial_score) / 2
                self._db.execute(
                    "UPDATE strategy_principles SET utility_score = ?, times_applied = times_applied + 1 WHERE id = ?",
                    (new_score, old.id),
                )
                self._db.commit()
                return None  # 重复，不新增

        # 新原则
        pid = _make_principle_id(principle)
        self._db.execute(
            """INSERT OR REPLACE INTO strategy_principles
               (id, principle, source_trajectory_id, category, utility_score, tags, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (pid, principle, source, category, initial_score,
             json.dumps(tags or [], ensure_ascii=False), time.time()),
        )
        self._db.commit()
        return StrategyPrinciple(
            id=pid, principle=principle, source_trajectory_id=source,
            category=category, utility_score=initial_score, tags=tags or [],
        )

    def _infer_category(self, goal: str) -> str:
        """从目标文本推断类别。"""
        if any(kw in goal for kw in ["审计", "audit", "底稿", "函证"]):
            return "审计"
        if any(kw in goal for kw in ["测试", "test", "pytest", "覆盖率"]):
            return "测试"
        if any(kw in goal for kw in ["编码", "实现", "修复", "bug"]):
            return "编码"
        if any(kw in goal for kw in ["部署", "deploy", "k8s", "docker"]):
            return "部署"
        return "通用"

    def _extract_action_pattern(self, steps: list[dict]) -> str:
        """从步骤中提取动作模式（成功轨迹）。"""
        if not steps:
            return ""
        actions = [s.get("action", "") for s in steps if s.get("action")]
        if len(actions) >= 3:
            return " → ".join(actions[-3:])  # 最近 3 步
        return " → ".join(actions)

    def close(self) -> None:
        self._db.close()


def _row_to_principle(row: sqlite3.Row) -> StrategyPrinciple:
    return StrategyPrinciple(
        id=row["id"], principle=row["principle"],
        source_trajectory_id=row["source_trajectory_id"],
        category=row["category"], utility_score=row["utility_score"],
        times_applied=row["times_applied"],
        times_succeeded=row["times_succeeded"],
        tags=json.loads(row["tags"]), created_at=row["created_at"],
    )


def _make_principle_id(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16]
