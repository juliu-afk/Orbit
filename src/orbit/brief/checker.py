"""检查项目说明书/基础代码包/边界规则是否就绪。

WHY 独立模块: generator/storage/injector 各自职责清晰，checker 作为
统一入口判断"是否需要生成"，避免各模块各自重复判断。
"""

from __future__ import annotations

import os

from orbit.brief.models import BriefStatus


def check_brief(project_path: str) -> BriefStatus:
    """检查项目目录下 .orbit/ 的文件就绪状态。

    Args:
        project_path: 项目根目录的绝对路径

    Returns:
        BriefStatus 包含各项就绪状态的布尔值和路径
    """
    orbit_dir = os.path.join(project_path, ".orbit")
    brief_path = os.path.join(orbit_dir, "brief.md")
    base_path = os.path.join(orbit_dir, "base")
    boundaries_path = os.path.join(orbit_dir, "boundaries", "rules.yaml")

    status = BriefStatus(
        has_brief=os.path.isfile(brief_path),
        has_base_package=os.path.isdir(base_path) and _has_template_files(base_path),
        has_boundaries=os.path.isfile(boundaries_path),
        has_context_md=_any_context_md(project_path),
        brief_path=brief_path,
        base_path=base_path,
        boundaries_path=boundaries_path,
    )
    return status


def is_ready(project_path: str) -> bool:
    """项目说明书全套就绪？——全 True 才返回 True。

    WHY 不强制要求 base_package: 已有大量代码的项目不需要基础代码包。
    """
    status = check_brief(project_path)
    return status.has_brief and status.has_boundaries


def _has_template_files(base_dir: str) -> bool:
    """检查 base 目录是否包含至少一个模板文件。"""
    for root, _dirs, files in os.walk(base_dir):
        for f in files:
            # 排除 manifest.yaml 自身——需要至少一个实际的代码模板
            if f != "manifest.yaml" and not f.startswith("."):
                return True
    return False


def _any_context_md(project_path: str) -> bool:
    """检查项目目录下是否存在任何 .orbit/context.md 文件。"""
    for root, _dirs, files in os.walk(project_path):
        # 只检查 .orbit/ 下的 context.md
        if os.path.basename(root) == ".orbit" and "context.md" in files:
            return True
    return False
