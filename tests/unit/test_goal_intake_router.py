"""IntakeRouter 单元测试——形态检测/清晰度评分/拆解度评分/route 判定。"""

from __future__ import annotations

import pytest

from orbit.goal.intake_router import CLARITY_MARKERS, DECOMPOSITION_MARKERS, IntakeRouter
from orbit.goal.models import GoalSession, IntakeDecision


class TestDetectForm:
    """_detect_form 四种输入形态。"""

    def test_vague_string(self):
        """无特征描述 → vague_string。"""
        goal = GoalSession(description="帮我改改代码")
        form = IntakeRouter._detect_form(goal)
        assert form == "vague_string"

    def test_batch_from_flag(self):
        """含 --from → batch。"""
        goal = GoalSession(description="--from docs/req.md")
        form = IntakeRouter._detect_form(goal)
        assert form == "batch"

    def test_batch_three_tier_memory(self):
        """goal.three_tier_memory 含 batch_goals → batch。"""
        goal = GoalSession(description="批量处理", three_tier_memory={"batch_goals": ["a", "b"]})
        form = IntakeRouter._detect_form(goal)
        assert form == "batch"

    def test_single_file_md_path(self):
        """.md 结尾且含路径分隔符 → single_file。"""
        goal = GoalSession(description="/home/user/req.md")
        form = IntakeRouter._detect_form(goal)
        assert form == "single_file"

    def test_task_only_keywords(self):
        """含子任务关键词 → task_only。"""
        goal = GoalSession(description="## 任务列表\ndepends_on: A\n")
        form = IntakeRouter._detect_form(goal)
        assert form == "task_only"

    def test_single_file_does_not_exist_with_slash(self):
        """路径不存在但有 '/' → 仍判定为 single_file。"""
        goal = GoalSession(description="nonexistent/path/req.md")
        form = IntakeRouter._detect_form(goal)
        assert form == "single_file"

    def test_md_not_starting_with_double_dash(self):
        """.md 但以 -- 开头 → 不是文件路径。"""
        goal = GoalSession(description="--help.md")
        form = IntakeRouter._detect_form(goal)
        # --help.md 虽以 .md 结尾，但也以 -- 开头 → 不是 single_file
        # 且不含子任务关键词 → vague_string
        assert form == "vague_string"

    def test_task_only_english(self):
        """英文 Task 关键词 → task_only。"""
        goal = GoalSession(description="## tasks\ndepends_on: A")
        form = IntakeRouter._detect_form(goal)
        assert form == "task_only"


class TestScoreClarity:
    """_score_clarity 评分逻辑。"""

    def test_empty_text(self):
        """空文本 → 0.0。"""
        score = IntakeRouter._score_clarity("")
        assert score == 0.0

    def test_short_text(self):
        """短文本 50-200 → 0.05。"""
        score = IntakeRouter._score_clarity("a" * 60)
        assert score >= 0.05

    def test_medium_text(self):
        """中等文本 200-500 → 0.10。"""
        score = IntakeRouter._score_clarity("a" * 250)
        assert score >= 0.10

    def test_long_text(self):
        """长文本 >500 → 0.20。"""
        score = IntakeRouter._score_clarity("a" * 600)
        assert score >= 0.20

    def test_yaml_frontmatter(self):
        """YAML frontmatter → +0.15。"""
        score = IntakeRouter._score_clarity("---\ntitle: test\n---")
        assert score >= 0.15

    def test_acceptance_criteria_marker(self):
        """验收标准 → +0.18。"""
        score = IntakeRouter._score_clarity("验收标准: 功能正常")
        assert score >= 0.18

    def test_verification_marker(self):
        """验证命令 → +0.12。"""
        score = IntakeRouter._score_clarity("验证命令: pytest tests/")
        assert score >= 0.12

    def test_all_markers_combined(self):
        """多个关键词累积。"""
        text = (
            "---\ntitle: spec\n---\n"
            "验收标准: 功能正常\n"
            "验证命令: pytest\n"
            "约束: 无外部依赖\n"
            "Non-Goals: 不做性能优化\n"
            "pytest 测试通过"
        )
        score = IntakeRouter._score_clarity(text)
        # 0.15(frontmatter) + 0.18 + 0.12 + 0.10 + 0.10 + 0.12 = 0.77 + 可能长度分
        assert score >= 0.50
        assert score <= 1.0

    def test_individual_marker_weights(self):
        """各标记权重匹配 CLARITY_MARKERS。"""
        for marker, expected_weight in CLARITY_MARKERS.items():
            score = IntakeRouter._score_clarity(marker)
            assert score >= expected_weight, f"{marker} 权重 {expected_weight} 未命中"

    def test_capped_at_one(self):
        """超过 1.0 → 裁剪为 1.0。"""
        text = "---\n" + "\n".join(CLARITY_MARKERS.keys()) + "a" * 1000
        score = IntakeRouter._score_clarity(text)
        assert score == 1.0


