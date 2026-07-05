"""执行轨迹结构化收集器 (Phase B3).

WHY 存在:
  observability/events 当前的日志是纯文本——供人类阅读，不适合机器学习。
  TrajectoryCollector 将 Agent 执行轨迹结构化为可提炼的训练数据——
  区分成功/失败、标注失败类型、关联任务目标。
  为 Phase C 的 EvolveR 离线自蒸馏准备数据源。

设计:
  - 每个任务产生一条 Trajectory
  - 每个 turn 产生一个 Step（含 thought/action/observation/reflection/outcome）
  - SQLite 存储——支持批量查询和导出
  - per-client 隔离
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from enum import StrEnum


class StepOutcome(StrEnum):
    SUCCESS = "success"            # 步骤成功推进目标
    FAILED = "failed"              # 步骤失败（工具报错）
    DRIFTED = "drifted"            # 步骤偏离目标（ReflAct 检测到）
    REPEATED = "repeated"          # 步骤重复（Monitor 检测到）
    HITL_INTERRUPTED = "hitl_interrupted"  # 被人为干预中断


@dataclass
class TrajectoryStep:
    """单个 ReAct 步骤的结构化记录。"""
    turn: int
    thought: str = ""              # LLM 推理内容（截断）
    action: str = ""               # 工具调用名称
    action_args: dict = field(default_factory=dict)
    observation: str = ""          # 工具返回结果（截断）
    reflection: str = ""           # Reflection 阶段的输出
    outcome: StepOutcome = StepOutcome.SUCCESS
    duration_ms: float = 0.0
    token_count: int = 0
    error_message: str = ""


@dataclass
class Trajectory:
    """单次任务的完整执行轨迹。"""
    trajectory_id: str = ""
    task_id: str = ""
    goal: str = ""                 # 原始目标
    agent_role: str = ""           # Agent 类型
    project_id: str = ""           # per-client 隔离
    steps: list[TrajectoryStep] = field(default_factory=list)
    total_turns: int = 0
    total_tool_calls: int = 0
    final_outcome: str = ""        # "completed" / "failed" / "aborted" / "max_turns"
    quality_score: float = 0.0     # GoalJudge 给出的质量分
    tags: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


class TrajectoryCollector:
    """执行轨迹收集器——结构化存储，为 EvolveR 自蒸馏准备。

    用法:
        tc = TrajectoryCollector("trajectories.db")
        traj = tc.start_trajectory(
            task_id="task_123", goal="审计应收账款",
            agent_role="developer", project_id="client_001"
        )
        tc.add_step(traj, step)
        tc.finish_trajectory(traj, final_outcome="completed", quality_score=0.85)
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS trajectories (
        trajectory_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        goal TEXT NOT NULL DEFAULT '',
        agent_role TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL DEFAULT '',
        total_turns INTEGER NOT NULL DEFAULT 0,
        total_tool_calls INTEGER NOT NULL DEFAULT 0,
        final_outcome TEXT NOT NULL DEFAULT '',
        quality_score REAL NOT NULL DEFAULT 0.0,
        tags TEXT NOT NULL DEFAULT '[]',
        started_at REAL NOT NULL,
        completed_at REAL NOT NULL DEFAULT 0.0
    );
    CREATE INDEX IF NOT EXISTS idx_traj_task ON trajectories(task_id);
    CREATE INDEX IF NOT EXISTS idx_traj_project ON trajectories(project_id);
    CREATE INDEX IF NOT EXISTS idx_traj_outcome ON trajectories(final_outcome);

    CREATE TABLE IF NOT EXISTS trajectory_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trajectory_id TEXT NOT NULL,
        turn INTEGER NOT NULL,
        thought TEXT NOT NULL DEFAULT '',
        action TEXT NOT NULL DEFAULT '',
        action_args TEXT NOT NULL DEFAULT '{}',
        observation TEXT NOT NULL DEFAULT '',
        reflection TEXT NOT NULL DEFAULT '',
        outcome TEXT NOT NULL DEFAULT 'success',
        duration_ms REAL NOT NULL DEFAULT 0.0,
        token_count INTEGER NOT NULL DEFAULT 0,
        error_message TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (trajectory_id) REFERENCES trajectories(trajectory_id)
    );
    CREATE INDEX IF NOT EXISTS idx_tstep_traj ON trajectory_steps(trajectory_id);
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()

    def start_trajectory(
        self, task_id: str, goal: str = "", agent_role: str = "",
        project_id: str = "", tags: list[str] | None = None,
    ) -> Trajectory:
        """开始记录一条新轨迹。"""
        traj_id = _make_traj_id(task_id)
        traj = Trajectory(
            trajectory_id=traj_id, task_id=task_id, goal=goal,
            agent_role=agent_role, project_id=project_id,
            tags=tags or [],
        )
        self._db.execute(
            """INSERT OR REPLACE INTO trajectories
               (trajectory_id, task_id, goal, agent_role, project_id, tags, started_at)
               VALUES (?,?,?,?,?,?,?)""",
            (traj.trajectory_id, traj.task_id, traj.goal, traj.agent_role,
             traj.project_id, json.dumps(traj.tags, ensure_ascii=False),
             traj.started_at),
        )
        self._db.commit()
        return traj

    def add_step(self, trajectory_id: str, step: TrajectoryStep) -> None:
        """添加一个步骤到轨迹。"""
        self._db.execute(
            """INSERT INTO trajectory_steps
               (trajectory_id, turn, thought, action, action_args, observation,
                reflection, outcome, duration_ms, token_count, error_message)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (trajectory_id, step.turn, step.thought[:2000], step.action,
             json.dumps(step.action_args, ensure_ascii=False),
             step.observation[:2000], step.reflection[:500],
             step.outcome.value, step.duration_ms, step.token_count,
             step.error_message),
        )
        self._db.commit()

    def finish_trajectory(
        self, trajectory_id: str, final_outcome: str = "completed",
        quality_score: float = 0.0, total_turns: int = 0,
        total_tool_calls: int = 0,
    ) -> None:
        """标记轨迹完成——写入汇总数据。"""
        now = time.time()
        self._db.execute(
            """UPDATE trajectories SET
               final_outcome=?, quality_score=?, total_turns=?,
               total_tool_calls=?, completed_at=?
               WHERE trajectory_id=?""",
            (final_outcome, quality_score, total_turns, total_tool_calls,
             now, trajectory_id),
        )
        self._db.commit()

    # ── 查询（供 EvolveR 离线蒸馏使用） ──────────────

    def get_completed(self, limit: int = 100) -> list[dict]:
        """获取已完成的轨迹——供离线蒸馏。"""
        rows = self._db.execute(
            """SELECT * FROM trajectories
               WHERE final_outcome = 'completed' AND quality_score > 0
               ORDER BY quality_score DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_steps(self, trajectory_id: str) -> list[dict]:
        """获取某条轨迹的所有步骤。"""
        rows = self._db.execute(
            "SELECT * FROM trajectory_steps WHERE trajectory_id = ? ORDER BY turn",
            (trajectory_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_failed(self, limit: int = 50) -> list[dict]:
        """获取失败的轨迹——供错误模式分析。"""
        rows = self._db.execute(
            """SELECT * FROM trajectories
               WHERE final_outcome IN ('failed', 'aborted', 'max_turns')
               ORDER BY started_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def export_for_training(self, trajectory_id: str) -> dict:
        """导出一条轨迹为训练格式——EvolveR 离线自蒸馏的输入。"""
        traj = self._db.execute(
            "SELECT * FROM trajectories WHERE trajectory_id = ?",
            (trajectory_id,),
        ).fetchone()
        if traj is None:
            return {}
        steps = self.get_steps(trajectory_id)
        return {
            "trajectory": dict(traj),
            "steps": steps,
        }

    def close(self) -> None:
        self._db.close()


def _make_traj_id(task_id: str) -> str:
    import hashlib
    return hashlib.sha256(f"{task_id}:{time.time()}".encode()).hexdigest()[:16]
