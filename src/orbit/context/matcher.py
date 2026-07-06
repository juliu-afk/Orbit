"""上下文匹配引擎 (NL交互 PR #2).

从自然语言输入提取关键词 → 匹配已注册项目 → 返回排序候选。

匹配策略 (6级优先级):
  1. 会话历史 (最高) —— 当前未实现, 预留接口。
     WHY 未实现: 依赖 SessionStore 的项目操作历史追踪（PR #35），
     该模块完成后 match() 的 session_projects 参数可消费会话级项目上下文。
  2. 关键词精确匹配项目名
  3. 关键词匹配项目标签
  4. 关键词匹配项目描述
  5. 语义检索 —— 当前降级为 LIKE 搜索
  6. 默认回退 —— 返回最近活跃项目列表

用法:
    matcher = ContextMatcher(registry)
    result = matcher.match("支付超时了修一下")
    # → MatchResult(project="Keshen", confidence=0.8, ...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from orbit.projects.registry import ProjectRegistry

logger = structlog.get_logger("orbit.context")

# 常见中文停用词 + 通用词 (不参与匹配)
STOP_WORDS: set[str] = {
    "的",
    "了",
    "是",
    "在",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "他",
    "她",
    "它",
    "们",
    "那",
    "些",
    "个",
    "下",
    "修",
    "一下",
    "搞",
    "弄",
    "做",
    "帮",
    "请",
    "让",
    "把",
    "被",
    "给",
    "从",
    "对",
    "向",
    "跟",
    "与",
    "或",
    "且",
    "但",
    "而",
    "吗",
    "呢",
    "吧",
    "啊",
    "哦",
    "嗯",
    "哈",
    "呀",
}

# 技术关键词强化权重 (匹配到这些词时加分)
TECH_KEYWORDS: dict[str, float] = {
    "支付": 1.5,
    "超时": 1.2,
    "财务": 1.5,
    "凭证": 1.5,
    "报表": 1.3,
    "agent": 1.3,
    "调度": 1.2,
    "熔断": 1.2,
    "图谱": 1.2,
    "api": 1.1,
    "数据库": 1.2,
    "前端": 1.1,
    "后端": 1.1,
    "python": 1.0,
    "react": 1.0,
    "vue": 1.0,
    "sql": 1.0,
}


@dataclass
class MatchCandidate:
    """单个匹配候选。"""

    project_name: str
    score: float  # 0.0-1.0, 分数越高越匹配
    match_reason: str = ""  # "name_exact" | "tag_match" | "desc_match" | "fallback"
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    """上下文匹配结果。"""

    query: str  # 原始输入
    keywords: list[str]  # 提取的关键词
    candidates: list[MatchCandidate]  # 按 score 降序排列
    source: str = "keyword_match"  # session | keyword | fallback
    requires_confirmation: bool = True  # 是否需要用户确认

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "keywords": self.keywords,
            "candidates": [
                {
                    "project": c.project_name,
                    "score": round(c.score, 2),
                    "reason": c.match_reason,
                    "matched_keywords": c.matched_keywords,
                }
                for c in self.candidates[:5]  # 最多返回 5 个
            ],
            "source": self.source,
            "requires_confirmation": self.requires_confirmation,
        }


class ContextMatcher:
    """上下文匹配引擎。

    用法:
        matcher = ContextMatcher(registry)
        result = matcher.match("支付超时了修一下")
        if result.candidates:
            print(f"匹配到项目: {result.candidates[0].project_name}")
    """

    def __init__(self, registry: ProjectRegistry | None = None) -> None:
        self._registry = registry or ProjectRegistry()

    def match(self, query: str, session_projects: list[str] | None = None) -> MatchResult:
        """匹配自然语言输入到项目。

        session_projects: 当前会话/驾驶舱中最近操作的项目名列表 (预留, 会话历史优先)
        """
        # 1. 提取关键词
        keywords = self._extract_keywords(query)
        logger.info("context_match", query=query, keywords=keywords)

        # 2. 会话历史优先 (如果提供)
        if session_projects:
            for name in session_projects:
                p = self._registry.get(name)
                if p and p.is_active:
                    return MatchResult(
                        query=query,
                        keywords=keywords,
                        candidates=[
                            MatchCandidate(
                                project_name=name,
                                score=1.0,
                                match_reason="session_history",
                                matched_keywords=keywords,
                            )
                        ],
                        source="session",
                        requires_confirmation=False,
                    )

        # 3. 无关键词 → 回退列表
        if not keywords:
            recent = self._registry.list_all()[:5]
            return MatchResult(
                query=query,
                keywords=[],
                candidates=[
                    MatchCandidate(
                        project_name=p.name,
                        score=0.1,
                        match_reason="fallback",
                    )
                    for p in recent
                ],
                source="fallback",
                requires_confirmation=True,
            )

        # 4. 关键词匹配
        candidates = self._score_candidates(keywords)
        if candidates:
            # 如果第一名分数 >0.8 且第二名分数 <第一名×0.5, 无需确认
            top = candidates[0]
            needs_confirm = True
            if (len(candidates) == 1 and top.score > 0.8) or (
                len(candidates) >= 2 and top.score > 0.8 and top.score > candidates[1].score * 2
            ):
                needs_confirm = False
            return MatchResult(
                query=query,
                keywords=keywords,
                candidates=candidates,
                source="keyword_match",
                requires_confirmation=needs_confirm,
            )

        # 5. 无匹配 → 回退
        recent = self._registry.list_all()[:5]
        return MatchResult(
            query=query,
            keywords=keywords,
            candidates=[
                MatchCandidate(
                    project_name=p.name,
                    score=0.0,
                    match_reason="fallback",
                )
                for p in recent
            ],
            source="fallback",
            requires_confirmation=True,
        )

    # ── 内部 ─────────────────────────────────────────────

    def _extract_keywords(self, query: str) -> list[str]:
        """从中文/英文混合输入中提取关键词。

        英文按空格分词，中文按标点切分后做 bigram 滑动窗口
        (2-4字词组)，同时保留整体段落后备匹配。
        """
        # 先按标点/空格粗切
        segments = re.split(r"[,，。\.\s!！?？;；:：、]+", query.strip().lower())
        keywords: list[str] = []
        for seg in segments:
            if not seg or len(seg) < 2:
                continue
            # 判断是否为纯中文 (无ASCII字母)
            has_ascii = any(ord(c) < 128 for c in seg)
            if has_ascii:
                # 英文/混合: 直接作为关键词
                if seg not in STOP_WORDS:
                    keywords.append(seg)
            else:
                # 纯中文: 先过滤停用词碎片
                if seg in STOP_WORDS:
                    continue
                # 短中文 (2-4字): 直接作为关键词
                if len(seg) <= 4:
                    keywords.append(seg)
                else:
                    # 长中文: bigram 滑动窗口 (2字词组), 同时保留完整段落后备
                    keywords.append(seg)  # 完整段落
                    for i in range(len(seg) - 1):
                        bigram = seg[i : i + 2]
                        if bigram not in STOP_WORDS and len(bigram) >= 2:
                            keywords.append(bigram)
        # 去重, 保持顺序
        seen: set[str] = set()
        result: list[str] = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                result.append(k)
        return result

    def _score_candidates(self, keywords: list[str]) -> list[MatchCandidate]:
        """关键词评分——综合名称/标签/描述匹配度。"""
        projects = self._registry.list_all()
        if not projects:
            return []

        candidates: list[MatchCandidate] = []
        for p in projects:
            score = 0.0
            matched: list[str] = []
            reasons: list[str] = []

            for kw in keywords:
                # 名称精确匹配 (含子串)
                if kw in p.name.lower():
                    w = TECH_KEYWORDS.get(kw, 1.0)
                    score += 0.4 * w
                    matched.append(kw)
                    if "name_exact" not in reasons:
                        reasons.append("name_exact")

                # 标签匹配
                for tag in p.tags:
                    if kw in tag.lower():
                        w = TECH_KEYWORDS.get(kw, 1.0)
                        score += 0.25 * w
                        if kw not in matched:
                            matched.append(kw)
                        if "tag_match" not in reasons:
                            reasons.append("tag_match")
                        break

                # 描述匹配
                if kw in p.description.lower():
                    w = TECH_KEYWORDS.get(kw, 1.0)
                    score += 0.15 * w
                    if kw not in matched:
                        matched.append(kw)
                    if "desc_match" not in reasons:
                        reasons.append("desc_match")

            if score > 0:
                # 归一化: score / (关键词数 * 0.8), cap at 1.0
                normalized = min(score / (len(keywords) * 0.8), 1.0)
                candidates.append(
                    MatchCandidate(
                        project_name=p.name,
                        score=normalized,
                        match_reason="|".join(reasons),
                        matched_keywords=matched,
                    )
                )

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates
