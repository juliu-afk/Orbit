"""项目说明书生成器 + 目录分析 单元测试。"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from orbit.brief.generator import BriefGenerator, analyze_directory, _detect_python_framework, _detect_js_framework, BRIEF_SYSTEM_PROMPT
from orbit.brief.models import BriefRecord, ProjectAnalysis, REQUIRED_SECTIONS


class TestAnalyzeDirectory:
    def test_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = analyze_directory(tmpdir)
            assert analysis.file_count == 0
            assert analysis.language == ""

    def test_python_project_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").write_text("[project]\nname='test'")
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src/main.py").write_text("print('hello')")
            Path(tmpdir, "src/models.py").write_text("class User: pass")

            analysis = analyze_directory(tmpdir)
            assert analysis.language == "python"
            assert analysis.file_count >= 2
            assert analysis.python_files >= 2

    def test_typescript_project_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "package.json").write_text('{"name":"test"}')
            Path(tmpdir, "tsconfig.json").write_text("{}")
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src/index.ts").write_text("const x = 1")

            analysis = analyze_directory(tmpdir)
            assert analysis.language == "typescript"

    def test_detect_fastapi(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").write_text("[project]\nname='test'")
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src/api").mkdir()
            Path(tmpdir, "src/api/fastapi_app").mkdir()

            frameworks = _detect_python_framework(
                {"pyproject.toml"},
                {"src/api/fastapi_app"},
            )
            assert "FastAPI" in frameworks

    def test_detect_react(self) -> None:
        frameworks = _detect_js_framework(
            {"package.json"},
            {"vite.config.ts", "src/components/App.tsx", "src/react-app-env.d.ts"},
        )
        assert "Vite" in frameworks
        assert "React" in frameworks

    def test_ignore_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").write_text("")
            Path(tmpdir, "__pycache__").mkdir()
            Path(tmpdir, "__pycache__/cached.pyc").write_text("")
            Path(tmpdir, ".git").mkdir()
            Path(tmpdir, ".git/config").write_text("")
            Path(tmpdir, "node_modules").mkdir()
            Path(tmpdir, "node_modules/pkg.js").write_text("")

            analysis = analyze_directory(tmpdir)
            # __pycache__, .git, node_modules 应被忽略
            assert analysis.file_count == 1  # 只有 pyproject.toml


class TestBriefGenerator:
    @pytest.mark.asyncio
    async def test_generate_with_mock_llm(self) -> None:
        """用 mock LLMClient 测试生成流程。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个简单的项目
            Path(tmpdir, "pyproject.toml").write_text(
                "[project]\nname='test'\ndependencies=['fastapi','sqlalchemy']"
            )
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src/main.py").write_text("from fastapi import FastAPI")

            # Mock LLM
            mock_md = "\n".join(
                f"## {i}. {title}\n{title} 测试内容。\n"
                for i, title in enumerate(REQUIRED_SECTIONS, 1)
            )

            class MockResponse:
                content = mock_md
                model = "openai/glm-5.2"

            class MockLLM:
                async def generate(self, req, task_id, agent_name=""):
                    return MockResponse()

            gen = BriefGenerator(MockLLM())  # type: ignore[arg-type]
            analysis = analyze_directory(tmpdir)
            brief = await gen.generate(tmpdir, analysis=analysis)

            assert brief.is_valid()
            assert brief.project_name == os.path.basename(tmpdir)
            assert brief.project_language == "python"
            assert len(brief.sections) == len(REQUIRED_SECTIONS)
            # 检查内容
            summary = brief.get_section("摘要")
            assert summary is not None
            assert "测试内容" in summary.content

    @pytest.mark.asyncio
    async def test_generate_fills_missing_sections(self) -> None:
        """缺少段落时自动补全。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "pyproject.toml").write_text("[project]")

            # 只返回 3 个段落
            mock_md = """## 1. 摘要\n摘要内容。
## 2. 技术栈\nPython。
## 3. 命令\npytest。"""

            class MockResponse:
                content = mock_md
                model = "openai/glm-5.2"

            class MockLLM:
                async def generate(self, req, task_id, agent_name=""):
                    return MockResponse()

            gen = BriefGenerator(MockLLM())  # type: ignore[arg-type]
            brief = await gen.generate(tmpdir)

            # 应该补全到 6 个段落
            assert brief.is_valid()
            assert len(brief.sections) == len(REQUIRED_SECTIONS)
            # 补全的段落应包含占位文本
            filled = brief.get_section("目录结构")
            assert filled is not None
            assert "待人工补充" in filled.content

    def test_build_prompt_includes_analysis(self) -> None:
        """验证 prompt 包含分析结果。"""
        analysis = ProjectAnalysis(
            language="python",
            framework="fastapi",
            file_count=10,
            key_files=["pyproject.toml", "src/main.py"],
            dependencies=["fastapi", "pydantic"],
            directory_tree="root/\n  src/\n    main.py",
        )

        class MockLLM:
            pass

        gen = BriefGenerator(MockLLM())  # type: ignore[arg-type]
        prompt = gen._build_prompt("test-project", analysis)

        assert "test-project" in prompt
        assert "python" in prompt
        assert "fastapi" in prompt
        assert "pyproject.toml" in prompt
        assert "fastapi" in prompt
        assert "pydantic" in prompt

    def test_brief_system_prompt_has_all_sections(self) -> None:
        """系统 prompt 应提及所有 6 个必填段落。"""
        for title in REQUIRED_SECTIONS:
            assert title in BRIEF_SYSTEM_PROMPT, f"缺少段落: {title}"
