"""MMAG 长期用户画像记忆层 (Phase B2).

对标: MMAG 长期用户层——用户画像、偏好、长期目标

WHY 独立于 EpisodicMemory:
  EpisodicMemory 存储事件/经历（"发生了什么"）。
  UserProfile 存储用户特质（"用户是什么样的人"）——跨任务持久化。

设计:
  - per-client 隔离（tenant_id / project_id）
  - 偏好: 沟通风格、决策偏好、节奏容忍度
  - 长期目标: 用户正在推进的长期目标列表
  - 自动从交互中提取（LLM 辅助）或手动录入
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field


@dataclass
class UserProfile:
    """单个用户的长期画像。"""
    profile_id: str = ""           # project_id 或 tenant_id
    display_name: str = ""         # 显示名称
    role: str = ""                 # CFO / 审计合伙人 / FDE / ...
    preferences: dict = field(default_factory=dict)  # 键值对偏好
    goals: list[str] = field(default_factory=list)   # 长期目标列表
    communication_style: str = ""    # 沟通风格描述
    decision_style: str = ""         # 决策偏好描述
    notes: str = ""                  # 自由文本笔记
    updated_at: float = field(default_factory=time.time)


class ProfileStore:
    """用户画像存储——per-client 隔离的偏好与目标。

    用法:
        ps = ProfileStore(":memory:")
        ps.upsert_profile(UserProfile(profile_id="client_001", display_name="张三 CFO"))
        profile = ps.get_profile("client_001")
        ps.set_preference("client_001", "preferred_detail_level", "detailed")
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS user_profiles (
        profile_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT '',
        preferences TEXT NOT NULL DEFAULT '{}',
        goals TEXT NOT NULL DEFAULT '[]',
        communication_style TEXT NOT NULL DEFAULT '',
        decision_style TEXT NOT NULL DEFAULT '',
        notes TEXT NOT NULL DEFAULT '',
        updated_at REAL NOT NULL
    );
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db = sqlite3.connect(db_path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(self.SCHEMA_SQL)
        self._db.commit()

    def upsert_profile(self, profile: UserProfile) -> None:
        """插入或更新用户画像。"""
        profile.updated_at = time.time()
        self._db.execute(
            """INSERT OR REPLACE INTO user_profiles
               (profile_id, display_name, role, preferences, goals,
                communication_style, decision_style, notes, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (profile.profile_id, profile.display_name, profile.role,
             json.dumps(profile.preferences, ensure_ascii=False),
             json.dumps(profile.goals, ensure_ascii=False),
             profile.communication_style, profile.decision_style,
             profile.notes, profile.updated_at),
        )
        self._db.commit()

    def get_profile(self, profile_id: str) -> UserProfile | None:
        """获取用户画像。"""
        row = self._db.execute(
            "SELECT * FROM user_profiles WHERE profile_id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            return None
        return UserProfile(
            profile_id=row["profile_id"], display_name=row["display_name"],
            role=row["role"],
            preferences=json.loads(row["preferences"]),
            goals=json.loads(row["goals"]),
            communication_style=row["communication_style"],
            decision_style=row["decision_style"],
            notes=row["notes"], updated_at=row["updated_at"],
        )

    def set_preference(self, profile_id: str, key: str, value: str) -> None:
        """设置单个偏好——增量更新。"""
        profile = self.get_profile(profile_id)
        if profile is None:
            profile = UserProfile(profile_id=profile_id)
        profile.preferences[key] = value
        self.upsert_profile(profile)

    def add_goal(self, profile_id: str, goal: str) -> None:
        """添加一个长期目标。"""
        profile = self.get_profile(profile_id)
        if profile is None:
            profile = UserProfile(profile_id=profile_id)
        if goal not in profile.goals:
            profile.goals.append(goal)
        self.upsert_profile(profile)

    def get_preference(self, profile_id: str, key: str, default: str = "") -> str:
        """获取单个偏好值。"""
        profile = self.get_profile(profile_id)
        if profile is None:
            return default
        return profile.preferences.get(key, default)

    def all_profiles(self) -> list[UserProfile]:
        """获取所有用户画像（调试用）。"""
        rows = self._db.execute("SELECT * FROM user_profiles ORDER BY updated_at DESC").fetchall()
        return [_row_to_profile(r) for r in rows]

    def close(self) -> None:
        self._db.close()


def _row_to_profile(row: sqlite3.Row) -> UserProfile:
    return UserProfile(
        profile_id=row["profile_id"], display_name=row["display_name"],
        role=row["role"], preferences=json.loads(row["preferences"]),
        goals=json.loads(row["goals"]),
        communication_style=row["communication_style"],
        decision_style=row["decision_style"],
        notes=row["notes"], updated_at=row["updated_at"],
    )
