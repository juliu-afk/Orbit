"""QuizGenerator unit tests — P3-1: fallback path coverage (Fable 5 P1)."""

import pytest
from orbit.modes.quiz_generator import QuizGenerator, QuizQuestion, QuizResult


class TestQuizGeneratorInit:
    """QuizGenerator initialization and should_trigger."""

    def test_init_no_llm(self):
        g = QuizGenerator()
        assert g._llm is None

    def test_init_with_llm(self):
        g = QuizGenerator(llm="fake")
        assert g._llm == "fake"

    def test_should_trigger_core_module(self):
        assert QuizGenerator.should_trigger(["scheduler/state.py"]) is True
        assert QuizGenerator.should_trigger(["graph/query.py"]) is True
        assert QuizGenerator.should_trigger(["checkpoint/manager.py"]) is True

    def test_should_trigger_non_core(self):
        assert QuizGenerator.should_trigger(["docs/readme.md"]) is False
        assert QuizGenerator.should_trigger(["tests/test_x.py"]) is False

    def test_should_trigger_forced_enabled(self):
        assert QuizGenerator.should_trigger(["docs/x.md"], quiz_enabled=True) is True

    def test_should_trigger_forced_disabled(self):
        assert QuizGenerator.should_trigger(["scheduler/x.py"], quiz_enabled=False) is False

    def test_should_trigger_empty_list(self):
        assert QuizGenerator.should_trigger([]) is False


class TestQuizGenerateFallback:
    """LLM failure / no LLM → empty list fallback."""

    @pytest.mark.asyncio
    async def test_generate_no_llm_returns_empty(self):
        g = QuizGenerator()
        result = await g.generate(diff_text="some diff", impl_notes="notes", task_id="t1")
        assert result == []

    @pytest.mark.asyncio
    async def test_generate_empty_diff_returns_empty(self):
        g = QuizGenerator(llm="fake")
        result = await g.generate(diff_text="", impl_notes="notes", task_id="t1")
        assert result == []

    @pytest.mark.asyncio
    async def test_generate_whitespace_diff_returns_empty(self):
        g = QuizGenerator(llm="fake")
        result = await g.generate(diff_text="   ", impl_notes="notes", task_id="t1")
        assert result == []


class TestQuizRenderFallback:
    """HTML rendering — fallback paths when no questions or no Jinja2."""

    def test_render_empty_questions_returns_fallback(self):
        g = QuizGenerator()
        html = g.render_html([], task_id="t1")
        assert "t1" in html
        # committed version uses Chinese fallback text
        assert "降级" in html or "手动审查" in html or "fallback" in html.lower()

    def test_render_fallback_public(self):
        html = QuizGenerator().render_fallback("t1")
        assert "t1" in html
        assert "降级" in html or "手动审查" in html or "测验" in html

    def test_render_inline_basic(self):
        q = QuizQuestion(
            id=1, statement="Test statement", answer=True,
            explanation="Because X", source_files=["a.py"], category="zhengxuan",
        )
        html = QuizGenerator._render_inline([q], task_id="t1", attempt=1)
        assert "Test statement" in html
        assert "t1" in html
        assert "a.py" in html

    def test_render_inline_multiple_questions(self):
        qs = [
            QuizQuestion(id=i, statement=f"Q{i}", answer=i % 2 == 0,
                         explanation=f"Expl {i}", source_files=[f"f{i}.py"],
                         category="guiyin")
            for i in range(1, 6)
        ]
        html = QuizGenerator._render_inline(qs, task_id="t2", attempt=2)
        assert "Q1" in html
        assert "Q5" in html
        assert "t2" in html


class TestQuizModels:
    """QuizQuestion and QuizResult Pydantic models."""

    def test_quiz_question_valid(self):
        q = QuizQuestion(id=1, statement="S", answer=True, explanation="E")
        assert q.id == 1
        # category default is Chinese: "归因"
        assert "归因" in q.category or "guiyin" in q.category

    def test_quiz_question_invalid_id(self):
        with pytest.raises(Exception):
            QuizQuestion(id=0, statement="S", answer=True, explanation="E")

    def test_quiz_question_empty_statement(self):
        with pytest.raises(Exception):
            QuizQuestion(id=1, statement="", answer=True, explanation="E")

    def test_quiz_result_defaults(self):
        r = QuizResult(task_id="t1")
        assert r.score == 0
        assert r.total == 5
        assert r.passed is False
        assert r.attempt == 1
        assert r.questions == []
        assert r.error == ""

    def test_quiz_result_passed(self):
        r = QuizResult(task_id="t1", score=5, passed=True)
        assert r.passed is True
