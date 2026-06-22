"""Step 3.1 代码图谱引擎测试。

覆盖 PRD 验收标准：
- SC1: build_index 正常工作
- SC2: exists 查询
- SC4: get_callers 调用链
- 增量更新
- 语法错误文件跳过
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbit.graph.engines.code_graph import CodeGraphEngine
from orbit.graph.models.nodes import Base


@pytest.fixture
async def session_factory():
    """内存 SQLite 异步 session。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def code_engine(session_factory):
    return CodeGraphEngine(session_factory)


@pytest.mark.asyncio
async def test_build_index_single_file(tmp_path, code_engine):
    """解析单文件提取函数定义。"""
    f = tmp_path / "test.py"
    f.write_text("def add(a, b): return a + b\n", encoding="utf-8")
    count = await code_engine.build_index(str(tmp_path))
    assert count == 1
    assert await code_engine.exists("add") is True
    assert await code_engine.exists("nonexistent") is False


@pytest.mark.asyncio
async def test_build_index_class_and_variable(tmp_path, code_engine):
    """解析类定义和模块级变量。"""
    f = tmp_path / "mod.py"
    f.write_text(
        "MAX_SIZE = 100\nclass Calculator:\n    def compute(self): return 42\n",
        encoding="utf-8",
    )
    await code_engine.build_index(str(tmp_path))
    assert await code_engine.exists("Calculator", "class") is True
    assert await code_engine.exists("compute", "function") is True
    assert await code_engine.exists("MAX_SIZE", "variable") is True


@pytest.mark.asyncio
async def test_get_callers(tmp_path, code_engine):
    """SC4: 调用链——foo 调用 bar，get_callers('bar') 返回含 foo。"""
    f = tmp_path / "caller.py"
    f.write_text("def bar():\n    return 1\n\ndef foo():\n    return bar()\n", encoding="utf-8")
    await code_engine.build_index(str(tmp_path))
    callers = await code_engine.get_callers("bar")
    assert "foo" in callers


@pytest.mark.asyncio
async def test_get_callees(tmp_path, code_engine):
    """get_callees('foo') 返回 bar。"""
    f = tmp_path / "caller.py"
    f.write_text("def bar():\n    return 1\n\ndef foo():\n    return bar()\n", encoding="utf-8")
    await code_engine.build_index(str(tmp_path))
    callees = await code_engine.get_callees("foo")
    assert "bar" in callees


@pytest.mark.asyncio
async def test_incremental_update(tmp_path, code_engine):
    """SC3: 修改文件后增量更新。"""
    f = tmp_path / "mod.py"
    f.write_text("def add(a, b): return a + b\n", encoding="utf-8")
    await code_engine.build_index(str(tmp_path))
    assert await code_engine.exists("add") is True

    # 修改文件：加一个函数
    f.write_text(
        "def add(a, b): return a + b\n\ndef multiply(a, b): return a * b\n",
        encoding="utf-8",
    )
    await code_engine.incremental_update(str(f))
    assert await code_engine.exists("add") is True
    assert await code_engine.exists("multiply") is True


@pytest.mark.asyncio
async def test_syntax_error_file_skipped(tmp_path, code_engine):
    """语法错误文件跳过，不阻断构建。"""
    f = tmp_path / "bad.py"
    f.write_text("def broken(:\n", encoding="utf-8")  # 语法错误
    good = tmp_path / "good.py"
    good.write_text("def ok(): return 1\n", encoding="utf-8")
    count = await code_engine.build_index(str(tmp_path))
    assert count == 1  # 只有 good.py 解析成功
    assert await code_engine.exists("ok") is True


@pytest.mark.asyncio
async def test_multiple_files(tmp_path, code_engine):
    """多文件目录解析。"""
    (tmp_path / "a.py").write_text("def func_a(): return 1\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("def func_b(): return 2\n", encoding="utf-8")
    count = await code_engine.build_index(str(tmp_path))
    assert count == 2
    assert await code_engine.exists("func_a") is True
    assert await code_engine.exists("func_b") is True


@pytest.mark.asyncio
async def test_exists_with_type_filter(tmp_path, code_engine):
    """按类型过滤 exists 查询。"""
    f = tmp_path / "mod.py"
    f.write_text("def add(a, b): return a + b\n", encoding="utf-8")
    await code_engine.build_index(str(tmp_path))
    assert await code_engine.exists("add", "function") is True
    assert await code_engine.exists("add", "class") is False


@pytest.mark.asyncio
async def test_call_chain_multi_level(tmp_path, code_engine):
    """多级调用链：a 调 b，b 调 c。"""
    f = tmp_path / "chain.py"
    f.write_text(
        "def c(): return 1\ndef b(): return c()\ndef a(): return b()\n",
        encoding="utf-8",
    )
    await code_engine.build_index(str(tmp_path))
    assert "b" in await code_engine.get_callers("c")
    assert "a" in await code_engine.get_callers("b")
    assert "c" in await code_engine.get_callees("b")
