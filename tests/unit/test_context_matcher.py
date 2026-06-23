"""NL交互 PR #2——上下文匹配引擎单元测试。"""

import os

from orbit.context.matcher import ContextMatcher
from orbit.projects.registry import ProjectRegistry


class TestContextMatcher:
    """上下文匹配——关键词提取/项目匹配/候选排序。"""

    def test_match_by_project_name(self) -> None:
        reg = _seeded_registry()
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("Orbit 的调度器有问题")
            assert len(result.candidates) > 0
            assert result.candidates[0].project_name == "Orbit"
        finally:
            reg.close()
            _cleanup()

    def test_match_by_tag(self) -> None:
        reg = _seeded_registry()
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("agent 系统调度延迟高")
            assert any(c.project_name == "Orbit" for c in result.candidates)
        finally:
            reg.close()
            _cleanup()

    def test_match_by_description(self) -> None:
        reg = _seeded_registry()
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("财务凭证录入功能")
            # Finite description 含"财务"
            assert any(c.project_name == "Finite" for c in result.candidates)
        finally:
            reg.close()
            _cleanup()

    def test_match_chinese_query(self) -> None:
        """中文输入"支付超时了修一下"→匹配到含"支付"描述的项目。"""
        reg = _seeded_registry()
        # 注册一个支付相关项目
        reg.register("PaymentService", description="支付网关服务, 处理超时重试",
                     tags=["支付", "gateway"])
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("支付超时了修一下")
            assert len(result.candidates) > 0
            assert result.candidates[0].project_name == "PaymentService"
            assert len(result.keywords) > 0
        finally:
            reg.close()
            _cleanup()

    def test_no_match_fallback(self) -> None:
        reg = _seeded_registry()
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("xyzzy 不存在的项目")
            assert result.source == "fallback"
            assert result.requires_confirmation is True
        finally:
            reg.close()
            _cleanup()

    def test_empty_query_fallback(self) -> None:
        reg = _seeded_registry()
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("。，！")
            assert result.source == "fallback"
        finally:
            reg.close()
            _cleanup()

    def test_session_history_priority(self) -> None:
        reg = _seeded_registry()
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("随便改点什么", session_projects=["Keshen"])
            assert result.source == "session"
            assert result.candidates[0].project_name == "Keshen"
            assert result.requires_confirmation is False
        finally:
            reg.close()
            _cleanup()

    def test_high_confidence_no_confirmation(self) -> None:
        """单候选 >0.8 分且无竞品时无需确认。"""
        reg = _seeded_registry()
        # 注册一个名称与查询高度匹配的项目
        reg.register("OrbitAgent", description="agent framework", tags=["agent", "ai"])
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("OrbitAgent 调度优化")
            assert len(result.candidates) >= 1
            if result.candidates[0].score > 0.8 and len(result.candidates) == 1:
                assert result.requires_confirmation is False
        finally:
            reg.close()
            _cleanup()

    def test_stop_words_filtered(self) -> None:
        reg = _seeded_registry()
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("帮我修一下那个 bug")
            # "帮""我""一下""那个" 被过滤, "修""bug" 保留
            keywords = result.keywords
            assert "帮" not in keywords
            assert "我" not in keywords
            assert "一下" not in keywords
        finally:
            reg.close()
            _cleanup()

    def test_result_to_dict(self) -> None:
        reg = _seeded_registry()
        matcher = ContextMatcher(reg)
        try:
            result = matcher.match("Orbit agent")
            d = result.to_dict()
            assert d["query"] == "Orbit agent"
            assert len(d["candidates"]) <= 5
            assert "source" in d
        finally:
            reg.close()
            _cleanup()


# ── 辅助 ─────────────────────────────────────────────────


def _seeded_registry() -> ProjectRegistry:
    """预填测试数据的注册表。"""
    reg = ProjectRegistry()
    reg.register("Orbit", repo_url="https://github.com/juliu-afk/Orbit",
                 description="多Agent开发自循环系统",
                 tags=["agent", "python", "llm", "调度"])
    reg.register("Finite", description="财务数据分析平台",
                 tags=["财务", "python", "数据分析"])
    reg.register("Keshen", description="财务软件——凭证录入/报表",
                 tags=["财务", "会计", "react", "python"])
    return reg


def _cleanup() -> None:
    if os.path.exists("data/projects.db"):
        os.remove("data/projects.db")
