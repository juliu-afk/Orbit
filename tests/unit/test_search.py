"""search.py 测试——grep + glob_files 纯函数 + 边界.

覆盖:
- _set_workspace_root / _resolve_path
- grep: 目录不存在, files_with_matches, count, case_insensitive, 截断
- glob_files: 目录不存在, 隐藏目录跳过, 截断, 目录条目
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orbit.tools.registry import WorkspaceViolationError
from orbit.tools.search import _resolve_path, _set_workspace_root, glob_files, grep

# ── workspace 辅助 ────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_workspace(tmp_path: Path) -> None:
    """每次测试将 workspace 设为 tmp_path."""
    _set_workspace_root(str(tmp_path))
    yield


# ── _resolve_path ─────────────────────────────────────────


def test_resolve_path_valid(tmp_path: Path) -> None:
    """有效路径应在 workspace 内."""
    p = _resolve_path(".")
    assert p == tmp_path.resolve()


def test_resolve_path_nested(tmp_path: Path) -> None:
    """workspace 内的嵌套路径."""
    sub = tmp_path / "sub"
    sub.mkdir()
    p = _resolve_path("sub")
    assert p == tmp_path.resolve() / "sub"


def test_resolve_path_outside_raises(tmp_path: Path) -> None:
    """路径在 workspace 外应抛 WorkspaceViolationError."""
    with pytest.raises(WorkspaceViolationError, match="在工作区外"):
        _resolve_path("..")


# ── grep ──────────────────────────────────────────────────


def _write_files(root: Path) -> None:
    (root / "a.py").write_text("def hello():\n    pass\n", encoding="utf-8")
    (root / "b.py").write_text("HELLO = 42\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "c.txt").write_text("hello world\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_grep_content_mode(tmp_path: Path) -> None:
    """content 模式返回匹配行."""
    _write_files(tmp_path)
    result = await grep("hello", path=".")
    assert "a.py:1: def hello():" in result
    # Windows paths may use backslash
    assert "sub/c.txt:1: hello world" in result or "sub\\c.txt:1: hello world" in result


@pytest.mark.asyncio
async def test_grep_dir_not_exists(tmp_path: Path) -> None:
    """目录不存在返回提示."""
    result = await grep("hello", path="nonexistent")
    assert "目录不存在" in result


@pytest.mark.asyncio
async def test_grep_no_match(tmp_path: Path) -> None:
    """无匹配时返回无匹配信息."""
    _write_files(tmp_path)
    result = await grep("zzzzz", path=".")
    assert "无匹配" in result


@pytest.mark.asyncio
async def test_grep_files_with_matches(tmp_path: Path) -> None:
    """files_with_matches 只返回文件路径."""
    _write_files(tmp_path)
    result = await grep("hello", path=".", output_mode="files_with_matches")
    # 应该只包含路径, 不含行号
    lines = result.strip().split("\n")[1:]  # 去掉 header
    assert len(lines) >= 2
    assert all(":" not in line or line.count(":") < 2 for line in lines)


@pytest.mark.asyncio
async def test_grep_count_mode(tmp_path: Path) -> None:
    """count 模式返回文件:计数."""
    _write_files(tmp_path)
    result = await grep("hello", path=".", output_mode="count")
    lines = result.strip().split("\n")[1:]
    # a.py 匹配 1 次, c.txt 匹配 1 次
    assert any("a.py: 1" in line for line in lines)
    assert any("c.txt: 1" in line for line in lines)


@pytest.mark.asyncio
async def test_grep_case_insensitive(tmp_path: Path) -> None:
    """忽略大小写时 HELLO 匹配 hello."""
    _write_files(tmp_path)
    result = await grep("hello", path=".", case_insensitive=True)
    # b.py 含 HELLO, 大小写不敏感应匹配
    assert "b.py" in result


@pytest.mark.asyncio
<<<<<<< HEAD
async def @pytest.mark.skip(reason="P2-4: needs fixing")
test_grep_truncated(tmp_path: Path) -> None:
=======
async def test_grep_truncated(tmp_path: Path) -> None:
>>>>>>> feat/tests-from-190
    """结果超过 head_limit 应截断."""
    (tmp_path / "big.py").write_text("line0\n" + "\n".join(f"match line {i}" for i in range(100)), encoding="utf-8")
    result = await grep("match", path=".", head_limit=5)
    assert "已截断" in result


@pytest.mark.asyncio
async def test_grep_hidden_file_skipped(tmp_path: Path) -> None:
    """隐藏文件（.开头）跳过."""
    (tmp_path / ".secret").write_text("secret hello\n", encoding="utf-8")
    (tmp_path / "visible.py").write_text("hello\n", encoding="utf-8")
    result = await grep("hello", path=".")
    assert ".secret" not in result


@pytest.mark.asyncio
async def test_grep_glob_filter(tmp_path: Path) -> None:
    """glob 过滤只搜索 .py 文件."""
    _write_files(tmp_path)
    result = await grep("hello", path=".", glob="*.py")
    # c.txt 不是 .py, 应跳过
    assert "c.txt" not in result
    assert "a.py" in result


# ── glob_files ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_glob_files(tmp_path: Path) -> None:
    """基本 glob 匹配."""
    _write_files(tmp_path)
    result = await glob_files("*.py", path=".")
    assert "a.py" in result
    assert "b.py" in result


@pytest.mark.asyncio
async def test_glob_dir_not_exists(tmp_path: Path) -> None:
    """目录不存在返回提示."""
    result = await glob_files("*.py", path="nonexistent")
    assert "目录不存在" in result


@pytest.mark.asyncio
async def test_glob_hidden_parts_skipped(tmp_path: Path) -> None:
    """隐藏目录内的文件跳过."""
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "x.py").write_text("x", encoding="utf-8")
    (tmp_path / "visible.py").write_text("y", encoding="utf-8")
    result = await glob_files("**/*.py", path=".")
    assert "visible.py" in result
    assert ".hidden" not in result


@pytest.mark.asyncio
async def test_glob_node_modules_skipped(tmp_path: Path) -> None:
    """node_modules 目录跳过."""
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "dep.js").write_text("x", encoding="utf-8")
    result = await glob_files("**/*", path=".")
    assert "node_modules" not in result


@pytest.mark.asyncio
async def test_glob_truncated(tmp_path: Path) -> None:
    """结果超过 500 条截断."""
    for i in range(600):
        (tmp_path / f"f{i:04d}.txt").write_text("x", encoding="utf-8")
    result = await glob_files("*", path=".")
    assert "截断" in result


@pytest.mark.asyncio
async def test_glob_directories_marked(tmp_path: Path) -> None:
    """目录条目以 / 结尾."""
    (tmp_path / "mydir").mkdir()
    (tmp_path / "myfile.txt").write_text("x", encoding="utf-8")
    result = await glob_files("*", path=".")
    assert "mydir/" in result
    assert "myfile.txt" in result


@pytest.mark.asyncio
async def test_glob_no_match(tmp_path: Path) -> None:
    """无匹配返回 0 个匹配."""
    result = await glob_files("*.nonexistent", path=".")
    assert "0 个匹配" in result
