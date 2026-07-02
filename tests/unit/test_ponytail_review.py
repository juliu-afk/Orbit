"""Ponytail 审查维度 单元测试。"""

from orbit.review.ponytail import (
    PonytailReport,
    PonytailReviewer,
    _check_redundant_wrappers,
    _check_stdlib_replacements,
    _check_unnecessary_abstractions,
)


class TestStdlibReplacements:
    def test_detect_requests(self) -> None:
        content = "import requests\nresp = requests.get('http://example.com')"
        findings = _check_stdlib_replacements(content)
        assert len(findings) > 0
        assert "stdlib" in findings[0][1]

    def test_detect_pytz(self) -> None:
        content = "import pytz\ntz = pytz.timezone('Asia/Shanghai')"
        findings = _check_stdlib_replacements(content)
        assert len(findings) > 0
        assert "zoneinfo" in findings[0][1]

    def test_clean_code_no_findings(self) -> None:
        content = "import json\nfrom pathlib import Path\nfrom datetime import datetime"
        findings = _check_stdlib_replacements(content)
        assert len(findings) == 0


class TestUnnecessaryAbstractions:
    def test_single_method_class(self) -> None:
        content = """class Validator:
    def validate(self, data):
        return True"""
        findings = _check_unnecessary_abstractions(content)
        assert len(findings) > 0
        assert "abstraction" in findings[0][1]

    def test_multi_method_class_no_warning(self) -> None:
        content = """class Validator:
    def validate(self, data):
        return True
    def transform(self, data):
        return data"""
        findings = _check_unnecessary_abstractions(content)
        assert len(findings) == 0  # 两个方法，不警告


class TestRedundantWrappers:
    def test_simple_wrapper(self) -> None:
        content = """def get_name(user):
    return user.name"""
        findings = _check_redundant_wrappers(content)
        assert len(findings) > 0
        assert "wrapper" in findings[0][1]

    def test_multiline_function_no_warning(self) -> None:
        content = """def process(user):
    name = user.name.strip()
    return name.upper()"""
        findings = _check_redundant_wrappers(content)
        assert len(findings) == 0  # 多行，不算包装


class TestPonytailReviewer:
    def test_review_python_file(self) -> None:
        reviewer = PonytailReviewer()
        content = """import requests
import pytz

class SingleMethod:
    def do_it(self):
        return True

def get_name(obj):
    return obj.name
"""
        report = reviewer.review_file("test.py", content)
        # 应该检测到 requests + pytz + 单方法类 + 冗余包装
        assert report.total >= 3
        categories = {f.category for f in report.findings}
        assert "stdlib_replacement" in categories
        assert "unnecessary_abstraction" in categories
        assert "redundant_wrapper" in categories

    def test_review_non_python_skipped(self) -> None:
        reviewer = PonytailReviewer()
        report = reviewer.review_file("test.ts", "import * from 'lodash'")
        assert report.total == 0

    def test_review_clean_code(self) -> None:
        reviewer = PonytailReviewer()
        content = """from pathlib import Path
from datetime import datetime

def process_file(path: Path) -> dict:
    stats = {}
    for f in path.glob("*.txt"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        stats[str(f)] = mtime.isoformat()
    return stats
"""
        report = reviewer.review_file("clean.py", content)
        assert report.total == 0

    def test_review_files_batch(self) -> None:
        reviewer = PonytailReviewer()
        files = {
            "a.py": "import requests\n",
            "b.py": "from pathlib import Path\n",
        }
        report = reviewer.review_files(files)
        assert report.total == 1
        assert report.stats.get("stdlib_replacement", 0) == 1


class TestPonytailReport:
    def test_empty_report(self) -> None:
        report = PonytailReport()
        assert report.total == 0
        assert report.recommendations == []

    def test_report_recommendations(self) -> None:
        from orbit.review.ponytail import PonytailFinding

        f = PonytailFinding(
            file_path="x.py",
            line=1,
            severity="suggestion",
            problem="test problem",
            lazier_alternative="use stdlib",
            category="stdlib_replacement",
        )
        report = PonytailReport(findings=[f], stats={"stdlib_replacement": 1})
        assert report.total == 1
        assert len(report.recommendations) == 1
        assert "x.py:1" in report.recommendations[0]
