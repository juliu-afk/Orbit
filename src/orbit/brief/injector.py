"""将项目说明书 + 基础代码包 + 边界规则注入 Agent prompt 的 context 层。

WHY 独立注入器: PromptBuilder 不应直接依赖 brief 模块——通过 injector
解耦，方便在不加载 brief 模块时（如测试环境）跳过注入。
"""

from __future__ import annotations

from typing import Any

from orbit.brief.checker import check_brief
from orbit.brief.models import BriefRecord, PackageDecision
from orbit.brief.storage import collect_context_md_hierarchy, read_boundaries, read_brief


def inject_brief_into_context(
    ctx: dict[str, Any],
    project_path: str = "",
    target_file: str = "",
    package_decision: PackageDecision | None = None,
) -> dict[str, Any]:
    """将项目说明书注入 PromptBuilder context dict。

    这是 PromptBuilder._build_context() 中 L2.5 层的实现。
    调用方只需传 ctx + project_path，返回增强后的 ctx。

    Args:
        ctx: PromptBuilder 当前构建的 context dict
        project_path: 项目根目录
        target_file: Agent 正在操作的目标文件（用于 CONTEXT.md 层级收集）
        package_decision: LLM 的基础代码包注入决策

    Returns:
        增强后的 context dict——新增 brief、boundaries、context_md 等字段
    """
    if not project_path:
        return ctx

    status = check_brief(project_path)
    result = dict(ctx)  # 浅拷贝——避免修改调用方原始 dict

    # 1. 注入项目说明书
    if status.has_brief:
        brief = read_brief(project_path)
        if brief:
            result["brief"] = brief.to_markdown()
            result["brief_sections"] = {s.title: s.content for s in brief.sections}

    # 2. 注入边界规则（文本形式——L2 Prompt 层）
    if status.has_boundaries:
        rules_text = read_boundaries(project_path)
        if rules_text:
            result["boundaries"] = rules_text

    # 3. 注入目录级 CONTEXT.md 层级
    if target_file and status.has_context_md:
        context_entries = collect_context_md_hierarchy(target_file, project_path)
        if context_entries:
            result["context_md"] = context_entries

    # 4. 注入基础代码包（按 LLM 决策）
    if package_decision and package_decision.decision != "skip":
        result["base_package"] = {
            "decision": package_decision.decision,
            "package_ids": package_decision.package_ids,
            "reason": package_decision.reason,
        }

    return result


def format_brief_for_prompt(brief: BriefRecord | None) -> str:
    """将 BriefRecord 格式化为可注入 prompt 的文本块。

    WHY 独立函数: inject_brief_into_context 存原始 markdown，
    但某些场景只需特定段落或需要裁剪 token。
    """
    if brief is None:
        return ""

    # 只取前 3 段（摘要+技术栈+命令）——最常被 Agent 需要的信息
    key_sections = ["摘要", "技术栈", "命令"]
    lines = ["## 项目说明书\n"]
    total_chars = 0
    max_chars = 2000  # WHY 硬上限: 说明书不应占据 context 层过多 token

    for section in brief.sections:
        if section.title in key_sections:
            block = f"### {section.title}\n{section.content}\n"
            if total_chars + len(block) > max_chars:
                lines.append(f"### {section.title}\n... (截断)\n")
                break
            lines.append(block)
            total_chars += len(block)

    return "\n".join(lines)
