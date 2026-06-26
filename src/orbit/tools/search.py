"""搜索工具——grep / glob (并发安全).

对标: Claude Code Grep / Glob 工具
     + OpenCode 20 tools 中的 search 类
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from orbit.tools.registry import get_registry, WorkspaceViolationError

# workspace 根目录
_WORKSPACE_ROOT = Path.cwd().resolve()


def _set_workspace_root(path: str | Path) -> None:
    """设置工作区根目录."""
    global _WORKSPACE_ROOT
    _WORKSPACE_ROOT = Path(path).resolve()


def _resolve_path(path: str) -> Path:
    """解析路径——限定在 workspace 内."""
    p = (_WORKSPACE_ROOT / path).resolve()
    try:
        p.relative_to(_WORKSPACE_ROOT)
    except ValueError:
        raise WorkspaceViolationError(
            f"路径 '{path}' 在工作区外 (workspace: {_WORKSPACE_ROOT})"
        )
    return p


# ── grep ─────────────────────────────────────────────────


async def grep(
    pattern: str,
    path: str = ".",
    glob: str = "*",
    output_mode: str = "content",
    head_limit: int = 100,
    case_insensitive: bool = False,
) -> str:
    """内容搜索——内置实现，不依赖外部 rg.

    Args:
        pattern: 搜索模式 (子字符串匹配)
        path: 搜索目录
        glob: 文件过滤 (e.g. "*.py", "*.{ts,tsx}")
        output_mode: "content" | "files_with_matches" | "count"
        head_limit: 最大输出行数
        case_insensitive: 忽略大小写
    """
    search_root = _resolve_path(path)
    if not search_root.exists():
        return f"目录不存在: {path}"

    search_pattern = pattern.lower() if case_insensitive else pattern
    matches: list[str] = []
    file_count = 0

    # 解析 glob 模式
    glob_parts = glob.split(",") if "," in glob else [glob]

    for root, dirs, files in os.walk(str(search_root)):
        # 跳过隐藏目录和 venv/node_modules
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git", ".venv", "venv")]

        for fname in files:
            if fname.startswith("."):
                continue
            # glob 过滤
            if not any(fnmatch.fnmatch(fname, g.strip()) for g in glob_parts):
                continue

            file_count += 1
            fpath = Path(root) / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            if case_insensitive:
                content_lower = content.lower()
                if search_pattern not in content_lower:
                    continue
            elif search_pattern not in content:
                continue

            if output_mode == "files_with_matches":
                matches.append(str(fpath.relative_to(search_root)))
            elif output_mode == "count":
                count = content_lower.count(search_pattern) if case_insensitive else content.count(search_pattern)
                matches.append(f"{fpath.relative_to(search_root)}: {count}")
            else:  # content
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    line_check = line.lower() if case_insensitive else line
                    if search_pattern in line_check:
                        rel = fpath.relative_to(search_root)
                        matches.append(f"{rel}:{i + 1}: {line.strip()[:200]}")
                        if len(matches) >= head_limit:
                            break
                if len(matches) >= head_limit:
                    break

        if len(matches) >= head_limit:
            break

    if not matches:
        total_header = f"# 搜索 '{pattern}' 在 {path}/ ({file_count} 文件) —— 无匹配\n"
        return total_header

    truncated = len(matches) > head_limit
    if truncated:
        matches = matches[:head_limit]

    header = (
        f"# 搜索 '{pattern}' 在 {path}/ ({file_count} 文件)"
        f" —— {len(matches)} 个结果{' (已截断)' if truncated else ''}\n"
    )
    return header + "\n".join(matches)


# ── glob ─────────────────────────────────────────────────


async def glob_files(
    pattern: str,
    path: str = ".",
) -> str:
    """文件模式匹配——返回匹配的文件路径列表.

    Args:
        pattern: glob 模式 (e.g. "**/*.py", "src/**/*.ts")
        path: 搜索根目录
    """
    search_root = _resolve_path(path)
    if not search_root.exists():
        return f"目录不存在: {path}"

    matches = []
    for p in search_root.rglob(pattern):
        if p.name.startswith("."):
            continue
        if any(part.startswith(".") for part in p.parts):
            continue
        if any(x in p.parts for x in ("node_modules", "__pycache__", ".git", ".venv", "venv")):
            continue
        rel = p.relative_to(search_root)
        if p.is_dir():
            matches.append(f"{rel}/")
        else:
            matches.append(str(rel))

    # 排序——目录在前，文件在后
    matches.sort(key=lambda x: (0 if x.endswith("/") else 1, x))

    header = f"# glob '{pattern}' 在 {path}/ —— {len(matches)} 个匹配\n"
    # 截断过大的结果
    if len(matches) > 500:
        return header + "\n".join(matches[:500]) + f"\n... (截断 {len(matches) - 500} 个结果)"

    return header + "\n".join(matches)


# ── AST 自注册 ──────────────────────────────────────────

registry = get_registry()
registry.register_tool(
    name="grep",
    toolset="search",
    schema={
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "在文件中搜索匹配的文本模式。返回文件名:行号:内容。"
                "支持文件过滤 (glob)、大小写忽略、输出模式切换。"
                "用于查找函数定义、变量使用、错误信息等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式 (子字符串匹配)",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索目录，默认当前目录",
                        "default": ".",
                    },
                    "glob": {
                        "type": "string",
                        "description": "文件过滤 (e.g. '*.py', '*.{ts,tsx}')，默认 '*'",
                        "default": "*",
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": "输出模式: content(匹配行)/files_with_matches(文件路径)/count(计数)",
                        "default": "content",
                    },
                    "head_limit": {
                        "type": "integer",
                        "description": "最大输出行数，默认 100",
                        "default": 100,
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "忽略大小写",
                        "default": False,
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    handler=grep,
    concurrency="safe",
)

registry.register_tool(
    name="glob",
    toolset="search",
    schema={
        "type": "function",
        "function": {
            "name": "glob",
            "description": (
                "文件模式匹配——查找匹配 glob 模式的所有文件。"
                "用于浏览项目结构、找到特定类型文件等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "glob 模式 (e.g. '**/*.py', 'src/**/*.ts')",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索根目录，默认当前目录",
                        "default": ".",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    handler=glob_files,
    concurrency="safe",
)
