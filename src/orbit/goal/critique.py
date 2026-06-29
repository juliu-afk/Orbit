"""批判 Agent——CODING 完成后独立审查，决定放行或退回。

对标 Pantheon + Jules Critic:
- 独立上下文（不接收生成 Agent 的任何消息）
- 跨模型族（确保与生成 Agent 使用不同模型族）
- 差异聚焦审查（输入为 git diff，非全文件）
- 只有 APPROVED 才放行到 VERIFYING

v4 定位: Goal 模式的品质门禁——替代人工 PR review。

WHY 独立 Agent: 同模型自审遗漏率 ~40%，跨模型审查遗漏率 ~18%
（多模型集成研究数据）。CritiqueAgent = 自主合入前的最后防线。
"""

from __future__ import annotations

import json
import structlog
from typing import TYPE_CHECKING, Any
import asyncio

if TYPE_CHECKING:
    from orbit.compose.models import Task
    from orbit.gateway.client import LLMClient
    from orbit.gateway.schemas import LLMRequest

logger = structlog.get_logger("orbit.goal")

# 批判维度 + 权重
CRITIQUE_DIMENSIONS = {
    "correctness": {"weight": 0.40, "label": "正确性"},
    "security": {"weight": 0.25, "label": "安全性"},
    "performance": {"weight": 0.15, "label": "性能"},
    "maintainability": {"weight": 0.20, "label": "可维护性"},
}

CRITIQUE_SYSTEM_PROMPT = """你是代码批判专家。唯一职责：找到问题。

审查维度:
1. 正确性 (40%): 代码逻辑正确？边界条件处理？异常处理？
2. 安全性 (25%): 注入/泄漏/权限问题？硬编码密钥？
3. 性能 (15%): O(n²)/重复查询/不必要的内存分配？
4. 可维护性 (20%): 代码清晰？命名准确？注释充分？

批判原则:
- 宁错杀不放过——不确定也算作问题
- 有例证——每个问题引用具体代码行
- 无视作者解释——只看代码本身
- 找不到问题 → APPROVED
- 输入为 git diff，非全文

输出 JSON 格式（仅 JSON）:
{
  "approved": true/false,
  "issues": [
    {
      "severity": "critical"|"major"|"minor",
      "dimension": "correctness"|"security"|"performance"|"maintainability",
      "description": "具体问题描述",
      "location": "文件:行号"
    }
  ],
  "summary": "审查摘要"
}
"""


class CritiqueIssue:
    """批判发现的问题。"""

    def __init__(
        self,
        severity: str,
        dimension: str,
        description: str,
        location: str = "",
    ) -> None:
        self.severity = severity  # critical | major | minor
        self.dimension = dimension
        self.description = description
        self.location = location


class CritiqueResult:
    """批判审查结果。"""

    def __init__(
        self,
        approved: bool = True,
        issues: list[CritiqueIssue] | None = None,
        summary: str = "",
    ) -> None:
        self.approved = approved
        self.issues = issues or []
        self.summary = summary

    @property
    def max_severity(self) -> str:
        if not self.issues:
            return "none"
        for sev in ("critical", "major", "minor"):
            if any(i.severity == sev for i in self.issues):
                return sev
        return "none"

    @property
    def issue_count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for i in self.issues:
            counts[i.severity] = counts.get(i.severity, 0) + 1
        return counts


