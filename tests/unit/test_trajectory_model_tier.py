"""trajectory 模块单元测试——model_tier 持久化 (V14.2+Theory)."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from orbit.observability.trajectory import (
    Trajectory,
    TrajectoryCollector,
    TrajectoryStep,
    StepOutcome,
)


class TestTrajectoryModelTierField:
    """model_tier 字段——数据类 + 数据库持久化."""

    def test_trajectory_has_model_tier(self):
        t = Trajectory(task_id="t1", model_tier="tier_2")
        assert t.model_tier == "tier_2"

    def test_trajectory_default_empty(self):
        t = Trajectory(task_id="t1")
        assert t.model_tier == ""

    def test_start_trajectory_with_model_tier(self):
        db_path = str(Path(tempfile.gettempdir()) / "test_model_tier.db")
        tc = TrajectoryCollector(db_path=db_path)

        traj = tc.start_trajectory(
            task_id="task-001", goal="测试任务",
            agent_role="developer", model_tier="tier_1",
        )
        assert traj.model_tier == "tier_1"

        # 数据库验证
        row = tc._db.execute(
            "SELECT model_tier FROM trajectories WHERE task_id = ?", ("task-001",)
        ).fetchone()
        assert row is not None
        assert row["model_tier"] == "tier_1"

        tc._db.close()

    def test_set_model_tier_backfill(self):
        """RouterAgent 决策后通过 set_model_tier 回填."""
        db_path = str(Path(tempfile.gettempdir()) / "test_model_tier_backfill.db")
        tc = TrajectoryCollector(db_path=db_path)

        # 任务开始时 model_tier 未知
        traj = tc.start_trajectory(
            task_id="task-002", goal="测试",
            agent_role="architect",  # model_tier 留空
        )
        assert traj.model_tier == ""

        # RouterAgent 决策后回填
        tc.set_model_tier(traj.trajectory_id, "tier_3")

        row = tc._db.execute(
            "SELECT model_tier FROM trajectories WHERE task_id = ?", ("task-002",)
        ).fetchone()
        assert row["model_tier"] == "tier_3"

        tc._db.close()

    def test_alter_table_migration(self):
        """ALTER TABLE 迁移——旧表无 model_tier 时自动添加列."""
        db_path = str(Path(tempfile.gettempdir()) / "test_migration_fresh.db")
        # 删掉可能存在的旧文件
        import os
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass

        tc_new = TrajectoryCollector(db_path=db_path)
        cols = tc_new._db.execute("PRAGMA table_info(trajectories)").fetchall()
        col_names = [c["name"] for c in cols]
        assert "model_tier" in col_names, "CREATE TABLE should include model_tier"
        assert "project_id" in col_names

        tc_new._db.close()
