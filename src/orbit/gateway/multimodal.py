"""V15.1 多模态 P0：三梯度路由 + 模型配置。

WHY 三梯度：免费模型覆盖 80% 场景（T1/T2），付费模型覆盖重型场景（T3）。
Agent 不感知模型细节——只传 content + 可选 tier，路由层自动决策。

降级策略：T3 失败 → T2（保留视觉信息）→ 失败则抛异常（不静默降级到纯文本）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# ── 梯度定义 ──


class Tier(IntEnum):
    """三梯度——从轻到重。"""
    LIGHT = 1       # 免费，单图/短视频
    STANDARD = 2    # 免费+thinking，多图/中等视频/Bug诊断
    HEAVY = 3       # 付费，长视频/设计稿→代码/批量文档


# ── 梯度配置 ──


@dataclass
class TierConfig:
    """单个梯度的模型配置。

    WHY dataclass 而非 Pydantic：不需要校验——配置是常量，编译期保证正确。
    """
    model: str              # API model name
    endpoint: str           # API base URL
    max_tokens: int         # 默认 max_tokens
    thinking: bool | None   # None=使用模型默认, True=强制开启, False=关闭
    cost_per_million: float # 元/百万 tokens，0=免费
    context_window: int     # 上下文窗口（用于自动梯度判定）
    description: str        # 人类可读描述


# ── 三梯度配置表 ──
# WHY 硬编码：当前只有 2 个模型 × 3 个梯度，不需要外部配置文件。
# P1 多 provider 时迁移到 YAML/JSON 配置。

TIERS: dict[Tier, TierConfig] = {
    Tier.LIGHT: TierConfig(
        model="glm-4.1v-thinking-flash",
        endpoint="https://open.bigmodel.cn/api/paas/v4",
        max_tokens=4096,
        thinking=None,           # auto——信任模型判断
        cost_per_million=0.0,    # 永久免费
        context_window=64_000,
        description="T1 轻量：单截图、短视频(<10min)、UI 定位",
    ),
    Tier.STANDARD: TierConfig(
        model="glm-4.1v-thinking-flash",
        endpoint="https://open.bigmodel.cn/api/paas/v4",
        max_tokens=8192,
        thinking=True,           # 强制开启——深度推理
        cost_per_million=0.0,    # 永久免费
        context_window=64_000,
        description="T2 标准：多图对比、Bug 诊断、视频分析",
    ),
    Tier.HEAVY: TierConfig(
        model="glm-4.6v",
        endpoint="https://open.bigmodel.cn/api/paas/v4",
        max_tokens=8192,
        thinking=None,           # GLM-4.6V 无 thinking 参数
        cost_per_million=4.0,    # ¥1 入 + ¥3 出 ≈ ¥4/M (sum)
        context_window=128_000,
        description="T3 重量：长视频(>10min)、设计稿→代码、批量文档",
    ),
}

# ── 梯度降级链 ──
# T3 失败时降级到的目标梯度（None=不降级，直接抛异常）
DOWNGRADE_CHAIN: dict[Tier, Tier | None] = {
    Tier.HEAVY: Tier.STANDARD,   # T3 失败 → T2（保留视觉，免费兜底）
    Tier.STANDARD: None,          # T2 失败 → 抛异常（不降级到纯文本）
    Tier.LIGHT: None,             # T1 失败 → 抛异常
}

# ── 梯度自动判定 ──

# 触发 T2 的关键词——出现即需要深度推理
THINKING_KEYWORDS = ["分析", "诊断", "定位", "找问题", "bug", "根因", "为什么"]

# 触发 T3 的视频时长阈值（秒）
HEAVY_VIDEO_THRESHOLD_SEC = 600  # 10 分钟

# 触发 T3 的图片数量阈值
HEAVY_IMAGE_COUNT = 4


class TierRouter:
    """按 content 类型 + 可选手动 tier → 自动选择梯度。

    WHY 独立类：纯函数逻辑，方便单元测试（不依赖网络/API）。
    P1 多 provider 时扩展媒体类型检测逻辑。
    """

    @staticmethod
    def classify(content: str | list[dict] | None, tier: int | None = None) -> Tier:
        """根据 content 自动判定梯度。

        Args:
            content: LLMRequest.content 字段
            tier: 手动指定的梯度（1-3），None=自动

        Returns:
            Tier 枚举值

        Raises:
            ValueError: tier 不在 1-3 范围内
        """
        # 手动指定优先
        if tier is not None:
            if tier not in (1, 2, 3):
                raise ValueError(f"tier 必须在 1-3 范围内，当前值: {tier}")
            return Tier(tier)

        # content 为 None 或纯文本 → 不应走多模态路径（调用方应走纯文本）
        if content is None:
            return Tier.LIGHT  # 安全兜底

        content_list: list[dict] = []
        if isinstance(content, str):
            # str content → 视为纯文本 prompt，走 T1
            return Tier.LIGHT

        content_list = content  # list[dict]

        # 分析 content 构成
        image_count = 0
        video_count = 0
        has_long_video = False
        has_thinking_keyword = False

        # 收集所有文本用于关键词检测
        all_text = ""

        for item in content_list:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "image_url":
                    image_count += 1
                elif item_type == "video_url":
                    video_count += 1
                    # 检查视频时长元数据（如有）
                    video_data = item.get("video_url", {})
                    if isinstance(video_data, dict):
                        duration = video_data.get("duration", 0)
                        if duration > HEAVY_VIDEO_THRESHOLD_SEC:
                            has_long_video = True
                elif item_type == "text":
                    all_text += " " + item.get("text", "")

        # 关键词检测
        for kw in THINKING_KEYWORDS:
            if kw in all_text.lower():
                has_thinking_keyword = True
                break

        # 判定逻辑（顺序敏感——先检查 T3，再 T2，最后 T1）
        if has_long_video or image_count >= HEAVY_IMAGE_COUNT:
            return Tier.HEAVY

        if video_count > 0 or image_count >= 2 or has_thinking_keyword:
            return Tier.STANDARD

        return Tier.LIGHT

    @staticmethod
    def get_config(tier: Tier) -> TierConfig:
        """获取梯度配置。"""
        return TIERS[tier]

    @staticmethod
    def get_downgrade(tier: Tier) -> Tier | None:
        """获取降级目标梯度。返回 None 表示不降级。"""
        return DOWNGRADE_CHAIN.get(tier)
