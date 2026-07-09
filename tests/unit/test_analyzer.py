"""analyzer.py coverage - directory analysis."""
from __future__ import annotations

import tempfile
from pathlib import Path

from orbit.brief.analyzer import analyze_directory, _detect_python_framework, _detect_js_framework


class TestAnalyzeDirectory:
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            result = analyze_directory(d)
            assert result.file_count == 0

    def test_nonexistent_dir(self):
        result = analyze_directory("/nonexistent/path/xyz")
        assert result.file_count == 0

    def test_python_project(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "pyproject.toml").write_text("[project]\nname='test'")
            Path(d, "src").mkdir()
            Path(d, "src/main.py").write_text("print('hello')")
            result = analyze_directory(d)
            assert result.file_count >= 2
            assert result.language == "python"

    def test_typescript_project(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "package.json").write_text('{"name":"test"}')
            Path(d, "tsconfig.json").write_text("{}")
            Path(d, "src").mkdir()
            Path(d, "src/index.ts").write_text("export {}")
            result = analyze_directory(d)
            assert result.file_count >= 3


class TestDetectFrameworks:
    def test_python_fastapi(self):
        assert "FastAPI" in _detect_python_framework(["fastapi==0.110.0"])

    def test_python_flask(self):
        assert "Flask" in _detect_python_framework(["flask==2.0"])

    def test_python_django(self):
        assert "Django" in _detect_python_framework(["django==5.0"])

    def test_python_unknown(self):
        result = _detect_python_framework(["some-random-lib==1.0"])
        # 未知依赖 → 返回空字符串，无匹配框架
        assert result == ""

    def test_js_react(self):
        assert "React" in _detect_js_framework(["react"], {"react": "^18.0"})

    def test_js_vue(self):
        assert "Vue" in _detect_js_framework(["vue"], {"vue": "^3.0"})

    def test_js_unknown(self):
        result = _detect_js_framework(["some-lib"], {})
        # 未知依赖 → 返回空字符串，无匹配框架
        assert result == ""
