"""项目说明书模块——公共 API。

模块职责:
- models: 数据结构定义
- checker: 就绪状态检查
- generator: LLM 驱动的说明书生成
- storage: .orbit/ 目录文件读写
- injector: PromptBuilder context 层注入
- boundaries: 五层边界执行体系
- package_library: D盘基础代码包库索检
"""

from orbit.brief.boundaries import DEFAULT_RULES, BoundaryEngine
from orbit.brief.checker import check_brief, is_ready
from orbit.brief.generator import BriefGenerator, analyze_directory
from orbit.brief.injector import format_brief_for_prompt, inject_brief_into_context
from orbit.brief.models import (
    BasePackage,
    BoundaryRule,
    BriefRecord,
    BriefSection,
    BriefStatus,
    PackageDecision,
    ProjectAnalysis,
)
from orbit.brief.package_library import DEFAULT_LIBRARY_PATH, PackageLibrary
from orbit.brief.storage import (
    collect_context_md_hierarchy,
    generate_base_package,
    read_brief,
    read_boundaries,
    read_context_md,
    write_boundaries,
    write_brief,
    write_context_md,
)

__all__ = [
    # models
    "BriefSection",
    "BriefRecord",
    "BasePackage",
    "PackageDecision",
    "BriefStatus",
    "BoundaryRule",
    "ProjectAnalysis",
    # checker
    "check_brief",
    "is_ready",
    # generator
    "BriefGenerator",
    "analyze_directory",
    # storage
    "read_brief",
    "write_brief",
    "read_context_md",
    "write_context_md",
    "collect_context_md_hierarchy",
    "generate_base_package",
    "read_boundaries",
    "write_boundaries",
    # injector
    "inject_brief_into_context",
    "format_brief_for_prompt",
    # boundaries
    "BoundaryEngine",
    "DEFAULT_RULES",
    # package_library
    "PackageLibrary",
    "DEFAULT_LIBRARY_PATH",
]
