"""检查点边界算法 (Phase 2 AC11b).

TAIL 10K-20K tokens + 5 条文本保护 + 可压缩工具结果擦除。
对标 MiMo Code checkpoint.ts ~500 行。

WHY TAIL 而非 HEAD: 最近的上下文对 LLM 最重要（locality of reference）。
"""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger("orbit.checkpoint.boundary")

# 5 条文本保护——匹配这些模式的内容永不被压缩
TEXT_PROTECTIONS: list[re.Pattern] = [
    re.compile(r"(?:Error|Exception|Traceback|raise)\b", re.IGNORECASE),
    re.compile(r"[\w./\\]+\.\w{2,4}"),  # 文件路径
    re.compile(r"line \d+"),  # 行号
    re.compile(r"(?i)(?:key|secret|token|password|api_key)\s*[:=]\s*\S+"),
    re.compile(r'"(?:[^"\\]|\\.)*"'),  # 引用字符串
]

# 可压缩内容模式
COMPRESSIBLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"```[\s\S]{400,}```"),  # 大代码块 (>400 chars)
    re.compile(r"─{10,}"),  # 分隔线
    re.compile(r"\n{4,}"),  # 过多空行
]


def should_protect(text: str) -> bool:
    """检查文本是否匹配保护模式."""
    return any(p.search(text) for p in TEXT_PROTECTIONS)


def erase_compressible(text: str) -> tuple[str, int]:
    """擦除可压缩内容，返回 (清理后文本, 移除字节数)."""
    original_len = len(text)
    for pattern in COMPRESSIBLE_PATTERNS:
        text = pattern.sub(
            lambda m: f"\n[可压缩内容已移除: {len(m.group())} 字节]\n",
            text,
        )
    return text, original_len - len(text)


def compute_checkpoint_boundary(
    messages: list[dict[str, Any]],
    tail_token_target: int = 15_000,
    min_tail_tokens: int = 10_000,
    max_tail_tokens: int = 20_000,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """计算检查点边界——保留 TAIL 部分的消息.

    Args:
        messages: 完整消息历史
        tail_token_target: 目标 token 数（默认 15K）
        min_tail_tokens: 最小保留 token
        max_tail_tokens: 最大保留 token

    Returns:
        (tail_messages, metadata)
    """
    total_tokens = 0
    kept: list[dict[str, Any]] = []
    protections_hit: set[str] = set()
    total_erased = 0

    # 从尾部向前遍历
    for msg in reversed(messages):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        msg_tokens = len(content) // 4

        # 检查文本保护
        if should_protect(content):
            protections_hit.add(role)

        # 擦除可压缩工具结果（不保护的工具消息）
        msg_copy = dict(msg)
        if role == "tool" and not should_protect(content):
            cleaned, erased = erase_compressible(content)
            msg_copy["content"] = cleaned
            total_erased += erased
            msg_tokens = len(cleaned) // 4

        kept.insert(0, msg_copy)
        total_tokens += msg_tokens

        if total_tokens >= max_tail_tokens:
            break

    metadata = {
        "start_idx": len(messages) - len(kept),
        "kept_messages": len(kept),
        "kept_tokens": total_tokens,
        "total_messages": len(messages),
        "protections_applied": sorted(protections_hit),
        "erased_bytes": total_erased,
        "tail_token_target": tail_token_target,
    }

    logger.info(
        "checkpoint_boundary_computed",
        kept=len(kept),
        tokens=total_tokens,
        erased=total_erased,
    )
    return kept, metadata
