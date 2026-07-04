"""ArtifactTierManager——图谱查询结果三级分级（Inkeep 借鉴 #2）。

WHY: Inkeep 的 Artifact 三级存储（preview/full/oversized）防止上下文溢出。
Orbit 六图谱查询结果全量进上下文，大结果集会挤爆 context window。
本模块与 L3 熵监控（hallucination/l3_entropy.py）互补——
L3 管"超了没"（token 计数+熔断），tier 管"怎么裁"（信息密度侧）。

三级定义：
- PREVIEW (≤2KB): 摘要自动进 Agent 上下文
- FULL (≤64KB): 完整结果，Agent 通过 tool 按需查询
- OVERSIZED (>64KB): 拒绝加载，返回细化查询建议

阈值初始值可配置，运行时动态调整（每 100 次查询评估一次）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ArtifactTier(StrEnum):
    """三级分级枚举。"""

    PREVIEW = "preview"       # ≤2KB 摘要，自动进上下文
    FULL = "full"             # 完整结果，按需 tool 查询
    OVERSIZED = "oversized"   # 拒绝加载，返回细化建议


@dataclass
class TieredResult:
    """分级后的查询结果。"""

    tier: ArtifactTier
    preview: str              # 摘要（所有 tier 都有，preview 级 = 完整内容截断）
    full_content: str | None  # 仅 FULL tier 非空
    size_bytes: int
    hint: str = ""            # oversized 时的细化建议
    query_params: dict | None = None  # 原始查询参数（供 full 查询 tool 使用）

    def to_dict(self) -> dict:
        result = {
            "tier": self.tier.value,
            "preview": self.preview,
            "size_bytes": self.size_bytes,
            "hint": self.hint,
        }
        if self.full_content is not None:
            result["full_content"] = self.full_content
        if self.query_params:
            result["query_params"] = self.query_params
        return result


# 默认阈值（可通过 US-5 配置面板调整）
DEFAULT_PREVIEW_THRESHOLD = 2048     # 2KB
DEFAULT_FULL_THRESHOLD = 65536       # 64KB
# 动态调整上限
MAX_PREVIEW_THRESHOLD = 8192         # 8KB
MAX_FULL_THRESHOLD = 262144          # 256KB
# 动态调整评估间隔
ADJUSTMENT_INTERVAL = 100


class ArtifactTierManager:
    """图谱查询结果分级管理器。

    用法:
        mgr = ArtifactTierManager()
        result = mgr.classify(query_output, query_params={"domain": "code", "symbol": "main"})
        if result.tier == ArtifactTier.PREVIEW:
            context += result.preview       # 自动注入
        elif result.tier == ArtifactTier.FULL:
            context += result.preview       # 摘要进上下文
            # Agent 需要详情时调用 load_artifact tool → 返回 result.full_content
        else:
            # OVERSIZED——提示 Agent 细化查询
            context += f"查询结果过大（{result.size_bytes} 字节）。{result.hint}"
    """

    def __init__(
        self,
        preview_threshold: int = DEFAULT_PREVIEW_THRESHOLD,
        full_threshold: int = DEFAULT_FULL_THRESHOLD,
    ) -> None:
        self.preview_threshold = preview_threshold
        self.full_threshold = full_threshold
        # 动态调整统计计数器
        self._preview_hits: int = 0       # preview 查询且 Agent 未请求 full（命中）
        self._preview_total: int = 0      # preview 查询总数
        self._oversized_count: int = 0
        self._total_queries: int = 0

    def classify(self, content: str, query_params: dict | None = None) -> TieredResult:
        """对查询结果分级。

        Args:
            content: 图谱查询返回的原始文本内容
            query_params: 原始查询参数（供 full 查询 tool 重建查询）

        Returns:
            TieredResult——分级后的结果。
        """
        size = len(content.encode("utf-8"))
        self._total_queries += 1

        if size < self.preview_threshold:
            # PREVIEW: 内容 < 阈值（严格小于，不含等于——等于进 FULL）
            self._preview_total += 1
            # 默认认为 preview 已足够（命中），除非 Agent 后续请求 full
            self._preview_hits += 1
            return TieredResult(
                tier=ArtifactTier.PREVIEW,
                preview=content,
                full_content=content,  # 小内容 full=preview，避免额外查询
                size_bytes=size,
                query_params=query_params,
            )

        if size <= self.full_threshold:
            self._preview_total += 1
            # preview 不命中——内容超 preview 阈值，Agent 可能需要 full
            return TieredResult(
                tier=ArtifactTier.FULL,
                preview=_truncate_utf8_safe(content, self.preview_threshold),
                full_content=content,
                size_bytes=size,
                query_params=query_params,
            )

        # OVERSIZED
        self._oversized_count += 1
        return TieredResult(
            tier=ArtifactTier.OVERSIZED,
            preview=_truncate_utf8_safe(content, self.preview_threshold),
            full_content=None,
            size_bytes=size,
            hint=f"查询结果 {size} 字节，超过上限 {self.full_threshold} 字节。"
                 f"请细化查询条件（如添加 domain/symbol 过滤、限制返回数量）。",
            query_params=query_params,
        )

    def record_full_request(self) -> None:
        """Agent 请求了 full 内容——说明 preview 不够，降低命中计数。"""
        if self._preview_hits > 0:
            self._preview_hits -= 1

    def maybe_adjust(self) -> bool:
        """每 ADJUSTMENT_INTERVAL 次查询评估一次，必要时动态调整阈值。

        Returns:
            True 如果阈值被调整，False 否则。
        """
        if self._total_queries < ADJUSTMENT_INTERVAL:
            return False

        adjusted = False

        # preview 命中率 < 80% → 升 preview 阈值（翻倍，有上限）
        if self._preview_total > 0:
            hit_rate = self._preview_hits / self._preview_total
            if hit_rate < 0.8 and self.preview_threshold < MAX_PREVIEW_THRESHOLD:
                self.preview_threshold = min(
                    self.preview_threshold * 2, MAX_PREVIEW_THRESHOLD
                )
                adjusted = True

        # oversized 触发率 > 10% → 升 full 阈值（翻倍，有上限）
        oversized_rate = self._oversized_count / self._total_queries
        if oversized_rate > 0.1 and self.full_threshold < MAX_FULL_THRESHOLD:
            self.full_threshold = min(
                self.full_threshold * 2, MAX_FULL_THRESHOLD
            )
            adjusted = True

        # 重置计数器
        self._preview_hits = 0
        self._preview_total = 0
        self._oversized_count = 0
        self._total_queries = 0

        return adjusted

    def get_stats(self) -> dict:
        """返回当前统计信息（供 US-5 配置面板展示）。"""
        return {
            "preview_threshold": self.preview_threshold,
            "full_threshold": self.full_threshold,
            "preview_hits": self._preview_hits,
            "preview_total": self._preview_total,
            "oversized_count": self._oversized_count,
            "total_queries": self._total_queries,
        }


def _truncate_utf8_safe(text: str, max_bytes: int) -> str:
    """UTF-8 安全截断——不会在多字节字符中间切断。

    WHY: Python str[:n] 按字符截断，但字节长度可能超限。
    encode[:max_bytes] 可能切断多字节字符中间 → decode 报错。
    用 errors='ignore' 丢弃不完整尾字节。
    预留 "…" (3 bytes) 空间，避免截断后加省略号超出上限。
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    ellipsis_bytes = len("…".encode("utf-8"))
    truncated = encoded[: max_bytes - ellipsis_bytes]
    return truncated.decode("utf-8", errors="ignore") + "…"
