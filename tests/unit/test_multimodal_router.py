"""V15.1 多模态 P0：TierRouter + TierConfig 单元测试。

测试梯度判定逻辑——纯函数，不依赖网络/API。
"""

import pytest
from orbit.gateway.multimodal import Tier, TierRouter, TierConfig, TIERS, DOWNGRADE_CHAIN


class TestTierRouter:
    """TierRouter.classify() 自动梯度判定。"""

    # ── T1：轻量 ──

    def test_single_image_t1(self):
        """单图 → T1"""
        assert TierRouter.classify([
            {"type": "image_url", "image_url": {"url": "https://x.com/a.jpg"}}
        ]) == Tier.LIGHT

    def test_short_text_t1(self):
        """纯文本 content → T1"""
        assert TierRouter.classify([
            {"type": "text", "text": "hello"}
        ]) == Tier.LIGHT

    def test_str_content_t1(self):
        """str content → T1"""
        assert TierRouter.classify("hello world") == Tier.LIGHT

    def test_none_content_t1(self):
        """None content → T1（安全兜底）"""
        assert TierRouter.classify(None) == Tier.LIGHT

    # ── T2：标准 ──

    def test_two_images_t2(self):
        """2 张图片 → T2"""
        assert TierRouter.classify([
            {"type": "image_url", "image_url": {"url": "a.jpg"}},
            {"type": "image_url", "image_url": {"url": "b.jpg"}},
        ]) == Tier.STANDARD

    def test_video_triggers_t2(self):
        """视频 → T2（含分析推理需求）"""
        assert TierRouter.classify([
            {"type": "video_url", "video_url": {"url": "v.mp4"}}
        ]) == Tier.STANDARD

    def test_keyword_analysis_t2(self):
        """含"分析"关键词 → T2"""
        assert TierRouter.classify([
            {"type": "text", "text": "请分析这个bug的原因"}
        ]) == Tier.STANDARD

    def test_keyword_diagnose_t2(self):
        """含"诊断"关键词 → T2"""
        assert TierRouter.classify([
            {"type": "text", "text": "诊断这个UI问题"}
        ]) == Tier.STANDARD

    def test_keyword_locate_t2(self):
        """含"定位"关键词 → T2"""
        assert TierRouter.classify([
            {"type": "text", "text": "定位到这个错误的根因"}
        ]) == Tier.STANDARD

    def test_keyword_bug_t2(self):
        """含"bug"关键词（英文）→ T2"""
        assert TierRouter.classify([
            {"type": "text", "text": "find the bug"}
        ]) == Tier.STANDARD

    def test_three_images_t2(self):
        """3 张图片 → T2（未到 T3 阈值）"""
        assert TierRouter.classify([
            {"type": "image_url", "image_url": {"url": f"{i}.jpg"}}
            for i in range(3)
        ]) == Tier.STANDARD

    # ── T3：重量 ──

    def test_four_images_t3(self):
        """4 张图片 → T3"""
        assert TierRouter.classify([
            {"type": "image_url", "image_url": {"url": f"{i}.jpg"}}
            for i in range(4)
        ]) == Tier.HEAVY

    def test_long_video_t3(self):
        """长视频（900s > 600s 阈值）→ T3"""
        assert TierRouter.classify([
            {"type": "video_url", "video_url": {"url": "v.mp4", "duration": 900}}
        ]) == Tier.HEAVY

    def test_video_exceeds_threshold_t3(self):
        """视频 601s（>600s 阈值）→ T3"""
        assert TierRouter.classify([
            {"type": "video_url", "video_url": {"url": "v.mp4", "duration": 601}}
        ]) == Tier.HEAVY

    def test_short_video_not_t3(self):
        """短视频（120s < 600s）→ T2（非 T3）"""
        assert TierRouter.classify([
            {"type": "video_url", "video_url": {"url": "v.mp4", "duration": 120}}
        ]) == Tier.STANDARD

    # ── 手动 tier ──

    def test_manual_tier_override(self):
        """手动 tier=3 覆盖自动判定"""
        assert TierRouter.classify(
            [{"type": "image_url", "image_url": {"url": "a.jpg"}}],
            tier=3
        ) == Tier.HEAVY

    def test_manual_tier_1(self):
        """手动 tier=1"""
        assert TierRouter.classify(
            [{"type": "image_url", "image_url": {"url": "a.jpg"}},
             {"type": "image_url", "image_url": {"url": "b.jpg"}}],
            tier=1
        ) == Tier.LIGHT

    def test_manual_tier_invalid_raises(self):
        """手动 tier=0（非法）→ ValueError"""
        with pytest.raises(ValueError, match="1-3"):
            TierRouter.classify([], tier=0)

    def test_manual_tier_out_of_range_raises(self):
        """手动 tier=5（非法）→ ValueError"""
        with pytest.raises(ValueError, match="1-3"):
            TierRouter.classify([], tier=5)

    # ── 综合 ──

    def test_mixed_content_image_priority(self):
        """混合 content：图片数优先于关键词"""
        # 4 图 → T3，即使有"分析"关键词
        content = [{"type": "image_url", "image_url": {"url": f"{i}.jpg"}} for i in range(4)]
        content.append({"type": "text", "text": "分析这些截图"})
        assert TierRouter.classify(content) == Tier.HEAVY

    def test_empty_list_t1(self):
        """空 content list → T1"""
        assert TierRouter.classify([]) == Tier.LIGHT