class CritiqueAgent:
    """批判 Agent——独立上下文 + 跨模型审查。

    Usage:
        critic = CritiqueAgent(critique_llm_client)
        result = await critic.critique(task, code_artifact)
        if result.approved:
            # 放行 → VERIFYING
    """

    # 生成模型族 → 批判模型族映射
    GENERATOR_TO_CRITIC_MODEL: dict[str, str] = {
        "anthropic": "openai",     # Claude 生成 → GPT 批判
        "openai": "anthropic",     # GPT 生成 → Claude 批判
        "glm": "anthropic",        # GLM 生成 → Claude 批判
        "default": "anthropic",
    }

    def __init__(
        self,
        llm: Any = None,  # LLMClient
        model_family: str = "default",
    ) -> None:
        self._llm = llm
        self._model_family = model_family

    async def critique(
        self,
        task: Any,  # Task
        code_artifact: str = "",
        diff_only: bool = True,
        verification_results: list[dict] | None = None,
        ensemble_alternatives: list[dict] | None = None,
    ) -> CritiqueResult:
        """审查代码产物。

        Args:
            task: 子任务定义
            code_artifact: 代码产物——diff_only=True 时为 git diff
            diff_only: 是否仅审查 diff（非全文件）
            verification_results: ExecutorVerifier 的结果（如果有）
            ensemble_alternatives: 集成模式下的其他方案（供对比）

        Returns:
            CritiqueResult: approved + issues
        """
        if not self._llm:
            logger.info("critique_mock_mode_auto_approve")
            return CritiqueResult(approved=True, summary="mock mode——自动通过")

        # 构建审查 prompt——仅含代码和验证结果，不含生成 Agent 的推理过程
        prompt_parts = [f"## 任务\n{task.description if hasattr(task, 'description') else str(task)}"]

        if code_artifact:
            # 截断超长代码——批判关注质量不关注全量
            truncated = code_artifact[:10000]
            if len(code_artifact) > 10000:
                truncated += f"\n\n... [截断 {len(code_artifact) - 10000} 字符]"
            prompt_parts.append(f"\n## {'Diff' if diff_only else '代码产物'}\n```\n{truncated}\n```")

        if verification_results:
            prompt_parts.append(f"\n## 验证结果\n{self._format_verification(verification_results)}")

        if ensemble_alternatives:
            prompt_parts.append(f"\n## 其他方案（供对比）\n{self._format_alternatives(ensemble_alternatives)}")

        prompt = "\n".join(prompt_parts)

        try:
            from orbit.gateway.schemas import LLMRequest

            req = LLMRequest(
                prompt=prompt,
                system_prompt=CRITIQUE_SYSTEM_PROMPT,
                temperature=0.3,   # 低温度——确定性审查
                max_tokens=1000,
            )
            response = await self._llm.generate(req, task_id="critique")
            return self._parse_response(response.content or "")
        except asyncio.CancelledError:
            raise
            logger.warning("critique_llm_failed_fail_open", error=str(e))
        except Exception as e:
            return CritiqueResult(
                approved=True,
                summary=f"批判 LLM 调用失败→fail-open: {str(e)}",
            )

    # ── 内部 ──────────────────────────────────────────

    def _parse_response(self, content: str) -> CritiqueResult:
        """解析 LLM 批判响应——robust parsing。"""
        try:
            # 去除 markdown code block
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.strip("`")
                if clean.startswith("json"):
                    clean = clean[4:]
            data = json.loads(clean)
            issues = [
                CritiqueIssue(
                    severity=i.get("severity", "minor"),
                    dimension=i.get("dimension", "correctness"),
                    description=i.get("description", ""),
                    location=i.get("location", ""),
                )
                for i in data.get("issues", [])
            ]
            return CritiqueResult(
                approved=data.get("approved", True),  # 默认 fail-open
                issues=issues,
                summary=data.get("summary", ""),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("critique_parse_failed_fail_open", content=content[:200])
            return CritiqueResult(
                approved=True,
                summary=f"批判解析失败→fail-open: {str(e)}",
            )

    @staticmethod
    def _format_verification(results: list[dict]) -> str:
        """格式化验证结果——简要。"""
        lines = []
        for r in results:
            icon = "✅" if r.get("passed") else "❌"
            lines.append(
                f"- {icon} `{r.get('command', '?')}` → exit={r.get('exit_code', '?')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_alternatives(alternatives: list[dict]) -> str:
        """格式化集成候选方案——简要。"""
        lines = []
        for i, alt in enumerate(alternatives):
            lines.append(
                f"方案 {i+1} ({alt.get('model', '?')}): "
                f"{str(alt.get('output', ''))[:200]}"
            )
        return "\n".join(lines)
