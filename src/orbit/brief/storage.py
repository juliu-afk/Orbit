"""读写 .orbit/ 目录下的所有文件。

WHY 集中文件 I/O: generator/checker/injector 不应各自直接操作文件系统，
统一入口方便测试 mock 和路径管理。
"""

from __future__ import annotations

import os
import shutil

import structlog

from orbit.brief.models import BriefRecord

logger = structlog.get_logger("orbit.brief.storage")

ORBIT_DIR = ".orbit"
BRIEF_FILE = "brief.md"
BASE_DIR = "base"
BOUNDARIES_DIR = "boundaries"
RULES_FILE = "rules.yaml"
CONTEXT_FILE = "context.md"


def _ensure_orbit_dir(project_path: str) -> str:
    """确保 .orbit/ 目录存在，返回其绝对路径。"""
    orbit_dir = os.path.join(project_path, ORBIT_DIR)
    os.makedirs(orbit_dir, exist_ok=True)
    return orbit_dir


def read_brief(project_path: str) -> BriefRecord | None:
    """读取 .orbit/brief.md 并解析为 BriefRecord。

    Returns:
        BriefRecord 如果文件存在且解析成功，否则 None
    """
    brief_path = os.path.join(project_path, ORBIT_DIR, BRIEF_FILE)
    if not os.path.isfile(brief_path):
        return None
    try:
        content = brief_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
    except (OSError, UnicodeDecodeError):
        logger.warning("brief_read_failed", path=brief_path)
        return None

    # 从路径提取项目名
    project_name = os.path.basename(project_path.rstrip("/").rstrip("\\"))
    try:
        record = BriefRecord.from_markdown(content, project_name=project_name)
        if not record.is_valid():
            logger.warning("brief_invalid_sections", path=brief_path)
            return None
        return record
    except Exception:
        logger.exception("brief_parse_failed", path=brief_path)
        return None


def write_brief(project_path: str, brief: BriefRecord) -> str:
    """将 BriefRecord 写入 .orbit/brief.md。

    Returns:
        写入的文件绝对路径
    """
    orbit_dir = _ensure_orbit_dir(project_path)
    brief_path = os.path.join(orbit_dir, BRIEF_FILE)
    markdown = brief.to_markdown()
    # WHY 用 Path.write_text: 统一 UTF-8 编码，跨平台一致
    from pathlib import Path

    Path(brief_path).write_text(markdown, encoding="utf-8")
    logger.info("brief_written", path=brief_path, project=brief.project_name)
    return brief_path


def read_context_md(directory: str) -> str | None:
    """读取指定目录下的 .orbit/context.md 内容。

    Args:
        directory: 要检查的目录绝对路径

    Returns:
        文件内容字符串，不存在时返回 None
    """
    context_path = os.path.join(directory, ORBIT_DIR, CONTEXT_FILE)
    if not os.path.isfile(context_path):
        return None
    try:
        from pathlib import Path
        return Path(context_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def write_context_md(directory: str, content: str) -> str:
    """在指定目录下写入 .orbit/context.md。

    Returns:
        写入的文件绝对路径
    """
    orbit_dir = _ensure_orbit_dir(directory)
    context_path = os.path.join(orbit_dir, CONTEXT_FILE)
    from pathlib import Path

    Path(context_path).write_text(content, encoding="utf-8")
    logger.info("context_md_written", path=context_path)
    return context_path


def collect_context_md_hierarchy(target_file: str, project_root: str) -> list[tuple[str, str]]:
    """从目标文件所在目录向上走到项目根，收集所有 .orbit/context.md。

    WHY 按层级收集: 子目录的 context.md 比父目录更具体，注入时最近优先。

    Args:
        target_file: Agent 正在操作的目标文件路径
        project_root: 项目根目录

    Returns:
        [(目录路径, context.md 内容), ...] 列表——从项目根到目标目录排序
    """
    results: list[tuple[str, str]] = []
    # 从目标文件目录向上走到项目根
    current = os.path.dirname(os.path.abspath(target_file))
    project_root = os.path.abspath(project_root)

    while current.startswith(project_root):
        content = read_context_md(current)
        if content:
            results.append((current, content))
        if current == project_root:
            break
        parent = os.path.dirname(current)
        if parent == current:  # 到达文件系统根
            break
        current = parent

    # 反转——项目根优先，子目录在后（Prompt 中后面的覆盖前面的认知）
    results.reverse()
    return results


def generate_base_package(project_path: str, files: dict[str, str]) -> str:
    """将生成的基础代码文件写入 .orbit/base/ 目录。

    WHY 写入 .orbit/ 而非项目根: 基础代码包是参考模板，
    不是直接可运行的代码。Agent 读取后按需复制/调整。

    Args:
        project_path: 项目根目录
        files: {相对路径: 文件内容} 映射

    Returns:
        base 目录的绝对路径
    """
    orbit_dir = _ensure_orbit_dir(project_path)
    base_dir = os.path.join(orbit_dir, BASE_DIR)

    # 清理旧的基础代码包
    if os.path.isdir(base_dir):
        shutil.rmtree(base_dir)

    os.makedirs(base_dir, exist_ok=True)

    for rel_path, content in files.items():
        abs_path = os.path.join(base_dir, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        from pathlib import Path

        Path(abs_path).write_text(content, encoding="utf-8")

    logger.info("base_package_written", path=base_dir, file_count=len(files))
    return base_dir


def write_boundaries(project_path: str, rules_yaml: str) -> str:
    """写入 .orbit/boundaries/rules.yaml。

    Returns:
        写入的文件绝对路径
    """
    orbit_dir = _ensure_orbit_dir(project_path)
    boundaries_dir = os.path.join(orbit_dir, BOUNDARIES_DIR)
    os.makedirs(boundaries_dir, exist_ok=True)
    rules_path = os.path.join(boundaries_dir, RULES_FILE)
    from pathlib import Path

    Path(rules_path).write_text(rules_yaml, encoding="utf-8")
    logger.info("boundaries_written", path=rules_path)
    return rules_path


def read_boundaries(project_path: str) -> str | None:
    """读取 .orbit/boundaries/rules.yaml 内容。"""
    rules_path = os.path.join(project_path, ORBIT_DIR, BOUNDARIES_DIR, RULES_FILE)
    if not os.path.isfile(rules_path):
        return None
    try:
        return rules_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
    except (OSError, UnicodeDecodeError):
        return None
