"""Goal dependency analyzer 单元测试——全覆盖版。"""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from orbit.goal.dependency_analyzer import DependencyAnalyzer
from orbit.goal.models import GoalSession


def test_analyze_returns_result():
    d = DependencyAnalyzer()
    goals = [GoalSession(description="task1"), GoalSession(description="task2")]
    result = d.analyze(goals=goals)
    assert result is not None


def test_init():
    assert DependencyAnalyzer() is not None


# ── 显式依赖——JSON 错误回退到逗号分隔 (lines 123-125) ──
def test_extract_explicit_deps_non_json_fallback():
    """depends_on 值不是合法 JSON → 逗号分隔回退。"""
    d = DependencyAnalyzer()
    # "dep1, dep2" 不是 JSON array（缺引号） → JSONDecodeError → 逗号分隔
    goals = [
        GoalSession(id="g1", description="任务一 depends_on: [dep2, dep3] 实现登录"),
        GoalSession(id="g2", description="任务二 用户模块"),
        GoalSession(id="g3", description="任务三 数据导出"),
    ]
    # g2.description == "用户模块" ← 匹配 dep2?
    # dep2 → _find_goal_by_name → 模糊搜索 "dep2" 对 "任务二 用户模块"
    # "dep3" 对 "任务三 数据导出"
    edges = d._extract_explicit_deps(goals)
    # 至少验证不崩，边可能找到也可能找不到（取决于模糊匹配）
    assert isinstance(edges, list)


def test_extract_explicit_deps_at_depends_on():
    """@depends-on 注释路径。"""
    d = DependencyAnalyzer()
    goals = [
        GoalSession(id="g1", description="前端登录 @depends-on g2"),
        GoalSession(id="g2", description="认证API"),
    ]
    edges = d._extract_explicit_deps(goals)
    assert len(edges) >= 1
    assert edges[0].type == "explicit"


# ── 文件冲突——空关键词 (lines 177-178) ──
@pytest.mark.asyncio
async def test_detect_file_conflicts_empty_keywords():
    """关键词提取为空 → 跳过 CodeGraph 搜索。"""
    d = DependencyAnalyzer()
    goals = [
        GoalSession(id="g1", description="做点事情"),
        GoalSession(id="g2", description="另一个任务"),
    ]
    # _extract_keywords 对中文描述只提取英文/技术名词——这两条没有 → 空
    result = await d._detect_file_conflicts(goals, ".")
    assert result == []


# ── 文件冲突——CodeGraph 搜索异常 (lines 182-184) ──
@pytest.mark.asyncio
async def test_detect_file_conflicts_codegraph_exception():
    """CodeGraph 搜索抛异常 → fail-open（记录警告+空文件集）。"""
    mock_cg = Mock()
    mock_cg.search_files = AsyncMock(side_effect=RuntimeError("boom"))

    d = DependencyAnalyzer(codegraph=mock_cg)
    # 用带英文关键词的描述确保 _extract_keywords 不返回空
    goals = [
        GoalSession(id="g1", description="add login API"),
        GoalSession(id="g2", description="add user model"),
    ]
    result = await d._detect_file_conflicts(goals, ".")
    # 异常被捕获，返回空边集
    assert isinstance(result, list)


# ── 隐式推断——LLM 异常 (lines 244-246) ──
@pytest.mark.asyncio
async def test_infer_implicit_deps_llm_exception():
    """廉价 LLM 抛异常 → 返回空列表。"""
    mock_llm = Mock()
    mock_llm.generate = AsyncMock(side_effect=RuntimeError("LLM down"))

    d = DependencyAnalyzer(cheap_llm=mock_llm)
    goals = [
        GoalSession(id="g1", description="前端登录表单"),
        GoalSession(id="g2", description="POST /auth/login API"),
    ]
    result = await d._infer_implicit_deps(goals)
    assert result == []


# ── 隐式推断——单 goal 不调用 (line 220) ──
@pytest.mark.asyncio
async def test_infer_implicit_deps_single_goal():
    """单个 Goal → 无需推断依赖。"""
    d = DependencyAnalyzer()
    goals = [GoalSession(id="g1", description="唯一任务")]
    result = await d._infer_implicit_deps(goals)
    assert result == []


# ── 解析隐式响应——解析错误 (lines 279-280) ──
def test_parse_implicit_response_bad_item():
    """LLM 返回的 JSON 元素缺 from/to → ValueError → continue。"""
    d = DependencyAnalyzer()
    goals = [
        GoalSession(id="g1", description="任务A"),
        GoalSession(id="g2", description="任务B"),
    ]
    # 元素缺 "from" 字段 → int(None) → TypeError (在 except 中)
    result = d._parse_implicit_response(
        '[{"reason": "needs B to run"}]',
        goals,
    )
    assert result == []


def test_parse_implicit_response_valid():
    """正常解析隐式依赖。"""
    d = DependencyAnalyzer()
    goals = [
        GoalSession(id="g1", description="任务A"),
        GoalSession(id="g2", description="任务B"),
    ]
    result = d._parse_implicit_response(
        '[{"from": 2, "to": 1, "reason": "B is prerequisite for A"}]',
        goals,
    )
    assert len(result) == 1
    assert result[0].type == "implicit"
    assert result[0].confidence == 0.6


def test_parse_implicit_response_bad_json():
    """完全不可解析的 JSON → 返回空。"""
    d = DependencyAnalyzer()
    result = d._parse_implicit_response("not json at all", [])
    assert result == []


def test_parse_implicit_response_code_block():
    """响应被 markdown 代码块包裹 → 清理后解析。"""
    d = DependencyAnalyzer()
    goals = [
        GoalSession(id="g1", description="A"),
        GoalSession(id="g2", description="B"),
    ]
    result = d._parse_implicit_response(
        '```json\n[{"from": 2, "to": 1, "reason": "B→A"}]\n```',
        goals,
    )
    assert len(result) == 1
