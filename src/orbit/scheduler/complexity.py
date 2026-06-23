"""任务复杂度评分器 (Step O1 系统优化).

在 PARSING 阶段评估任务复杂度，决定走快车道还是完整流水线。
评分维度: 涉及文件数/修改范围/风险等级/是否核心逻辑。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComplexityResult:
    """复杂度评分结果。"""

    score: int  # 0-100
    file_count: int  # 估计涉及文件数
    scope: str  # single_line | single_file | multi_file | multi_module
    risk: str  # low | medium | high
    is_core: bool  # 是否涉及核心模块
    recommended_mode: str  # fast | full
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "file_count": self.file_count,
            "scope": self.scope,
            "risk": self.risk,
            "is_core": self.is_core,
            "recommended_mode": self.recommended_mode,
            "reasons": self.reasons,
        }


class ComplexityScorer:
    """任务复杂度检测——启发式规则 + 关键词权重。

    用法:
        scorer = ComplexityScorer()
        result = scorer.evaluate("把日志级别改成debug")
        if result.recommended_mode == "fast":
            ...  # 走快车道
    """

    FAST_LANE_THRESHOLD = 30  # 低于此分数走快车道

    # 简单任务关键词 → 拉低分数
    SIMPLE_KEYWORDS: list[tuple[str, int]] = [
        (r"(修改|改成|改.*日志|日志.*改)", -20), (r"改一行", -25),
        (r"加个.*日志", -20), (r"调整.*配置", -15),
        (r"换个.*名字", -20), (r"注释", -15),
        (r"改个.*文案", -20), (r"格式化", -20), (r"修.*拼写", -25),
        (r"bump.*version", -20), (r"update.*README", -20),
    ]

    # 复杂任务关键词 → 推高分数
    COMPLEX_KEYWORDS: list[tuple[str, int]] = [
        (r"实现", 25), (r"重构", 30), (r"架构", 30),
        (r"新增.*功能", 20), (r"设计", 25), (r"支付", 20),
        (r"数据库.*迁移", 30), (r"API.*breaking", 35),
        (r"实时", 15), (r"并发", 20), (r"分布式", 25),
        (r"安全", 15), (r"加密", 15), (r"认证", 20),
    ]

    # 核心模块关键词
    CORE_MODULES: list[str] = [
        "double_entry", "voucher", "posting", "ledger",
        "trial_balance", "statement", "closing",
        "scheduler", "orchestrator", "checkpoint",
    ]

    def evaluate(self, prd_text: str) -> ComplexityResult:
        """评估任务复杂度。"""
        reasons: list[str] = []
        score = 50  # 基准分 50

        # 1. 关键词打分
        for pattern, weight in self.SIMPLE_KEYWORDS:
            if re.search(pattern, prd_text, re.IGNORECASE):
                score += weight
                reasons.append(f"简单模式匹配:{pattern} ({weight:+d})")
                break  # 只匹配第一个

        for pattern, weight in self.COMPLEX_KEYWORDS:
            if re.search(pattern, prd_text, re.IGNORECASE):
                score += weight
                reasons.append(f"复杂模式匹配:{pattern} ({weight:+d})")

        # 2. 涉及文件数推断
        file_count = self._estimate_files(prd_text)
        if file_count == 1:
            score -= 10
            reasons.append("单文件修改 (-10)")
        elif file_count >= 5:
            score += 15
            reasons.append(f"多文件修改 ~{file_count} (+15)")

        # 3. 范围判断
        scope = self._determine_scope(prd_text, file_count)
        if scope == "single_line":
            score -= 10
        elif scope in ("multi_file", "multi_module"):
            score += 10

        # 4. 核心模块检测
        is_core = any(mod in prd_text.lower() for mod in self.CORE_MODULES)
        if is_core:
            score += 20
            reasons.append("涉及核心模块 (+20)")

        # 5. 风险判定
        risk = self._assess_risk(prd_text, is_core, file_count)

        # 钳制 0-100
        score = max(0, min(100, score))
        mode = "fast" if score < self.FAST_LANE_THRESHOLD else "full"

        return ComplexityResult(
            score=score,
            file_count=file_count,
            scope=scope,
            risk=risk,
            is_core=is_core,
            recommended_mode=mode,
            reasons=reasons,
        )

    def _estimate_files(self, prd_text: str) -> int:
        """估计涉及文件数——基于关键词启发式。"""
        multi_indicators = ["多个", "所有", "批量", "每个", "各个", "几个", "一些"]
        if any(w in prd_text for w in multi_indicators):
            return 5
        single_indicators = ["一个", "某个", "这个", "那个", "一行", "单个"]
        if any(w in prd_text for w in single_indicators):
            return 1
        return 2  # 默认 2 个文件

    def _determine_scope(self, prd_text: str, file_count: int) -> str:
        if any(w in prd_text for w in ["一行", "这个变量", "这个函数"]):
            return "single_line"
        if file_count >= 5:
            return "multi_module"
        if file_count >= 3:
            return "multi_file"
        return "single_file"

    def _assess_risk(self, prd_text: str, is_core: bool, file_count: int) -> str:
        if is_core and file_count >= 3:
            return "high"
        if is_core or file_count >= 5:
            return "medium"
        return "low"


def find_similar_task(prd_text: str, history: list[str], threshold: float = 0.7) -> str | None:
    """查找历史相似任务——简单 Jaccard 相似度 (2-gram)。

    threshold: 相似度阈值（默认 0.9），超过则返回匹配的历史任务文本。
    返回 None 表示无匹配。
    """
    if not history:
        return None

    def _bigrams(text: str) -> set[str]:
        """2-gram 集合——简单有效的中英混合相似度。"""
        chars = text.lower().replace(" ", "")
        return {chars[i:i + 2] for i in range(len(chars) - 1)}

    prd_grams = _bigrams(prd_text)
    if not prd_grams:
        return None

    best_match: str | None = None
    best_score = 0.0

    for h in history:
        h_grams = _bigrams(h)
        if not h_grams:
            continue
        # Jaccard 相似度: |A ∩ B| / |A ∪ B|
        intersection = len(prd_grams & h_grams)
        union = len(prd_grams | h_grams)
        score = intersection / union if union > 0 else 0.0
        if score > best_score:
            best_score = score
            best_match = h

    return best_match if best_score >= threshold else None
