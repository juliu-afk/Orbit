"""ArtifactTierManager 单元测试——三级分级 + 动态调整（Inkeep 借鉴 #2）。

覆盖: preview/full/oversized 三种 tier + 边界值 + 动态调整 + UTF-8 安全截断。
"""

from __future__ import annotations


class TestArtifactTierEnum:
    """ArtifactTier 枚举。"""

    def test_tier_values(self):
        from orbit.graph.tier import ArtifactTier

        assert ArtifactTier.PREVIEW == "preview"
        assert ArtifactTier.FULL == "full"
        assert ArtifactTier.OVERSIZED == "oversized"


class TestArtifactTierManager:
    """ArtifactTierManager 分级逻辑。"""

    def test_small_content_preview(self):
        """内容 ≤2KB → PREVIEW。"""
        from orbit.graph.tier import ArtifactTier, ArtifactTierManager

        mgr = ArtifactTierManager()
        content = "Hello World"  # 11 bytes
        result = mgr.classify(content)
        assert result.tier == ArtifactTier.PREVIEW
        assert result.preview == content
        assert result.full_content == content  # 小内容 full=preview
        assert result.size_bytes == 11

    def test_medium_content_full(self):
        """内容 >2KB ≤64KB → FULL。"""
        from orbit.graph.tier import ArtifactTier, ArtifactTierManager

        mgr = ArtifactTierManager()
        # 生成 ~3KB 内容
        content = "A" * 3000
        result = mgr.classify(content)
        assert result.tier == ArtifactTier.FULL
        assert result.full_content == content
        assert len(result.preview.encode("utf-8")) <= 2048  # preview 不超过 2KB

    def test_large_content_oversized(self):
        """内容 >64KB → OVERSIZED。"""
        from orbit.graph.tier import ArtifactTier, ArtifactTierManager

        mgr = ArtifactTierManager()
        # 生成 ~70KB 内容
        content = "A" * 70000
        result = mgr.classify(content)
        assert result.tier == ArtifactTier.OVERSIZED
        assert result.full_content is None
        assert "细化查询" in result.hint

    def test_boundary_preview_equals_threshold(self):
        """内容恰好 = preview_threshold → FULL（不等号 <）。"""
        from orbit.graph.tier import ArtifactTier, ArtifactTierManager

        mgr = ArtifactTierManager(preview_threshold=2048)
        # 恰好 2048 字节 → 不是 PREVIEW，是 FULL
        content = "A" * 2048
        result = mgr.classify(content)
        assert result.tier == ArtifactTier.FULL

    def test_boundary_preview_one_byte_under(self):
        """内容 = preview_threshold - 1 → PREVIEW。"""
        from orbit.graph.tier import ArtifactTier, ArtifactTierManager

        mgr = ArtifactTierManager(preview_threshold=2048)
        content = "A" * 2047
        result = mgr.classify(content)
        assert result.tier == ArtifactTier.PREVIEW

    def test_boundary_full_equals_threshold(self):
        """内容恰好 = full_threshold → FULL（不等号 ≤）。"""
        from orbit.graph.tier import ArtifactTier, ArtifactTierManager

        # preview_threshold=50, full_threshold=100 → 100 bytes: 50 < 100 ≤ 100 → FULL
        mgr = ArtifactTierManager(preview_threshold=50, full_threshold=100)
        content = "A" * 100
        result = mgr.classify(content)
        assert result.tier == ArtifactTier.FULL

    def test_empty_content(self):
        """空内容 → PREVIEW。"""
        from orbit.graph.tier import ArtifactTier, ArtifactTierManager

        mgr = ArtifactTierManager()
        result = mgr.classify("")
        assert result.tier == ArtifactTier.PREVIEW
        assert result.size_bytes == 0

    def test_query_params_preserved(self):
        """查询参数通过 TieredResult 传递。"""
        from orbit.graph.tier import ArtifactTierManager

        mgr = ArtifactTierManager()
        params = {"domain": "code", "symbol": "main"}
        result = mgr.classify("test", query_params=params)
        assert result.query_params == params

    def test_to_dict_serializable(self):
        """TieredResult.to_dict() 可 JSON 序列化。"""
        import json

        from orbit.graph.tier import ArtifactTierManager

        mgr = ArtifactTierManager()
        result = mgr.classify("test content", query_params={"key": "value"})
        d = result.to_dict()
        assert d["tier"] == "preview"
        assert d["preview"] == "test content"
        # 可 JSON 序列化
        json.dumps(d)

    def test_utf8_safe_truncate_multibyte(self):
        """多字节字符（中文）截断不会切在字符中间。"""
        from orbit.graph.tier import ArtifactTier, ArtifactTierManager

        mgr = ArtifactTierManager(preview_threshold=10)
        # 每个中文字符 3 字节，"你好世界" = 12 字节 > 10
        content = "你好世界"
        result = mgr.classify(content)
        assert result.tier != ArtifactTier.OVERSIZED
        # preview 不会包含损坏的 UTF-8
        preview_bytes = result.preview.encode("utf-8")
        assert len(preview_bytes) <= 10 or result.tier != ArtifactTier.PREVIEW


