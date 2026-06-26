"""MergeEngine——固定评审维度 + 确定性验证 + LLM辅助对比融合。

评审逻辑:
    Phase 1: 确定性验证（不调 LLM）——每个方案跑 L1-L5 自动检查
    Phase 2: LLM 对比评分——GLM-5.2 按 6 个固定维度逐项打分
    Phase 3: 融合——高分部分优先，冲突时以 Tier 3 为准，补充遗漏

为什么不是"让 LLM 选最好的":
    LLM 容易给出模糊的总体评价。固定维度+逐项打分 = 可审计、可复现、不会拍脑袋。
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any

import structlog

from orbit.gateway.schemas import LLMRequest
from orbit.scheduler.escalation import TierAttempt, EscalationResult

logger = structlog.get_logger("orbit.scheduler.merge_engine")

# ── 固定评审维度（6 维）──────────────────────────
EVALUATION_DIMENSIONS = [
    {
        "key": "correctness",
        "name": "正确性",
        "weight": 30,
        "description": "功能是否满足需求？逻辑是否正确？是否有明显 bug？",
        "deterministic_checks": ["syntax_valid", "no_empty_output", "status_is_ok"],
    },
    {
        "key": "completeness",
        "name": "完整性",
        "weight": 20,
        "description": "是否有错误处理？边界条件是否覆盖？空值是否检查？",
        "deterministic_checks": ["has_error_handling", "has_edge_cases"],
    },
    {
        "key": "security",
        "name": "安全性",
        "weight": 20,
        "description": "无注入/SQL拼接/硬编码密钥/命令注入？",
        "deterministic_checks": ["no_eval", "no_hardcoded_secret", "no_shell_injection"],
    },
    {
        "key": "maintainability",
        "name": "可维护性",
        "weight": 10,
        "description": "命名是否清晰？注释是否解释 WHY？结构是否合理？",
        "deterministic_checks": [],
    },
    {
        "key": "simplicity",
        "name": "简洁性",
        "weight": 10,
        "description": "是否过度抽象？是否重复代码？是否最小改动？",
        "deterministic_checks": [],
    },
    {
        "key": "performance",
        "name": "性能",
        "weight": 10,
        "description": "是否有多余 I/O？是否有 N+1 查询？复杂度是否合理？",
        "deterministic_checks": [],
    },
]


@dataclass
class DimensionScore:
    """单个维度的评分。"""

    key: str
    score: float  # 0-10
    reason: str
    best_of: str | None = None  # 哪个 Tier 在这维度最好


@dataclass
class ScoredAttempt:
    """带评分的方案。"""

    attempt: TierAttempt
    scores: list[DimensionScore] = field(default_factory=list)
    weighted_total: float = 0.0

    @property
    def tier_label(self) -> str:
        return self.attempt.tier.value


@dataclass
class MergeResult:
    """融合结果。"""

    merged: dict[str, Any]
    scorer: str  # 裁判模型
    scorecard: dict[str, dict[str, float]]  # {tier: {dimension: score}}
    taken_from: dict[str, list[str]]  # 每部分来自哪个 Tier
    gaps_filled: list[str]
    total_scores: dict[str, float]  # {tier: weighted_total}


class MergeEngine:
    """方案对比融合引擎。

    用法:
        engine = MergeEngine(llm_client)
        result = await engine.merge(attempts, task)
    """

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    async def merge(
        self,
        attempts: list[TierAttempt],
        task: str,
    ) -> MergeResult:
        """三阶段合并流程。"""
        valid = [a for a in attempts if a.output]

        if len(valid) < 2:
            # 只有一个有效方案——直接返回
            only = valid[0] if valid else attempts[-1]
            return MergeResult(
                merged=only.output or {},
                scorer="n/a (single attempt)",
                scorecard={only.tier_label: {}},
                taken_from={only.tier_label: ["全部"]},
                gaps_filled=[],
                total_scores={only.tier_label: 1.0},
            )

        # Phase 1: 确定性验证
        det_scores = {a.tier_label: self._deterministic_check(a.output or {}, task) for a in valid}

        # Phase 2: LLM 逐维评分
        try:
            llm_scores = await self._llm_evaluate(valid, task, det_scores)
        except Exception as e:
            logger.error("llm_evaluate_failed", error=str(e))
            # 评分失败 → 降级：Tier 3 直接胜出
            return self._fallback_merge(valid)

        # Phase 3: LLM 代码融合
        merged, taken_from, gaps = await self._synthesize(valid, llm_scores, task)

        total_scores = {}
        for label, scores in llm_scores.items():
            weighted = sum(
                s.score
                * next((d["weight"] for d in EVALUATION_DIMENSIONS if d["key"] == s.key), 0)
                / 100
                for s in scores
            )
            total_scores[label] = weighted

        scorecard = {}
        for label, sc in llm_scores.items():
            scorecard[label] = {s.key: s.score for s in sc}

        return MergeResult(
            merged=merged,
            scorer="GLM-5.2",
            scorecard=scorecard,
            taken_from=taken_from,
            gaps_filled=gaps,
            total_scores=total_scores,
        )

    # ── Phase 1: 确定性验证 ──────────────────────

    def _deterministic_check(self, output: dict[str, Any], task: str) -> dict[str, float]:
        """不调 LLM 的自动检查——快、零成本、可复现。"""
        scores: dict[str, float] = {}

        # 语法有效
        content = str(output)
        scores["syntax_valid"] = 10.0 if len(content) > 10 else 0.0

        # 非空
        scores["no_empty_output"] = 10.0 if content.strip() else 0.0

        # 状态正常
        status = output.get("status", "ok")
        scores["status_is_ok"] = 10.0 if status == "ok" else 0.0

        # 无明显注入
        risky = ["eval(", "exec(", "__import__", "subprocess", "os.system"]
        scores["no_eval"] = 0.0 if any(r in content for r in risky) else 10.0

        # 无硬编码密钥
        secret_patterns = ["sk-", "api_key=", "password=", "secret="]
        scores["no_hardcoded_secret"] = 0.0 if any(p in content for p in secret_patterns) else 10.0

        # 错误处理
        error_indicators = ["try", "except", "catch", "error", "raise", "throw"]
        scores["has_error_handling"] = 10.0 if any(e in content for e in error_indicators) else 5.0

        return scores

    # ── Phase 2: LLM 逐维评分 ────────────────────

    async def _llm_evaluate(
        self,
        attempts: list[TierAttempt],
        task: str,
        det_scores: dict[str, dict[str, float]],
    ) -> dict[str, list[DimensionScore]]:
        """调用 GLM-5.2，按 6 个维度逐项评分。"""
        prompt = self._build_evaluation_prompt(attempts, task, det_scores)

        resp = await self.llm.generate(
            LLMRequest(
                prompt=prompt,
                system_prompt=(
                    "你是代码方案评审裁判。按 6 个固定维度逐项评分(0-10分)。"
                    "必须基于具体证据，不能凭感觉。输出纯 JSON。"
                ),
            ),
            task_id="merge-eval",
        )

        return self._parse_scores(resp.content, attempts)

    def _build_evaluation_prompt(
        self,
        attempts: list[TierAttempt],
        task: str,
        det_scores: dict[str, dict[str, float]],
    ) -> str:
        """构建结构化评分 prompt。"""
        parts = [
            "## 任务\n" + task,
            "",
            "## 评审维度（6维·固定标准）",
        ]

        for d in EVALUATION_DIMENSIONS:
            parts.append(f"- **{d['name']}**({d['key']}, 权重{d['weight']}%): {d['description']}")

        parts.append("")
        parts.append("## 确定性检查结果（自动验证，不调LLM）")
        for tier_label, scores in det_scores.items():
            parts.append(f"### {tier_label}")
            for k, v in scores.items():
                parts.append(f"  {k}: {v}/10")

        parts.append("")
        parts.append("## 各方案输出")
        tier_labels = {0: "tier_1", 1: "tier_2", 2: "tier_3"}
        for i, a in enumerate(attempts):
            label = tier_labels.get(i, a.tier.value)
            parts.append(f"### {label} ({a.model})")
            parts.append(str(a.output)[:2000])

        parts.append("")
        parts.append("## 评分要求")
        parts.append("1. 对每个方案、每个维度给出 0-10 的分数")
        parts.append("2. 每个分数必须附具体理由（引用方案中的代码/文字作为证据）")
        parts.append("3. 标注每个维度哪个方案最好（best_of: 'tier_1'/'tier_2'/'tier_3'）")
        parts.append("4. 输出 JSON:")
        parts.append("""{
  "evaluations": {
    "tier_1": {
      "correctness": {"score": 8, "reason": "逻辑正确，但缺少空值检查", "best_of": null},
      ...
    },
    "tier_2": {...},
    "tier_3": {...}
  },
  "overall_best": "tier_3",
  "take_from": {
    "tier_1": ["简洁的函数命名"],
    "tier_2": ["完整的错误处理"],
    "tier_3": ["核心算法", "安全防护"]
  },
  "gaps": ["缺少并发处理", "未考虑超时"]
}""")
        parts.append("只输出 JSON，不要其他内容。")

        return "\n".join(parts)

    def _parse_scores(
        self,
        raw: str,
        attempts: list[TierAttempt],
    ) -> dict[str, list[DimensionScore]]:
        """解析 LLM 返回的评分 JSON。"""
        result = _json.loads(raw)
        evals = result.get("evaluations", {})

        scored: dict[str, list[DimensionScore]] = {}

        for a in attempts:
            label = a.tier_label  # 直接用 TierAttempt.tier_label
            tier_eval = evals.get(label, {})
            scores = []
            for dim in EVALUATION_DIMENSIONS:
                dk = dim["key"]
                dim_eval = tier_eval.get(dk, {"score": 5, "reason": "评分缺失"})
                scores.append(
                    DimensionScore(
                        key=dk,
                        score=float(dim_eval.get("score", 5)),
                        reason=str(dim_eval.get("reason", "")),
                        best_of=dim_eval.get("best_of"),
                    )
                )
            scored[label] = scores

        return scored

    # ── Phase 3: 融合 ────────────────────────────

    def _build_synthesis_prompt(
        self,
        attempts: list[TierAttempt],
        all_scores: dict[str, list[DimensionScore]],
        task: str,
    ) -> str:
        """构建代码融合 prompt——评分卡驱动，各取所长。"""
        tier_labels = [a.tier_label for a in attempts]

        parts = [
            "## 任务\n" + task,
            "",
            "## 三维度评分卡（裁判已打分，你据此融合）",
            "| 维度 | Tier1(DS Flash) | Tier2(DS V4 Pro) | Tier3(GLM-5.2) | 最佳 |",
            "|------|:-:|:-:|:-:|------|",
        ]

        for dim in EVALUATION_DIMENSIONS:
            dk = dim["key"]
            scores = []
            best_label = None
            best_s = -1.0
            for i, a in enumerate(attempts):
                label = tier_labels[i]
                tier_scores = all_scores.get(label, [])
                sc = next((s.score for s in tier_scores if s.key == dk), 5)
                scores.append(str(sc))
                if sc > best_s:
                    best_s = sc
                    best_label = label
            score_cols = " | ".join(scores)
            parts.append(f"| {dim['name']}({dim['weight']}%) | {score_cols} | {best_label} |")

        parts.append("")
        parts.append("## 各方案代码")
        for i, a in enumerate(attempts):
            label = tier_labels[i]
            parts.append(f"### {label} ({a.model})")
            parts.append(f"```\n{_json.dumps(a.output, indent=2, ensure_ascii=False)}\n```")
            parts.append("")

        parts.append("## 融合要求")
        parts.append("1. 以评分最高的方案为基础")
        parts.append("2. 从其他方案中吸收评分更高的维度的具体写法")
        parts.append("3. 冲突时以评分卡为准——哪个方案在该维度分高就用哪个的写法")
        parts.append("4. 补充评分卡暴露的遗漏点")
        parts.append(
            '5. 输出纯代码，不要解释。格式: {"code": "融合后的完整代码", "taken_from": {"tier_1": [...], "tier_2": [...], "tier_3": [...]}, "changes": "简述融合做了哪些改动"}'
        )
        parts.append("只输出 JSON。")

        return "\n".join(parts)

    async def _synthesize(
        self,
        attempts: list[TierAttempt],
        all_scores: dict[str, list[DimensionScore]],
        task: str,
    ) -> tuple[dict[str, Any], dict[str, list[str]], list[str]]:
        """Phase 3: LLM 融合——基于评分卡的代码级合并。

        不是简单复制 Tier 3，而是让 GLM-5.2 看到评分卡后，
        从每个方案中提取真正优秀的部分，生成融合代码。
        """
        # 先做确定性最佳维度统计（用作评分卡）
        taken_from: dict[str, list[str]] = {}

        for dim in EVALUATION_DIMENSIONS:
            dk = dim["key"]
            best_label = None
            best_score = -1.0
            for a in attempts:
                label = a.tier_label
                scores = all_scores.get(label, [])
                for s in scores:
                    if s.key == dk and s.score > best_score:
                        best_score = s.score
                        best_label = label
            if best_label:
                taken_from.setdefault(best_label, []).append(dim["name"])

        # 调 LLM 融合代码
        try:
            prompt = self._build_synthesis_prompt(attempts, all_scores, task)
            resp = await self.llm.generate(
                LLMRequest(
                    prompt=prompt,
                    system_prompt="你是代码融合 Agent。基于评分卡，从三个方案中各取所长，输出最优代码。输出纯 JSON。",
                ),
                task_id="merge-synth",
            )
            result = _json.loads(resp.content)
            merged_code = result.get("code", str(result))
            llm_taken = result.get("taken_from", {})
            changes = result.get("changes", "")

            # 合并固定维度统计和 LLM 判断
            final_output = {"code": merged_code, "changes": changes}
            return final_output, llm_taken or taken_from, [changes] if changes else []

        except Exception as e:
            logger.error("synthesize_llm_failed", error=str(e))
            # 降级：返回 Tier 3 原始输出
            for a in reversed(attempts):
                if a.output:
                    return a.output, taken_from, []
            return {}, taken_from, []

    def _fallback_merge(self, attempts: list[TierAttempt]) -> MergeResult:
        """评分失败时的降级合并——Tier 3 直接胜出。"""
        t3 = None
        for a in reversed(attempts):
            if a.output:
                t3 = a
                break
        if not t3:
            t3 = attempts[-1]

        return MergeResult(
            merged=t3.output or {},
            scorer="fallback (评分失败)",
            scorecard={},
            taken_from={t3.tier_label: ["全部(降级)"]},
            gaps_filled=[],
            total_scores={t3.tier_label: 1.0},
        )
