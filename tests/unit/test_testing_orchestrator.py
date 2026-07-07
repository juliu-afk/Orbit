"""testing/orchestrator.py 单元测试——非 async 方法。

Phase 1: 测试 _merge_test_code / _static_review_fallback 等同步方法。
Phase 2: async 方法需要 sandbox mock 基础设施。
"""

from __future__ import annotations

from orbit.testing.orchestrator import TestOrchestrator
from orbit.testing.strategies.intention_driven import GeneratedTest


class TestMergeTestCode:
    """_merge_test_code 合并多个 GeneratedTest 为可执行代码。"""

    def test_merges_single_test(self):
        orch = TestOrchestrator()
        tests = [GeneratedTest(
            name="test_foo", code="def test_foo(): pass",
            target="foo", type="positive",
        )]
        result = orch._merge_test_code(tests)
        assert "import pytest" in result
        assert "def test_foo(): pass" in result

    def test_merges_multiple_tests(self):
        orch = TestOrchestrator()
        tests = [
            GeneratedTest(name="t1", code="def test_a(): pass", target="x", type="positive"),
            GeneratedTest(name="t2", code="def test_b(): pass", target="x", type="negative"),
            GeneratedTest(name="t3", code="def test_c(): pass", target="x", type="edge"),
        ]
        result = orch._merge_test_code(tests)
        assert result.count("def test_") == 3
        assert "import pytest" in result

    def test_empty_tests(self):
        orch = TestOrchestrator()
        result = orch._merge_test_code([])
        assert result == "import pytest\n\n"


class TestStaticReviewFallback:
    """_static_review_fallback——审查不可用时的静态兜底。"""

    def test_clean_code_no_issues(self):
        orch = TestOrchestrator()
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        result = orch._static_review_fallback(code, "math_utils")
        assert result["source"] == "static_fallback"
        assert len(result["issues"]) == 0

    def test_detects_hardcoded_secret(self):
        orch = TestOrchestrator()
        code = 'API_KEY = "sk-1234567890abcdef"\n'
        result = orch._static_review_fallback(code, "config")
        assert len(result["issues"]) >= 1
        assert any("密钥" in i["message"] for i in result["issues"])

    def test_detects_eval_usage(self):
        orch = TestOrchestrator()
        code = "result = eval(user_input)\n"
        result = orch._static_review_fallback(code, "dangerous")
        assert len(result["issues"]) >= 1
        assert any("eval" in i["message"] for i in result["issues"])

    def test_detects_os_system(self):
        orch = TestOrchestrator()
        code = 'os.system("rm -rf /")\n'
        result = orch._static_review_fallback(code, "dangerous")
        issues = result["issues"]
        # os.system may trigger the eval warning too since os.system uses system()
        assert any("os.system" in i.get("message", "") for i in issues)

    def test_detects_syntax_error(self):
        orch = TestOrchestrator()
        code = "def broken( "
        result = orch._static_review_fallback(code, "broken")
        assert any("语法错误" in i["message"] for i in result["issues"])

    def test_detects_no_functions(self):
        orch = TestOrchestrator()
        code = "x = 1\ny = 2\n"
        result = orch._static_review_fallback(code, "constants")
        assert any("未定义函数" in i["message"] for i in result["issues"])

    def test_private_key_detection(self):
        orch = TestOrchestrator()
        code = "key = '-----BEGIN RSA PRIVATE KEY-----'\n"
        result = orch._static_review_fallback(code, "leaked")
        assert any("私钥" in i["message"] for i in result["issues"])

    def test_password_detection_varies(self):
        """password='short' 不应误报（< 8 字符）。"""
        orch = TestOrchestrator()
        code = "password = 'short'\n"
        result = orch._static_review_fallback(code, "config")
        # 'short' is only 5 chars, the regex requires ≥8 chars after =
        # Actually the pattern is [^"\']{8,} so "short" = 5 chars, won't match
        assert not any("密钥" in i["message"] for i in result["issues"])

    def test_subprocess_detection(self):
        orch = TestOrchestrator()
        code = "subprocess.call(['ls', '-la'])\n"
        result = orch._static_review_fallback(code, "shell")
        assert any("subprocess" in i["message"] for i in result["issues"])