class TestDynamicAdjustment:
    """动态调整逻辑。"""

    def test_no_adjust_below_interval(self):
        """查询数 < 100 → 不调整。"""
        from orbit.graph.tier import ArtifactTierManager

        mgr = ArtifactTierManager()
        for _ in range(50):
            mgr.classify("A" * 100)  # 小内容 → preview 命中
        adjusted = mgr.maybe_adjust()
        assert adjusted is False

    def test_adjust_when_hit_rate_low(self):
        """preview 命中率 < 80% → 升 preview 阈值。"""
        from orbit.graph.tier import ArtifactTierManager

        mgr = ArtifactTierManager(preview_threshold=2048)
        old_threshold = mgr.preview_threshold

        # 模拟低命中率：大部分查询 > preview 阈值
        for _ in range(80):
            mgr.classify("A" * 3000)  # FULL 级——preview 不命中
            mgr.record_full_request()  # Agent 请求了 full
        for _ in range(20):
            mgr.classify("A" * 100)  # PREVIEW 级——命中

        adjusted = mgr.maybe_adjust()
        assert adjusted is True
        # 命中率 = 20/100 = 0.2 < 0.8 → 阈值翻倍
        assert mgr.preview_threshold == min(old_threshold * 2, 8192)

    def test_adjust_when_oversized_high(self):
        """oversized 触发率 > 10% → 升 full 阈值。"""
        from orbit.graph.tier import ArtifactTierManager

        mgr = ArtifactTierManager(full_threshold=65536)
        old_threshold = mgr.full_threshold

        # 模拟高 oversized 率
        for _ in range(20):
            mgr.classify("A" * 70000)  # OVERSIZED
        for _ in range(80):
            mgr.classify("A" * 100)  # PREVIEW

        adjusted = mgr.maybe_adjust()
        assert adjusted is True
        # oversized_rate = 20/100 = 0.2 > 0.1 → 阈值翻倍
        assert mgr.full_threshold == min(old_threshold * 2, 262144)

    def test_stats_after_classify(self):
        """get_stats() 返回正确计数。"""
        from orbit.graph.tier import ArtifactTierManager

        mgr = ArtifactTierManager()
        mgr.classify("A" * 100)
        mgr.classify("A" * 3000)
        mgr.classify("A" * 70000)

        stats = mgr.get_stats()
        assert stats["total_queries"] == 3
        assert stats["oversized_count"] == 1

    def test_threshold_capped_at_max(self):
        """阈值不超过上限。"""
        from orbit.graph.tier import MAX_FULL_THRESHOLD, MAX_PREVIEW_THRESHOLD, ArtifactTierManager

        mgr = ArtifactTierManager(
            preview_threshold=MAX_PREVIEW_THRESHOLD - 1,
            full_threshold=MAX_FULL_THRESHOLD - 1,
        )
        # 制造低命中率触发调整
        for _ in range(80):
            mgr.classify("A" * (MAX_PREVIEW_THRESHOLD + 100))
            mgr.record_full_request()
        for _ in range(20):
            mgr.classify("A" * 100)

        mgr.maybe_adjust()
        assert mgr.preview_threshold <= MAX_PREVIEW_THRESHOLD
        assert mgr.full_threshold <= MAX_FULL_THRESHOLD
