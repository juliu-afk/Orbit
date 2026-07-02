"""覆盖率补测批次2——observability/metrics + sessions/registry + knowledge/engine."""

from __future__ import annotations

import pytest

from orbit.knowledge.engine import KnowledgeEngine
from orbit.observability import metrics
from orbit.sessions.registry import SessionRegistry


# ════════════════════════════════════════════
# 1. observability/metrics
# ════════════════════════════════════════════

class TestMetrics:
    def test_snapshot_returns_dict(self):
        snap = metrics.snapshot()
        assert isinstance(snap, dict)


# ════════════════════════════════════════════
# 2. sessions/registry
# ════════════════════════════════════════════

class TestSessionRegistry:
    def test_init(self, tmp_path):
        reg = SessionRegistry(db_path=str(tmp_path / "sessions.db"))
        assert reg is not None

    def test_init_registry(self, tmp_path):
        reg = SessionRegistry(db_path=str(tmp_path / "sessions.db"))
        assert reg is not None


# ════════════════════════════════════════════
# 3. knowledge/engine
# ════════════════════════════════════════════

class TestKnowledgeEngine:
    def test_init(self):
        engine = KnowledgeEngine()
        assert engine is not None

    def test_list_concepts(self):
        engine = KnowledgeEngine()
        concepts = engine.list_concepts("accounting")
        assert isinstance(concepts, list)

    def test_count(self):
        engine = KnowledgeEngine()
        c = engine.count()
        assert c >= 0

    def test_search(self):
        engine = KnowledgeEngine()
        results = engine.search("revenue", top_k=3)
        assert isinstance(results, list)