class TestTierConfig:
    """梯度配置完整性。"""

    def test_all_tiers_have_config(self):
        """三个梯度都有配置"""
        for tier in (Tier.LIGHT, Tier.STANDARD, Tier.HEAVY):
            cfg = TierRouter.get_config(tier)
            assert cfg.model, f"Tier {tier} missing model"
            assert cfg.endpoint.startswith("https://"), f"Tier {tier} bad endpoint"
            assert cfg.max_tokens > 0, f"Tier {tier} bad max_tokens"

    def test_t1_t2_free(self):
        """T1/T2 免费"""
        assert TIERS[Tier.LIGHT].cost_per_million == 0
        assert TIERS[Tier.STANDARD].cost_per_million == 0

    def test_t3_paid(self):
        """T3 付费"""
        assert TIERS[Tier.HEAVY].cost_per_million > 0

    def test_t1_t2_same_model(self):
        """T1/T2 用同一模型（GLM-4.1V）"""
        assert TIERS[Tier.LIGHT].model == TIERS[Tier.STANDARD].model

    def test_t1_t2_thinking_differs(self):
        """T1 thinking=None, T2 thinking=True"""
        assert TIERS[Tier.LIGHT].thinking is None
        assert TIERS[Tier.STANDARD].thinking is True

    def test_t3_different_model(self):
        """T3 用不同模型（GLM-4.6V）"""
        assert TIERS[Tier.HEAVY].model != TIERS[Tier.LIGHT].model

    def test_t3_larger_context(self):
        """T3 上下文 > T1/T2"""
        assert TIERS[Tier.HEAVY].context_window > TIERS[Tier.LIGHT].context_window


class TestDowngradeChain:
    """降级链完整性。"""

    def test_t3_downgrades_to_t2(self):
        """T3 → T2"""
        assert TierRouter.get_downgrade(Tier.HEAVY) == Tier.STANDARD

    def test_t2_no_downgrade(self):
        """T2 无降级（不降级到纯文本）"""
        assert TierRouter.get_downgrade(Tier.STANDARD) is None

    def test_t1_no_downgrade(self):
        """T1 无降级"""
        assert TierRouter.get_downgrade(Tier.LIGHT) is None


class TestLLMRequestMultimodal:
    """LLMRequest 多模态字段。"""

    def test_content_field_accepts_list(self):
        """content 接受 list[dict]"""
        from orbit.gateway.schemas import LLMRequest
        req = LLMRequest(
            prompt="describe",
            content=[{"type": "image_url", "image_url": {"url": "https://x.com/img.jpg"}}]
        )
        assert req.content is not None
        assert len(req.content) == 1

    def test_content_field_accepts_str(self):
        """content 接受 str（向后兼容）"""
        from orbit.gateway.schemas import LLMRequest
        req = LLMRequest(prompt="", content="plain text content")
        assert req.content == "plain text content"

    def test_content_default_none(self):
        """content 默认 None"""
        from orbit.gateway.schemas import LLMRequest
        req = LLMRequest(prompt="hello")
        assert req.content is None

    def test_tier_field_default_none(self):
        """tier 默认 None"""
        from orbit.gateway.schemas import LLMRequest
        req = LLMRequest(prompt="hello")
        assert req.tier is None

    def test_tier_field_accepts_1_3(self):
        """tier 接受 1/2/3"""
        from orbit.gateway.schemas import LLMRequest
        for t in (1, 2, 3):
            req = LLMRequest(prompt="hello", tier=t)
            assert req.tier == t

    def test_reject_oversized_data_uri(self):
        """拒绝超大 base64 图片"""
        from orbit.gateway.schemas import LLMRequest
        import pytest as pt
        # 构造一个 20MB 的假 data URI
        huge = "data:image/png;base64," + "A" * (20 * 1024 * 1024)
        with pt.raises(Exception):  # Pydantic ValidationError or ValueError
            LLMRequest(
                prompt="test",
                content=[{"type": "image_url", "image_url": {"url": huge}}]
            )

    def test_empty_prompt_with_content_ok(self):
        """content 存在时 prompt 可为空"""
        from orbit.gateway.schemas import LLMRequest
        req = LLMRequest(
            prompt="",
            content=[{"type": "text", "text": "describe this"}]
        )
        assert req.prompt == ""
        assert req.content is not None
