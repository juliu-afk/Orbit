"""BriefGenerator——使用 GLM-5.2 分析代码库并生成项目说明书。

WHY 始终用 GLM-5.2: 用户指定——说明书质量直接影响后续所有 Agent 的产出质量，
值得用最强模型一次性生成。

生成流程:
1. analyze_directory() → ProjectAnalysis（无 LLM，纯文件扫描）
2. 构建 prompt（分析结果 + 6 段式模板）
3. LLMClient.generate() → markdown 文本
4. BriefRecord.from_markdown() + 验证
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from orbit.brief.analyzer import analyze_directory, _extract_section
from orbit.brief.models import BriefRecord, BriefSection, ProjectAnalysis, REQUIRED_SECTIONS

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient

logger = structlog.get_logger("orbit.brief.generator")

# ── System Prompt 模板 ─────────────────────────────────────
# WHY 中文: 说明书面向会计/审计等非编程人员，中文注释是项目规范。

BRIEF_SYSTEM_PROMPT = """你是资深软件架构师，负责为新项目生成结构化的项目说明书。

说明书必须包含以下 6 个段落，用 Markdown 格式输出：

## 1. 摘要
3-5 句话：项目解决什么问题、目标用户是谁、成功的标准是什么。

## 2. 技术栈
列举语言、框架、版本号、关键依赖。已知的写确切版本，未知的标注"待确认"。

## 3. 命令
构建、测试、lint、启动开发环境——每条命令必须是可复制粘贴执行的精确 shell 命令。

## 4. 目录结构
描述每个目录的用途，一行说明。基于实际目录结构分析，不要编造不存在的目录。

## 5. 代码风格与模式
命名规范、格式化规则、项目中实际使用的代码模式。给出代码片段示例。

## 6. 边界
- 必须做：<强制遵守的规则>
- 需确认：<需要人类决策的事项>
- 禁止做：<绝对不能碰的红线>

输出规则：
- 直接输出 Markdown，不要输出 JSON、不要加解释前缀。
- 每个段落以 `## N. 标题` 开头。
- 只基于提供的代码库分析信息输出，不要编造。
- 如果某段落信息不足，写"信息不足，待人工补充"。
"""


class BriefGenerator:
    """项目说明书生成器——使用 GLM-5.2 分析代码库。

    Usage:
        gen = BriefGenerator(llm_client_pinned_to_glm5)
        brief = await gen.generate("D:/my-project")
        # brief 已写入 .orbit/brief.md
    """

    def __init__(self, llm: "LLMClient") -> None:
        """初始化生成器。

        Args:
            llm: 已 pin 到 GLM-5.2 的 LLMClient 实例。
                 BriefGenerator 不关心路由策略——调用方保证传 GLM-5.2。
        """
        self._llm = llm

    async def generate(
        self,
        project_path: str,
        analysis: ProjectAnalysis | None = None,
        existing_brief: BriefRecord | None = None,
    ) -> BriefRecord:
        """生成项目说明书。

        Args:
            project_path: 项目根目录绝对路径
            analysis: 预分析结果（可选——不传则自动运行 analyze_directory）
            existing_brief: 已有说明书（可选——用于增量更新）

        Returns:
            验证通过的 BriefRecord
        """
        # Step 1: 分析目录（如果未传入预分析结果）
        if analysis is None:
            analysis = analyze_directory(project_path)

        # Step 2: 构建 prompt
        project_name = os.path.basename(project_path.rstrip("/").rstrip("\\"))
        user_prompt = self._build_prompt(project_name, analysis, existing_brief)

        # Step 3: 调用 GLM-5.2
        from orbit.gateway.schemas import LLMRequest

        logger.info("brief_generation_start", project=project_name, language=analysis.language)

        response = await self._llm.generate(
            LLMRequest(
                prompt=user_prompt,
                system_prompt=BRIEF_SYSTEM_PROMPT,
                temperature=0.3,  # 低温度——说明书需要事实准确性而非创造性
                max_tokens=3072,  # 6 段说明书大约需要 1500-2500 tokens
            ),
            task_id=f"brief-gen-{project_name}",
            agent_name="brief_generator",
        )

        # Step 4: 解析 markdown
        brief = BriefRecord.from_markdown(response.content, project_name=project_name)
        brief.generated_at = time.time()
        brief.generated_by = response.model or "openai/glm-5.2"
        brief.project_language = analysis.language
        brief.project_framework = analysis.framework

        # Step 5: 验证必填段落
        if not brief.is_valid():
            logger.warning(
                "brief_missing_sections",
                project=project_name,
                sections=[s.title for s in brief.sections],
            )
            # 补全缺失的段落
            brief = self._fill_missing_sections(brief, analysis)

        logger.info(
            "brief_generated",
            project=project_name,
            sections=len(brief.sections),
            model=brief.generated_by,
        )
        return brief

    async def generate_context_md(
        self, directory: str, project_brief: BriefRecord
    ) -> str:
        """为单个目录生成 .orbit/context.md。

        Args:
            directory: 目标目录绝对路径
            project_brief: 项目级说明书（提供大背景）

        Returns:
            context.md 的 markdown 内容
        """
        dir_name = os.path.basename(directory.rstrip("/").rstrip("\\"))
        # 列出该目录下的文件
        try:
            entries = os.listdir(directory)
            files_in_dir = [e for e in entries if os.path.isfile(os.path.join(directory, e))]
            subdirs = [e for e in entries if os.path.isdir(os.path.join(directory, e))]
        except OSError:
            files_in_dir, subdirs = [], []

        prompt = f"""为以下目录生成 .orbit/context.md 文件。

