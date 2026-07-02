"""Ponytail 债务台账 单元测试。"""

import tempfile
from pathlib import Path

from orbit.api.routes.ponytail_debt import _scan_ponytail_comments, PONYTAIL_PATTERN


class TestPonytailPattern:
    def test_python_comment(self) -> None:
        match = PONYTAIL_PATTERN.search("# ponytail: no pagination — 升级触发: >50 items")
        assert match is not None
        assert match.group(1).strip() == "no pagination"
        assert match.group(2).strip() == ">50 items"

    def test_python_comment_without_trigger(self) -> None:
        match = PONYTAIL_PATTERN.search("# ponytail: simple cache for <1000 rows")
        assert match is not None
        assert match.group(1).strip() == "simple cache for <1000 rows"
        assert match.group(2) is None  # 无触发条件

    def test_js_comment(self) -> None:
        match = PONYTAIL_PATTERN.search("// ponytail: no SSR -- trigger: SEO needed")
        assert match is not None
        assert match.group(1).strip() == "no SSR"
        assert match.group(2).strip() == "SEO needed"

    def test_html_comment(self) -> None:
        match = PONYTAIL_PATTERN.search("<!-- ponytail: no pagination for <50 items -->")
        assert match is not None
        assert match.group(1).strip() == "no pagination for <50 items"

    def test_no_match(self) -> None:
        match = PONYTAIL_PATTERN.search("# regular comment")
        assert match is None
        match = PONYTAIL_PATTERN.search("// TODO: fix this")
        assert match is None


class TestScanComments:
    def test_scan_empty_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = _scan_ponytail_comments(tmpdir)
            assert entries == []

    def test_scan_with_ponytail_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src/utils.py").write_text(
                '# ponytail: simple cache -- trigger: >1000 rows\ndef cache_data():\n    return {}\n',
                encoding="utf-8",
            )
            Path(tmpdir, "src/app.py").write_text(
                '"""App module."""\n# ponytail: no async needed\n# regular comment\ndef main():\n    pass\n',
                encoding="utf-8",
            )
            entries = _scan_ponytail_comments(tmpdir)

            assert len(entries) == 2
            # 按文件排序验证
            entries.sort(key=lambda e: e["file"])

            assert entries[0]["file"] == "src/app.py"
            assert entries[0]["ceiling"] == "no async needed"
            assert entries[0]["trigger"] == ""

            assert entries[1]["file"] == "src/utils.py"
            assert entries[1]["ceiling"] == "simple cache"
            assert entries[1]["trigger"] == ">1000 rows"

    def test_scan_ignores_non_code_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "README.md").write_text(
                "# ponytail: this is a readme, not code"
            )
            Path(tmpdir, "data.json").write_text(
                '{"ponytail": "not a comment"}'
            )
            entries = _scan_ponytail_comments(tmpdir)
            # .md 和 .json 不在代码文件列表中
            assert entries == []

    def test_scan_ignores_git_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".git").mkdir()
            Path(tmpdir, ".git/hooks").mkdir(parents=True)
            Path(tmpdir, ".git/hooks/pre-commit").write_text(
                "# ponytail: should be ignored\n"
            )
            Path(tmpdir, "src").mkdir()
            Path(tmpdir, "src/main.py").write_text(
                "# ponytail: visible -- trigger: never\n",
                encoding="utf-8",
            )
            entries = _scan_ponytail_comments(tmpdir)
            assert len(entries) == 1
            assert "src/main.py" in entries[0]["file"]

    def test_scan_by_ceiling_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a.py").write_text("# ponytail: X\n")
            Path(tmpdir, "b.py").write_text("# ponytail: X\n")
            Path(tmpdir, "c.py").write_text("# ponytail: Y\n")

            entries = _scan_ponytail_comments(tmpdir)
            assert len(entries) == 3

            by_ceiling: dict[str, int] = {}
            for e in entries:
                c = e["ceiling"] or "未分类"
                by_ceiling[c] = by_ceiling.get(c, 0) + 1

            assert by_ceiling["X"] == 2
            assert by_ceiling["Y"] == 1