class TestScoreDecomposition:
    """_score_decomposition 评分逻辑。"""

    def test_empty_text(self):
        """空文本 → 0.0。"""
        score = IntakeRouter._score_decomposition("")
        assert score == 0.0

    def test_subtask_marker(self):
        """## 子任务 → +0.20。"""
        score = IntakeRouter._score_decomposition("## 子任务列表")
        assert score >= 0.20

    def test_task_list_marker(self):
        """任务列表 → +0.15。"""
        score = IntakeRouter._score_decomposition("任务列表: 1. 功能A")
        assert score >= 0.15

    def test_depends_on(self):
        """depends_on → +0.20。"""
        score = IntakeRouter._score_decomposition("depends_on: task_1")
        assert score >= 0.20

    def test_dag_keyword(self):
        """DAG → +0.05。"""
        score = IntakeRouter._score_decomposition("DAG 依赖图")
        assert score >= 0.05

    def test_individual_decomp_markers(self):
        """各拆解标记权重匹配 DECOMPOSITION_MARKERS。"""
        for marker, expected_weight in DECOMPOSITION_MARKERS.items():
            score = IntakeRouter._score_decomposition(marker)
            assert score >= expected_weight, f"{marker} 权重 {expected_weight} 未命中"

    def test_markdown_table_with_task_header(self):
        """含任务表头的 Markdown 表格 → +0.15。"""
        text = "| 任务 | 描述 |\n| --- | --- |\n| T1 | 实现A |"
        score = IntakeRouter._score_decomposition(text)
        assert score >= 0.15

    def test_markdown_table_without_task_header(self):
        """无任务关键词的表格 → 不加分。"""
        text = "| 列1 | 列2 |\n| --- | --- |\n| A | B |"
        score = IntakeRouter._score_decomposition(text)
        # 0 + 0 = 0
        assert score < 0.01

    def test_capped_at_one(self):
        """超过 1.0 → 裁剪为 1.0。"""
        text = "\n".join(DECOMPOSITION_MARKERS.keys()) + "\n| 任务 | --- |"
        score = IntakeRouter._score_decomposition(text)
        assert score == 1.0


class TestRoute:
    """route() 完整判定逻辑。"""

    @pytest.mark.asyncio
    async def test_route_batch(self):
        """batch 模式 → is_batch=True, needs_clarify=False。"""
        router = IntakeRouter()
        goal = GoalSession(description="--from multi.md")
        result = await router.route(goal)
        assert result.is_batch
        assert result.needs_clarify is False
        assert result.needs_decompose is False
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_route_clarity_high(self):
        """清晰度 >= 0.7 → 跳过澄清。"""
        router = IntakeRouter()
        # 构建高清晰度文本
        text = "a" * 600 + "\n验收标准: 全通过\n验证命令: pytest\n约束: 无\nNon-Goals: 无\n"
        goal = GoalSession(description=text)
        result = await router.route(goal)
        assert result.needs_clarify is False
        assert "跳过澄清" in result.reason_clarify

    @pytest.mark.asyncio
    async def test_route_clarity_medium(self):
        """清晰度 0.4-0.7 → 需要补齐。"""
        router = IntakeRouter()
        # 多个关键词叠加使清晰度落在 0.4-0.7 区间
        text = "pytest 测试通过\n约束: 限制\n验收标准: 全部功能正常"
        goal = GoalSession(description=text)
        result = await router.route(goal)
        assert result.needs_clarify is True
        assert "补齐缺口" in result.reason_clarify

    @pytest.mark.asyncio
    async def test_route_clarity_low(self):
        """清晰度 < 0.4 → 全量澄清。"""
        router = IntakeRouter()
        goal = GoalSession(description="帮我改改代码")
        result = await router.route(goal)
        assert result.needs_clarify is True
        assert "全量澄清" in result.reason_clarify

    @pytest.mark.asyncio
    async def test_route_decomp_high(self):
        """拆解度 >= 0.7 → 跳过拆解。"""
        router = IntakeRouter()
        text = "## 子任务\ndepends_on: task_x\n任务列表: A, B\nagent_role: dev\n拓扑: a→b"
        goal = GoalSession(description=text)
        result = await router.route(goal)
        assert result.needs_decompose is False
        assert "跳过拆解" in result.reason_decompose

    @pytest.mark.asyncio
    async def test_route_decomp_partial(self):
        """拆解度 > 0 但 < 0.7 → 需补充拆解。"""
        router = IntakeRouter()
        goal = GoalSession(description="依赖: task_A")
        result = await router.route(goal)
        assert result.reason_decompose == "部分子任务——需补充拆解"

    @pytest.mark.asyncio
    async def test_route_returns_decision_object(self):
        """route 返回 IntakeDecision 实例。"""
        router = IntakeRouter()
        goal = GoalSession(description="测试输入")
        result = await router.route(goal)
        assert isinstance(result, IntakeDecision)
        assert 0 <= result.clarity_score <= 1
        assert 0 <= result.decomposition_score <= 1
        assert isinstance(result.is_batch, bool)
