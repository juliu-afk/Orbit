"""DiagnosticService 单元测试——mypy 输出解析 + 诊断模型。

_parse_mypy_output 是纯函数，用真实 mypy 输出格式验证。
"""

from __future__ import annotations

import pytest

from orbit.lsp.service import DiagnosticService, Diagnostic, DiagnosticSeverity


class TestParseMypyOutput:
    """mypy 输出解析——纯函数，覆盖各种输出格式。"""

    def _parse(self, output: str) -> list[Diagnostic]:
        svc = DiagnosticService("/tmp")
        return svc._parse_mypy_output(output)

    def test_error_with_rule_id(self):
        """标准 mypy 错误格式: file:line:col: error: message [rule-id]"""
        output = "src/main.py:10:5: error: Argument 1 to 'login' has incompatible type 'int'; expected 'str' [arg-type]"
        diags = self._parse(output)
        assert len(diags) == 1
        d = diags[0]
        assert d.file_path == "src/main.py"
        assert d.line == 10
        assert d.column == 5
        assert d.severity == DiagnosticSeverity.ERROR
        assert "incompatible type" in d.message
        assert d.rule_id == "arg-type"

    def test_warning_without_rule_id(self):
        """warning 格式——无 [rule-id] 后缀。"""
        output = "utils.py:42:10: warning: Unused variable 'x'"
        diags = self._parse(output)
        assert len(diags) == 1
        d = diags[0]
        assert d.file_path == "utils.py"
        assert d.line == 42
        assert d.column == 10
        assert d.severity == DiagnosticSeverity.WARNING
        assert d.rule_id is None

    def test_note_with_rule_id(self):
        """note 格式——mypy 的辅助信息。"""
        output = "src/app.py:5:1: note: 'x' defined here [misc]"
        diags = self._parse(output)
        assert len(diags) == 1
        d = diags[0]
        assert d.file_path == "src/app.py"
        assert d.severity == DiagnosticSeverity.INFO
        assert d.rule_id == "misc"

    def test_multiple_lines(self):
        """多行输出——每行一个诊断。"""
        output = (
            "a.py:1:1: error: Missing return statement [return-value]\n"
            "a.py:3:2: warning: Unused import 'os'\n"
            "b.py:10:15: error: Name 'x' is not defined [name-defined]"
        )
        diags = self._parse(output)
        assert len(diags) == 3
        assert diags[0].severity == DiagnosticSeverity.ERROR
        assert diags[1].severity == DiagnosticSeverity.WARNING
        assert diags[2].severity == DiagnosticSeverity.ERROR

    def test_empty_output(self):
        """无 mypy 错误→空列表。"""
        diags = self._parse("")
        assert diags == []

    def test_blank_lines_ignored(self):
        """空行/空白行→跳过。"""
        output = "\n\nsrc/main.py:1:1: error: Syntax error [syntax]\n\n"
        diags = self._parse(output)
        assert len(diags) == 1

    def test_windows_path_with_colon(self):
        """Windows 绝对路径含盘符冒号（如 C:/...）——正则应正确解析。"""
        output = "C:/project/src/main.py:10:5: error: Import error [import]"
        diags = self._parse(output)
        assert len(diags) == 1
        d = diags[0]
        assert d.file_path == "C:/project/src/main.py"
        assert d.line == 10

    def test_non_matching_lines_ignored(self):
        """非 mypy 输出行→跳过。"""
        output = "This is not a mypy output line"
        diags = self._parse(output)
        assert diags == []


class TestDiagnosticModel:
    """Diagnostic/DiagnosticSeverity Pydantic 模型。"""

    def test_severity_enum(self):
        assert DiagnosticSeverity.ERROR.value == "error"
        assert DiagnosticSeverity.WARNING.value == "warning"
        assert DiagnosticSeverity.INFO.value == "info"

    def test_diagnostic_minimal(self):
        d = Diagnostic(
            file_path="test.py",
            line=1,
            column=1,
            severity=DiagnosticSeverity.ERROR,
            message="test error",
        )
        assert d.rule_id is None  # 可选字段默认 None

    def test_diagnostic_full(self):
        d = Diagnostic(
            file_path="test.py",
            line=10,
            column=5,
            severity=DiagnosticSeverity.WARNING,
            message="unused variable",
            rule_id="unused-var",
        )
        assert d.rule_id == "unused-var"
