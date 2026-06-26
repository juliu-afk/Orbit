"""失败升级与多方案对比合并 (Step 5.x 重试增强 + 用户反馈).

升级规则:
    Tier 1 (DS Flash) 失败 → 升级到 Tier 2 (DS V4 Pro)
    Tier 2 失败 → 升级到 Tier 3 (GLM-5.2)
    Tier 3 也失败 → 转人工

关键设计:
    - 每个 Tier 独立执行，不传上一 Tier 的失败输出（避免偏见）
    - Tier 3 完成后，三个方案一起对比，各取所长合并
    - 任何 Tier 成功则提前终止
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from orbit.router.agent import ModelTier

logger = structlog.get_logger("orbit.scheduler.escalation")

MAX_ESCALATION = 3  # 最多三级


@dataclass(frozen=True)
class TierAttempt:
    """单次 Tier 尝试的结果。"""

    tier: ModelTier
    model: str
    output: dict[str, Any] | None = None
    error: str | None = None
    success: bool = False
    duration_ms: float = 0.0

    @property
    def tier_label(self) -> str:
        return self.tier.value


@dataclass
class EscalationResult:
    """升级执行的最终结果。"""

    attempts: list[TierAttempt] = field(default_factory=list)
    merged_output: dict[str, Any] | None = None
    final_status: str = "unknown"  # "success" | "merged" | "failed" | "needs_human"
    merge_reason: str = ""


def build_merge_prompt(attempts: list[TierAttempt], task: str) -> str:
    """构建对比合并提示词——三个方案各取所长。

    不会把失败方案的错误传给下一个 Tier，只在最后合并时对比。
    """
    parts = [
        "你是方案合并 Agent。以下是同一任务由三个不同模型独立完成的方案。",
        "请对比分析，各取所长，输出一个合并后的最优方案。",
        "",
        f"## 任务\n{task}",
        "",
    ]

    tier_names = {
        ModelTier.TIER_1: "Tier1-DS Flash (轻量·快速)",
        ModelTier.TIER_2: "Tier2-DS V4 Pro (中档·标准)",
        ModelTier.TIER_3: "Tier3-GLM-5.2 (最强·深度)",
    }

    for a in attempts:
        label = tier_names.get(a.tier, a.tier.value)
        status = "✅ 通过" if a.success else f"❌ 失败: {a.error}"
        parts.append(f"## {label} ({status})")
        if a.output:
            # 截断每方案输出避免超 token
            output_str = str(a.output)
            if len(output_str) > 3000:
                output_str = output_str[:3000] + "...(截断)"
            parts.append(output_str)
        parts.append("")

    parts.append("## 合并要求")
    parts.append("1. 从三个方案中提取各自最好的部分")
    parts.append("2. 冲突时以 Tier3-GLM-5.2 为准")
    parts.append("3. 补充任一方案遗漏的关键点")
    parts.append(
        '4. 输出 JSON: {"merged": {...}, "taken_from": {"tier1": [...], "tier2": [...], "tier3": [...]}, "gaps_filled": [...]}'
    )
    parts.append("")
    parts.append("只输出 JSON，不要其他内容。")

    return "\n".join(parts)


async def merge_outputs(
    llm_client: Any,
    attempts: list[TierAttempt],
    task: str,
) -> dict[str, Any] | None:
    """由 GLM-5.2（Tier 3 裁判）对比三个方案，各取所长融合。

    裁判逻辑:
        - 同一模型既当选手(Tier 3)又当裁判——它是最强的，有能力判断优劣
        - 冲突时以 Tier 3 输出为准（最强模型），但吸收 Tier 1/2 的亮点
        - 输出包含 taken_from 字段，标注每部分来自哪个 Tier，可审计
    """
    if len(attempts) < 2:
        return attempts[0].output if attempts else None

    prompt = build_merge_prompt(attempts, task)

    try:
        from orbit.gateway.schemas import LLMRequest

        resp = await llm_client.generate(
            LLMRequest(prompt=prompt, system_prompt="你是方案合并 Agent。输出纯 JSON。"),
            task_id="merge",
        )
        import json as _json

        return _json.loads(resp.content)
    except Exception as e:
        logger.error("merge_failed", error=str(e))
        # 合并失败 → 降级返回 Tier 3 的输出（最强模型）
        for a in reversed(attempts):
            if a.success and a.output:
                logger.info("merge_fallback_to_tier", tier=a.tier.value)
                return a.output
        return None


def needs_escalation(output: dict[str, Any] | None, error: str | None) -> bool:
    """判断是否需要升级。"""
    if error:
        return True
    if output is None:
        return True
    # 输出中有明确失败标记
    status = output.get("status", "ok")
    return status in ("error", "failed", "invalid")


def next_tier(current: ModelTier) -> ModelTier | None:
    """返回下一级 Tier，已是最高返回 None。"""
    order = [ModelTier.TIER_0, ModelTier.TIER_1, ModelTier.TIER_2, ModelTier.TIER_3]
    try:
        idx = order.index(current)
        if idx < len(order) - 1:
            return order[idx + 1]
    except ValueError:
        pass
    return None
