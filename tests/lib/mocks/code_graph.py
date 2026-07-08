"""Mock CodeGraphEngine——供消融实验和 L1 测试使用。

WHY mock 而非真实 graph: 消融 benchmark 是独立代码片段，没有完整项目上下文。
Mock engine 知道 Python stdlib + 常见第三方库的符号存在性，
能正确区分"真实存在的符号"和"LLM 幻觉出的符号"。
"""

from __future__ import annotations

# Python 3.14 stdlib 模块（用于 exists() 查询）
_STDLIB_MODULES: frozenset[str] = frozenset({
    "os", "sys", "json", "re", "math", "time", "datetime", "collections",
    "itertools", "functools", "typing", "pathlib", "hashlib", "uuid",
    "asyncio", "subprocess", "logging", "structlog", "argparse", "csv",
    "io", "tempfile", "shutil", "glob", "fnmatch", "random", "statistics",
    "decimal", "fractions", "enum", "dataclasses", "abc", "copy",
    "ast", "textwrap", "string", "unittest", "pytest",
    "sqlite3", "aiosqlite", "orjson", "pydantic", "prometheus_client",
    "aiohttp", "requests", "fastapi", "starlette", "uvicorn",
    "sqlalchemy", "alembic", "asyncpg", "redis",
    "numpy", "pandas", "polars", "openpyxl",
    "yaml", "toml", "base64", "struct", "pickle",
    "types", "inspect", "traceback", "warnings",
    "contextlib", "contextvars", "signal", "atexit",
    "threading", "multiprocessing", "concurrent",
    "http", "urllib", "socket", "ssl", "email",
    "zipfile", "tarfile", "gzip", "bz2", "lzma",
})

_STDLIB_FUNCTIONS: frozenset[str] = frozenset({
    "print", "len", "range", "int", "str", "float", "bool", "list", "dict",
    "set", "tuple", "type", "isinstance", "hasattr", "getattr", "setattr",
    "super", "object", "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "RuntimeError", "NotImplementedError",
    "StopIteration", "None", "True", "False", "open", "iter", "next",
    "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "abs", "sum", "min", "max", "round", "all", "any", "id", "dir",
    "vars", "staticmethod", "classmethod", "property",
    "repr", "hex", "oct", "bin", "chr", "ord", "format", "pow", "divmod",
    "async", "await", "yield", "lambda", "import", "from",
})


class MockCodeGraphEngine:
    """模拟代码图谱引擎——知道 Python stdlib 存在性。

    用途: 消融实验 + L1 测试——区分真实符号 vs LLM 幻觉。
    """

    def __init__(self, extra_symbols: set[str] | None = None) -> None:
        """初始化。

        Args:
            extra_symbols: 额外的已知符号——模拟项目上下文
        """
        self._extra = extra_symbols or set()
        self._exists_calls: list[str] = []  # 记录所有 exists() 调用

    async def exists(self, name: str, symbol_type: str | None = None) -> bool:
        """检查符号是否存在。

        Returns:
            True if name in stdlib modules/functions or extra_symbols
        """
        self._exists_calls.append(name)
        return (
            name in _STDLIB_MODULES
            or name in _STDLIB_FUNCTIONS
            or name in self._extra
        )

    @property
    def call_count(self) -> int:
        """exists() 被调用次数。"""
        return len(self._exists_calls)

    @property
    def queried_symbols(self) -> list[str]:
        """所有被查询的符号列表。"""
        return list(self._exists_calls)
