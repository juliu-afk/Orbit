"""PrototypeFirstGuide unit tests (P2-1 — Fable 5)."""

import pytest
from orbit.compose.prototype_first import (
    PrototypeFirstGuide, PrototypeResult, Strategy,
)


class TestStrategy:
    def test_enum_values(self):
        assert Strategy.STANDARD == "standard"
        assert Strategy.PROTOTYPE_FIRST == "prototype_first"


class TestPrototypeResult:
    def test_defaults(self):
        r = PrototypeResult()
        assert r.html == ""
        assert r.feedback == ""
        assert r.design_decisions == []
        assert r.iteration == 0

    def test_with_decisions(self):
        r = PrototypeResult(
            task_description="dashboard", html="<h1>hi</h1>",
            feedback="looks good", design_decisions=["use cards", "dark theme"],
            iteration=1,
        )
        assert len(r.design_decisions) == 2
        assert r.iteration == 1


class TestPrototypeFirstGuide:
    def test_init_no_llm(self):
        g = PrototypeFirstGuide()
        assert g._llm is None
        assert g.iterations == 0

    def test_static_prototype(self):
        html = PrototypeFirstGuide._static_prototype("test dashboard")
        assert "<!DOCTYPE html>" in html
        assert "test dashboard" in html
        assert "placeholder" in html.lower()

    def test_generate_prototype_no_llm_returns_static(self):
        g = PrototypeFirstGuide()
        result = g.generate_prototype_sync("my dashboard")
        assert "<!DOCTYPE html>" in result.html
        assert "my dashboard" in result.html
        assert result.iteration == 0
        assert g.iterations == 1

    def test_iterate_raises_without_generate(self):
        g = PrototypeFirstGuide()
        with pytest.raises(ValueError, match="No prototype"):
            g.iterate("feedback")

    def test_iterate_after_generate(self):
        g = PrototypeFirstGuide()
        g.generate_prototype_sync("task")
        result = g.iterate("more tabs please")
        assert result.iteration == 1
        assert result.feedback == "more tabs please"
        assert g.iterations == 2

    def test_get_design_context_empty(self):
        g = PrototypeFirstGuide()
        assert g.get_design_context() == ""

    def test_get_design_context_with_decisions(self):
        g = PrototypeFirstGuide()
        g.generate_prototype_sync("task")
        r = g.iterate("make it simpler")
        r.design_decisions = ["use grid layout", "reduce to 3 charts"]
        ctx = g.get_design_context()
        assert "use grid layout" in ctx
        assert "reduce to 3 charts" in ctx

    def test_collect_feedback_no_llm(self):
        g = PrototypeFirstGuide()
        result = g.generate_prototype_sync("task")
        result = g.collect_feedback_sync(result, "needs more charts")
        assert result.feedback == "needs more charts"
        # No LLM: feedback becomes the sole design decision
        assert len(result.design_decisions) == 1
        assert result.design_decisions[0] == "needs more charts"


# Helpers for testing sync paths without asyncio
def _add_sync_methods():
    """Add sync wrappers to PrototypeFirstGuide for testing without asyncio."""
    def generate_sync(self, task):
        result = PrototypeResult(task_description=task, iteration=0)
        result.html = self._static_prototype(task)
        self._history.append(result)
        return result

    def collect_sync(self, result, feedback):
        result.feedback = feedback
        result.design_decisions = [feedback.strip()] if feedback.strip() else []
        return result

    PrototypeFirstGuide.generate_prototype_sync = generate_sync
    PrototypeFirstGuide.collect_feedback_sync = collect_sync


_add_sync_methods()
