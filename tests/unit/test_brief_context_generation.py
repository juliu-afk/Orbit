"""BriefGenerator CONTEXT.md 批量生成 单元测试。"""

import tempfile
from pathlib import Path

import pytest

from orbit.brief.generator import BriefGenerator
from orbit.brief.models import BriefRecord, REQUIRED_SECTIONS, BriefSection


@pytest.fixture
def mock_brief() -> BriefRecord:
    sections = [BriefSection(title=t, content=f"{t} 测试") for t in REQUIRED_SECTIONS]
    return BriefRecord(
        project_name="TestProject",
        sections=sections,
        project_language="python",
        project_framework="fastapi",
    )


class TestGenerateAllContextMd:
    @pytest.mark.asyncio
    async def test_small_project_skipped(self) -> None:
        """子目录太少 (<3) 时跳过。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "src").mkdir()

            class MockLLM:
                async def generate(self, req, task_id, agent_name=""):
                    raise RuntimeError("should not be called")

            gen = BriefGenerator(MockLLM())  # type: ignore[arg-type]
            mock_brief = BriefRecord(
                project_name="Test",
                sections=[BriefSection(title="摘要", content="test")],
            )
            written = await gen.generate_all_context_md(tmpdir, mock_brief, min_subdirs=3)
            assert written == []  # 只有 1 个目录，不触发

    @pytest.mark.asyncio
    async def test_generates_for_code_dirs(self) -> None:
        """有足够子目录时生成 context.md。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建多个带代码文件的目录
            for d in ["src", "tests", "docs", "scripts"]:
                Path(tmpdir, d).mkdir()
                Path(tmpdir, d, "placeholder.py").write_text("# code")

            call_count = [0]

            class MockResponse:
                content = "此目录包含核心代码。"
                model = "openai/glm-5.2"

            class MockLLM:
                async def generate(self, req, task_id, agent_name=""):
                    call_count[0] += 1
                    return MockResponse()

            gen = BriefGenerator(MockLLM())  # type: ignore[arg-type]
            mock_brief = BriefRecord(
                project_name="Test",
                sections=[BriefSection(title="摘要", content="test")],
                project_language="python",
            )
            written = await gen.generate_all_context_md(tmpdir, mock_brief, min_subdirs=3)

            assert len(written) > 0
            assert call_count[0] > 0  # LLM 被调用过
            # 不超过 5 个（限制）
            assert len(written) <= 5

    @pytest.mark.asyncio
    async def test_ignores_hidden_and_build_dirs(self) -> None:
        """忽略 .git、node_modules 等目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            for d in ["src", "tests", "docs", ".git", "node_modules", "__pycache__"]:
                Path(tmpdir, d).mkdir()
                Path(tmpdir, d, "placeholder.py").write_text("# code")

            class MockLLM:
                async def generate(self, req, task_id, agent_name=""):
                    class R:
                        content = "test context"
                        model = "openai/glm-5.2"
                    return R()

            gen = BriefGenerator(MockLLM())  # type: ignore[arg-type]
            mock_brief = BriefRecord(
                project_name="Test",
                sections=[BriefSection(title="摘要", content="test")],
            )
            written = await gen.generate_all_context_md(tmpdir, mock_brief, min_subdirs=3)

            # 只对 src/tests/docs 生成，.git/node_modules/__pycache__ 应被忽略
            paths = [p.replace("\\", "/") for p in written]
            assert any("src" in p for p in paths)
            assert not any(".git" in p for p in paths)
            assert not any("node_modules" in p for p in paths)
