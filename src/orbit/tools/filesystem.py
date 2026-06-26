"""文件系统工具——read_file / write_file / edit_file.

对标: Claude Code leaked 43 tools 中的 file 操作
     + OpenClaw wrapToolWorkspaceRootGuard() workspace 边界保护
"""

from __future__ import annotations

import os
from pathlib import Path

from orbit.tools.registry import WorkspaceViolationError, get_registry

# workspace 根目录——文件操作不能越界
_WORKSPACE_ROOT = Path.cwd().resolve()


def set_workspace_root(path: str | Path) -> None:
    """设置工作区根目录——供调度器初始化时调用."""
    global _WORKSPACE_ROOT
    _WORKSPACE_ROOT = Path(path).resolve()


def _guard_path(path: str) -> Path:
    """路径安全守卫——resolve 后必须在 workspace 内.

    对标 OpenClaw wrapToolWorkspaceRootGuard():
    拒绝绝对路径越界、../ 穿透、符号链接逃逸。
    """
    p = (_WORKSPACE_ROOT / path).resolve()
    try:
        p.relative_to(_WORKSPACE_ROOT)
    except ValueError:
        raise WorkspaceViolationError(
            f"路径 '{path}' 在工作区外 (workspace: {_WORKSPACE_ROOT})"
        )
    return p


# ── read_file ────────────────────────────────────────────


async def read_file(path: str, offset: int = 0, limit: int = 200) -> str:
    """读取文件内容——指定行范围.

    Args:
        path: 相对于 workspace 的文件路径
        offset: 起始行号 (0-indexed)
        limit: 最大行数
    """
    p = _guard_path(path)
    if not p.exists():
        return f"文件不存在: {path}"
    if p.is_dir():
        return f"'{path}' 是目录，不是文件"

    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    end = min(offset + limit, total)
    selected = lines[offset:end]

    result = "\n".join(
        f"{i + 1:>6}\t{line}" for i, line in enumerate(selected, start=offset)
    )
    header = f"# {path} (行 {offset + 1}-{end} / 共 {total} 行)\n"
    return header + result


# ── write_file ───────────────────────────────────────────


async def write_file(path: str, content: str) -> str:
    """写入文件——覆盖已有或创建新文件.

    对标 Claude Code Write tool:
    - 父目录不存在则自动创建
    - 内容以 UTF-8 写入
    """
    p = _guard_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    lines = content.count("\n") + (0 if content.endswith("\n") else 1)
    return f"写入成功: {path} ({len(content)} 字符, {lines} 行)"


# ── edit_file ────────────────────────────────────────────


async def edit_file(
    path: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    """精确字符串替换——对标 Claude Code Edit tool.

    Args:
        path: 文件路径
        old_string: 要替换的文本 (必须唯一匹配)
        new_string: 替换后的文本
        replace_all: 替换所有匹配 (默认只替换一次)

    Raises:
        ValueError: old_string 不唯一或未找到
    """
    p = _guard_path(path)
    if not p.exists():
        return f"文件不存在: {path}"

    content = p.read_text(encoding="utf-8")

    count = content.count(old_string)
    if count == 0:
        return f"未找到匹配文本 (已检查 {len(content)} 字符)"

    if not replace_all and count > 1:
        return (
            f"匹配 {count} 处——old_string 不唯一。"
            "请扩大匹配范围使其唯一，或传 replace_all=true 替换全部。"
        )

    new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    p.write_text(new_content, encoding="utf-8")

    replaced = count if replace_all else 1
    return f"替换成功: {path} ({replaced} 处替换, {len(new_content)} 字符)"


# ── AST 自注册 ──────────────────────────────────────────
# 对标 Hermes: 文件底部 registry.register() 即自动发现

registry = get_registry()
registry.register_tool(
    name="read_file",
    toolset="filesystem",
    schema={
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取文件内容。返回带行号的文本，可指定起始行和行数。"
                "用于查看代码、配置文件、日志等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于工作区的文件路径",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始行号 (0-indexed)，默认 0",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回行数，默认 200",
                        "default": 200,
                    },
                },
                "required": ["path"],
            },
        },
    },
    handler=read_file,
    concurrency="safe",
)

registry.register_tool(
    name="write_file",
    toolset="filesystem",
    schema={
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "创建或覆盖文件。父目录不存在时自动创建。"
                "用于生成代码、配置文件、测试用例等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于工作区的文件路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整内容",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    handler=write_file,
    concurrency="serial",
)

registry.register_tool(
    name="edit_file",
    toolset="filesystem",
    schema={
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "精确字符串替换——找到 old_string 替换为 new_string。"
                "old_string 必须唯一匹配（除非 replace_all=true）。"
                "用于修改代码片段、修改变量名、调整配置等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于工作区的文件路径",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要替换的原文本 (必须精确匹配，含缩进)",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新文本",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换所有匹配 (默认 false，只替换一次)",
                        "default": False,
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    handler=edit_file,
    concurrency="serial",
)
