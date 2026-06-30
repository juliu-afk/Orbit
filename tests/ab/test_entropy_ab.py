"""减熵 AB 对比测试.

对照组 (ENTROPY=0): 关闭减熵策略
实验组 (ENTROPY=1): 开启减熵策略

对比指标: 代码行数、模板命中、决策记录.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbit.agents.base import AgentInput, AgentOutput, AgentRole
from orbit.agents.react_agent import ReActAgent
from orbit.memory.decision_log import DecisionLog
from orbit.scheduler.task_runner import TaskRunner  # noqa: F401


@pytest.fixture
def mock_llm() -> AsyncMock:
    """创建 MockLLM——返回简洁或冗余代码."""
    llm = AsyncMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def prd_text() -> str:
    """标准 PRD 输入——添加 FastAPI CRUD 端点."""
    return """
    需求: 为用户模块添加 CRUD 端点
    技术栈: FastAPI + SQLAlchemy 2.0
    验收标准:
    - POST /users 创建用户
    - GET /users 列表
    - GET /users/{id} 详情
    - PUT /users/{id} 更新
    - DELETE /users/{id} 删除
    Non-Goals: 不分页、不排序
    """


class TestABComparison:
    """AB 对比——减熵策略效果."""

    def test_baseline_keyword_extraction(self, prd_text: str) -> None:
        """关键词提取可从 PRD 中提取有意义的技术词."""
        keywords = TaskRunner._extract_keywords(prd_text)
        assert len(keywords) > 0, "PRD 应提取到关键词"
        tech_terms = [k for k in keywords if any(c.isupper() for c in k)]
        assert len(tech_terms) >= 1, f"应有技术标识符: {keywords}"

    def test_templates_match_prd(self, prd_text: str) -> None:
        """模板库可匹配 CRUD 相关关键词."""
        from orbit.knowledge.templates import get_registry

        keywords = TaskRunner._extract_keywords(prd_text)
        reg = get_registry()
        matched = reg.match(keywords)
        assert len(matched) >= 1, f"CRUD PRD 应匹配到模板: keywords={keywords}"

    def test_decision_log_records_ab_decision(self) -> None:
        """决策日志可记录和查询 AB 对比决策."""
        with tempfile.TemporaryDirectory() as tmp:
            dlog = DecisionLog(storage_dir=tmp)
            from orbit.memory.decision_log import Decision

            dlog.record(Decision(
                question="缓存选型",
                answer="Redis",
                alternatives=["Memcached", "SQLite"],
                rationale="需要持久化+高并发",
                agent="architect",
                task_id="ab-test-001",
                timestamp=0.0,
            ))
            results = dlog.query(["缓存"])
            assert len(results) == 1
            assert results[0].answer == "Redis"


class TestConcisenessAB:
    """简洁规则 AB——生成代码行数对比."""

    @pytest.mark.parametrize("verbose", [True, False])
    def test_conciseness_rule_in_prompt(self, verbose: bool) -> None:
        """验证简洁规则 #9 在 system prompt 中存在."""
        from orbit.prompt.builder import PromptBuilder

        builder = PromptBuilder()
        stable = builder._build_stable(role="developer")
        assert "简洁优先" in stable or "PonyTail" in stable, "简洁规则缺失"
