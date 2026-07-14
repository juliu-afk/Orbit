"""Agent 上下文统一工具——token 预算驱动的历史构建 + Grilling 协议。

从 chatter.py 提取，供所有 Agent 统一使用。

六条行业原则（Claude Code / Codex / OpenCode 共识）：
  1. 分层渐进——多水位线，不搞一刀切
  2. 成本严格递增——字符串截断 → placeholder → LLM 摘要
  3. 增量摘要 > 全量摘要——活摘要只合并新增
  4. 真实 token 计数——API totalTokens，tiktoken 仅规划估算
  5. 用户消息有特权——最近 N 轮 verbatim，不截断不摘要
  6. 单调边界——stub 单向不可逆，保护 prompt cache
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── 上下文参数 ──────────────────────────────────────────

_HISTORY_TOKEN_BUDGET = 16_000    # 对话历史 token 上限（动态 min(16K, 30%剩余窗口)）
_HISTORY_HARD_CAP = 200           # 安全网：极端情况下的兜底消息数上限
_HISTORY_MSG_TRUNC = 600          # 单条消息截断字符数
_USER_MSG_PROTECT_COUNT = 4       # 最近 N 条用户消息 verbatim 保护（原则 5）
_OMITTED_MSG = "（…更早的对话已省略…）"
_OVERHEAD_PER_MSG = 15            # "**角色:** " + 换行 的 token 开销


# ── GrillRequest 模型 ───────────────────────────────────


class GrillRequest(BaseModel):
    """跨 Agent Grilling 请求——上下文原则强制。

    裸问题（只有 question，background 为空）被拒绝。
    min_length=6 适应中文（"认证方案是什么？"仅 8 字但语义完整）。
    """

    question: str = Field(..., min_length=6, description="具体问题")
    background: str = Field(..., min_length=6, description="当前任务背景")
    location: str = Field(default="", description="涉及文件/函数/数据结构")
    root_cause: str = Field(default="", description="根因分析——架构性 vs 局部代码")
    impact: str = Field(default="", description="影响面/触发场景/严重程度")
    conflict_detection: str = Field(
        default="",
        description="冲突/模糊/冗余检测——与历史陈述、上游工件的矛盾，附引用来源",
    )
    candidates: list[str] = Field(default_factory=list, description="候选方案+利弊")
    constraints: list[str] = Field(default_factory=list, description="已知技术/业务约束")
    target_agent: str | None = Field(default=None, description="指定上游 Agent，None=自动路由")


# ── 对话历史构建 ────────────────────────────────────────


def _build_history_block(history: list[dict[str, str]]) -> str:
    """从对话历史构建注入 prompt 的文本块——token 预算驱动。

    策略：
    1. 用户最近 N 条消息 verbatim 保护（原则 5）
    2. 从最新→最旧累加 token，在预算内保留尽可能多的完整消息
    3. 超出预算的旧消息标记"已省略"（原则 6：单调边界）
    4. 单条超长消息截断但保留

    WHY: 不是拍脑袋的 10 条——是 token 预算驱动。
    """
    if not history:
        return ""

    from orbit.compression.token_counter import count_tokens

    kept: list[str] = []
    token_used = count_tokens(_OMITTED_MSG) + 20

    # 第一遍：标记用户消息（原则 5）
    user_indices: set[int] = set()
    user_count = 0
    actual_history = history[-_HISTORY_HARD_CAP:]
    for i in range(len(actual_history) - 1, -1, -1):
        if actual_history[i].get("role") == "user":
            user_indices.add(i)
            user_count += 1
            if user_count >= _USER_MSG_PROTECT_COUNT:
                break

    # 第二遍：从最新→最旧收集，token 预算驱动
    n_kept = 0
    for i in range(len(actual_history) - 1, -1, -1):
        h = actual_history[i]
        role_label = "用户" if h.get("role") == "user" else "Orbit"
        content = str(h.get("content", ""))

        # 用户受保护消息不截断；其他消息按 MSG_TRUNC 截断
        if i not in user_indices and len(content) > _HISTORY_MSG_TRUNC:
            content = content[:_HISTORY_MSG_TRUNC] + "…（已截断）"

        line = f"**{role_label}:** {content}"
        line_tokens = count_tokens(line) + _OVERHEAD_PER_MSG

        if token_used + line_tokens > _HISTORY_TOKEN_BUDGET:
            if n_kept == 0:
                kept.append(line)
            break

        kept.append(line)
        token_used += line_tokens
        n_kept += 1

    # 反转回时间序
    kept.reverse()

    # 如有省略，开头标记
    n_total = min(len(history), _HISTORY_HARD_CAP)
    if len(kept) < n_total:
        kept.insert(0, _OMITTED_MSG)

    return "## 对话历史\n\n" + "\n".join(kept) + "\n\n---\n\n"


def _build_history_block_with_relevance(
    history: list[dict[str, str]],
    current_query: str,
) -> str:
    """token 预算 + BGE 相关性混合策略（US5）。

    保留：
    - 最近 N 条消息（时间序）
    - 高相关性历史消息（BGE embedding 语义检索 Top-K）

    当 history ≤ 30 条时回退纯时间序。
    """
    if len(history) <= 30:
        return _build_history_block(history)

    from orbit.compression.token_counter import count_tokens

    # 最近 N 条保留（时间序）
    recent = history[-20:]
    older = history[:-20]

    # BGE 相关性检索
    relevant: list[dict[str, str]] = []
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        query_emb = model.encode(current_query, normalize_embeddings=True)

        scored = []
        for h in older:
            content = str(h.get("content", ""))
            if len(content) < 10:
                continue
            emb = model.encode(content, normalize_embeddings=True)
            score = float(np.dot(query_emb, emb))
            if score > 0.5:  # 相关性阈值
                scored.append((score, h))
        scored.sort(key=lambda x: x[0], reverse=True)
        relevant = [h for _, h in scored[:5]]  # Top-5
    except Exception:
        # fail-open: BGE 不可用 → 回退纯时间序
        return _build_history_block(history)

    # 合并：省略标记 + 高相关性历史 + 最近消息
    kept: list[str] = [_OMITTED_MSG]
    if relevant:
        kept.append("## 相关历史（语义检索）")
        for h in relevant:
            role_label = "用户" if h.get("role") == "user" else "Orbit"
            content = str(h.get("content", ""))
            if len(content) > _HISTORY_MSG_TRUNC:
                content = content[:_HISTORY_MSG_TRUNC] + "…"
            kept.append(f"**{role_label}:** {content}")
        kept.append("")

    kept.append("## 最近对话")
    for h in recent:
        role_label = "用户" if h.get("role") == "user" else "Orbit"
        content = str(h.get("content", ""))
        if len(content) > _HISTORY_MSG_TRUNC:
            content = content[:_HISTORY_MSG_TRUNC] + "…"
        kept.append(f"**{role_label}:** {content}")

    # Token 预算最终检查
    block = "\n".join(kept)
    block_tokens = count_tokens(block)
    if block_tokens > _HISTORY_TOKEN_BUDGET * 2:
        # 相关性模式超预算 → 回退标准模式
        return _build_history_block(history)

    return "## 对话历史\n\n" + block + "\n\n---\n\n"
