"""Unit tests: ProfileStore — user profile persistence (was 0% coverage, 57 stmts)."""

from __future__ import annotations

import pytest

from orbit.memory.profile import ProfileStore, UserProfile


@pytest.fixture
def store():
    s = ProfileStore(":memory:")
    yield s
    s.close()


# ── upsert + get ─────────────────────────────────────────────────


def test_upsert_and_get(store):
    """upsert → get 往返。"""
    store.upsert_profile(UserProfile(
        profile_id="c1", display_name="张三", role="CFO",
        preferences={"detail": "high"},
        goals=["降本增效"],
    ))
    p = store.get_profile("c1")
    assert p is not None
    assert p.display_name == "张三"
    assert p.role == "CFO"
    assert p.preferences["detail"] == "high"
    assert p.goals == ["降本增效"]


def test_get_nonexistent(store):
    """不存在的 profile → None。"""
    assert store.get_profile("nonexistent") is None


def test_upsert_overwrites(store):
    """同 profile_id upsert → 更新已有记录。"""
    store.upsert_profile(UserProfile(profile_id="c1", display_name="旧名"))
    store.upsert_profile(UserProfile(profile_id="c1", display_name="新名"))
    assert store.get_profile("c1").display_name == "新名"


# ── preferences ──────────────────────────────────────────────────


def test_set_preference_new_profile(store):
    """设置偏好——不存在的 profile → 自动创建。"""
    store.set_preference("c1", "language", "zh-CN")
    p = store.get_profile("c1")
    assert p is not None
    assert p.preferences["language"] == "zh-CN"


def test_set_preference_existing(store):
    """设置偏好——已有 profile → 增量更新。"""
    store.upsert_profile(UserProfile(profile_id="c1", display_name="T"))
    store.set_preference("c1", "theme", "dark")
    store.set_preference("c1", "lang", "en")
    p = store.get_profile("c1")
    assert p.preferences["theme"] == "dark"
    assert p.preferences["lang"] == "en"
    assert p.display_name == "T"  # 其他字段保留


def test_get_preference(store):
    """get_preference——存在/不存在/default。"""
    store.set_preference("c1", "key1", "val1")
    assert store.get_preference("c1", "key1") == "val1"
    assert store.get_preference("c1", "key2") == ""
    assert store.get_preference("c1", "key2", "fallback") == "fallback"
    assert store.get_preference("nonexistent", "any", "d") == "d"


# ── goals ────────────────────────────────────────────────────────


def test_add_goal(store):
    """add_goal——新 profile + 去重。"""
    store.add_goal("c1", "实现 IFRS 转换")
    store.add_goal("c1", "降低运营成本")
    store.add_goal("c1", "实现 IFRS 转换")  # 重复
    p = store.get_profile("c1")
    assert len(p.goals) == 2
    assert "实现 IFRS 转换" in p.goals


# ── all_profiles ─────────────────────────────────────────────────


def test_all_profiles(store):
    """all_profiles 返回所有画像。"""
    store.upsert_profile(UserProfile(profile_id="c1", display_name="A"))
    store.upsert_profile(UserProfile(profile_id="c2", display_name="B"))
    all_p = store.all_profiles()
    assert len(all_p) == 2


def test_all_profiles_empty(store):
    """空 store → 空列表。"""
    assert store.all_profiles() == []


# ── edge cases ───────────────────────────────────────────────────


def test_upsert_empty_profile(store):
    """空画像也可存储。"""
    store.upsert_profile(UserProfile(profile_id="empty"))
    p = store.get_profile("empty")
    assert p is not None
    assert p.display_name == ""
    assert p.preferences == {}
    assert p.goals == []


def test_updated_at_changes(store):
    """每次 upsert 更新 updated_at。"""
    store.upsert_profile(UserProfile(profile_id="c1"))
    t1 = store.get_profile("c1").updated_at
    store.upsert_profile(UserProfile(profile_id="c1", display_name="changed"))
    t2 = store.get_profile("c1").updated_at
    assert t2 >= t1