项目背景: {project_brief.project_name}（{project_brief.project_language} {project_brief.project_framework}）

目录名: {dir_name}
包含文件: {', '.join(files_in_dir[:20]) if files_in_dir else '（空目录）'}
子目录: {', '.join(subdirs) if subdirs else '（无）'}

请生成一段 3-5 句的目录说明，描述：
1. 这个目录在项目中的角色
2. 里面的代码应该遵循什么模式
3. 有什么特别要注意的约束"""

        from orbit.gateway.schemas import LLMRequest

        response = await self._llm.generate(
            LLMRequest(
                prompt=prompt,
                system_prompt="你是资深软件架构师。为项目目录写简洁的上下文说明。只输出 Markdown 段落，不要标题。",
                temperature=0.3,
                max_tokens=500,
            ),
            task_id=f"context-md-{dir_name}",
            agent_name="brief_generator",
        )
        return response.content.strip()

    async def generate_all_context_md(
        self,
        project_path: str,
        brief: BriefRecord,
        min_subdirs: int = 3,
    ) -> list[str]:
        """为项目中所有关键目录生成 .orbit/context.md。

        WHY 批量生成: 项目注册时一次性创建，避免每次 Agent 调用时
        再逐个生成（耗时 + token 浪费）。

        策略: 仅对包含代码文件的二级目录生成（src/、tests/ 等）。
        跳过 __pycache__、.git、node_modules 等忽略目录。

        Args:
            project_path: 项目根目录
            brief: 已生成的项目说明书
            min_subdirs: 最少子目录数才触发（默认 3——小项目跳过）

        Returns:
            已写入的 context.md 文件路径列表
        """
        import os

        from orbit.brief.storage import write_context_md

        IGNORE = {"__pycache__", ".git", "node_modules", ".venv", "venv",
                   "build", "dist", ".orbit", "data", "Deliverables", "target",
                   ".next", ".turbo", ".pytest_cache", ".mypy_cache"}

        root = os.path.abspath(project_path)
        written: list[str] = []

        # 收集顶层目录
        try:
            top_dirs = [
                d for d in os.listdir(root)
                if os.path.isdir(os.path.join(root, d)) and d not in IGNORE and not d.startswith(".")
            ]
        except OSError:
            return written

        if len(top_dirs) < min_subdirs:
            return written  # 目录太少，不值得生成

        # 遍历二级目录（最多 5 个，避免 LLM 调用过多）
        count = 0
        for top_dir in top_dirs[:8]:  # 最多 8 个顶层目录
            dir_path = os.path.join(root, top_dir)
            # 检查是否包含代码文件
            try:
                has_code = any(
                    f.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"))
                    for f in os.listdir(dir_path)
                    if os.path.isfile(os.path.join(dir_path, f))
                )
            except OSError:
                continue

            if has_code and count < 5:
                try:
                    content = await self.generate_context_md(dir_path, brief)
                    path = write_context_md(dir_path, content)
                    written.append(path)
                    count += 1
                except Exception:
                    logger.warning("context_md_gen_failed", dir=dir_path)

        logger.info("context_md_batch_done", project=brief.project_name, count=len(written))
        return written

    def _build_prompt(
        self,
        project_name: str,
        analysis: ProjectAnalysis,
        existing: BriefRecord | None = None,
    ) -> str:
        """构建 LLM 生成 prompt。

        WHY 结构化 prompt: 让 LLM 看到精确的格式要求 + 已提取的事实数据，
        减少幻觉空间。
        """
        parts = [f"请为以下项目生成项目说明书（Markdown 格式，6 个段落）：\n"]
        parts.append(f"## 项目名\n{project_name}\n")

        parts.append(f"## 检测到的语言\n{analysis.language or '未知'}")
        parts.append(f"## 检测到的框架\n{analysis.framework or '未知'}\n")

        parts.append(f"## 文件统计\n"
                     f"- 总文件数: {analysis.file_count}\n"
                     f"- Python: {analysis.python_files}\n"
                     f"- TypeScript: {analysis.ts_files}\n"
                     f"- JavaScript: {analysis.js_files}\n"
                     f"- 其他: {analysis.other_files}\n")

        if analysis.key_files:
            parts.append(f"## 关键文件\n" + "\n".join(f"- {f}" for f in analysis.key_files[:15]) + "\n")

        if analysis.dependencies:
            parts.append(f"## 检测到的依赖\n" + ", ".join(analysis.dependencies[:20]) + "\n")

        parts.append(f"## 目录结构\n```\n{analysis.directory_tree}\n```\n")

        if existing:
            parts.append(f"## 已有说明书（请在此基础上增量更新）\n{existing.to_markdown()}\n")

        parts.append("请输出完整的项目说明书（6 个段落，Markdown 格式）：")
        return "\n".join(parts)

    @staticmethod
    def generate_strategy_md(project_root: str) -> Path | None:
        """从已有 brief.md 生成 STRATEGY.md——无需 LLM，纯文本提取。

        读取 .orbit/brief.md → 提取 5 段战略结构 → 写入 STRATEGY.md。
        Compound 对标: STRATEGY.md 是项目策略锚点，所有 Agent 自动对齐。

        Args:
            project_root: 项目根目录

        Returns:
            写入的 STRATEGY.md 路径，brief.md 不存在则返回 None
        """
        root = Path(project_root)
        brief_path = root / ".orbit" / "brief.md"
        if not brief_path.exists():
            return None

        try:
            brief_text = brief_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        # 从 brief 6 段中提取战略相关段落
        extract = _extract_section

        strategy_parts = [
            "## Target Problem",
            extract(brief_text, "1. 摘要") or "（待补充——从项目说明书自动生成）",
            "",
            "## Approach",
            extract(brief_text, "2. 技术栈") or "（待补充）",
            "",
            "## Persona",
            "（待补充——请在 STRATEGY.md 中描述目标用户）",
            "",
            "## Key Metrics",
            "（待补充——请定义成功衡量标准）",
            "",
            "## Tracks",
            "（待补充——请列出产品迭代路线优先级）",
        ]

        strategy_text = "\n".join(strategy_parts)
        strategy_path = root / "STRATEGY.md"
        strategy_path.write_text(strategy_text, encoding="utf-8")
        return strategy_path

    @staticmethod
    def _fill_missing_sections(brief: BriefRecord, analysis: ProjectAnalysis) -> BriefRecord:
        """补全缺失的段落——用占位文本。

        WHY 补全而非抛异常: 说明书缺失部分段落不应阻断整个流程，
        标记为"待人工补充"让后续 Agent 知道这里信息不全。
        """
        existing_titles = {s.title for s in brief.sections}
        for required in REQUIRED_SECTIONS:
            if required not in existing_titles:
                placeholder = (
                    f"信息不足，待人工补充。\n"
                    f"（检测到语言: {analysis.language or '未知'}，"
                    f"框架: {analysis.framework or '未知'}）"
                )
                brief.sections.append(BriefSection(title=required, content=placeholder))
                logger.info("brief_section_filled", section=required)
        return brief
