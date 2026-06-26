"""PromptBuilder 单元测试——三层拼接.

Phase 1 AC9-AC10 验收测试.
"""

import pytest

from orbit.agents.base import AgentRole
from orbit.prompt.builder import PromptBuilder, ROLE_DESCRIPTIONS, RULES_BLOCK, TOOLS_GUIDE_BLOCK


class TestPromptBuilder:
    """AC9-AC10: stable/context/volatile 三层."""

    def test_build_developer(self):
        """构建 Developer 的 system prompt."""
        builder = PromptBuilder()
        prompt = builder.build(
            role=AgentRole.DEVELOPER,
            context={"task": "实现一个加法函数", "project": "Orbit"},
        )
        # stable 层——角色描述
        assert "开发者 Agent" in prompt or "Developer" in prompt
        # stable 层——工具指南
        assert "read_file" in prompt
        assert "exec_command" in prompt
        # stable 层——强制规则
        assert "Decimal" in prompt
        # context 层——项目信息
        assert "Orbit" in prompt
        # volatile 层——当前任务
        assert "加法" in prompt

    def test_build_architect(self):
        """构建 Architect 的 system prompt."""
        builder = PromptBuilder()
        prompt = builder.build(role=AgentRole.ARCHITECT)
        assert "架构师" in prompt or "Architect" in prompt
        # Architect 也需要工具（read_file/grep 了解现有代码结构）
        assert "read_file" in prompt

    def test_build_reviewer(self):
        """构建 Reviewer 的 system prompt."""
        builder = PromptBuilder()
        prompt = builder.build(role=AgentRole.REVIEWER)
        assert "审查员" in prompt or "Reviewer" in prompt

    def test_build_qa(self):
        """构建 QA 的 system prompt."""
        builder = PromptBuilder()
        prompt = builder.build(role=AgentRole.QA)
        assert "QA" in prompt or "验证员" in prompt

    def test_build_config_manager(self):
        """构建 ConfigManager 的 system prompt."""
        builder = PromptBuilder()
        prompt = builder.build(role=AgentRole.CONFIG_MANAGER)
        assert "配置管理员" in prompt or "ConfigManager" in prompt

    def test_stable_layer_cacheable(self):
        """stable 层——相同角色相同内容（可缓存）."""
        builder = PromptBuilder()
        p1 = builder._build_stable(AgentRole.DEVELOPER)
        p2 = builder._build_stable(AgentRole.DEVELOPER)
        assert p1 == p2

    def test_context_layer_project_info(self):
        """context 层——包含项目信息."""
        builder = PromptBuilder()
        ctx = builder._build_context({
            "project": "TestProject",
            "tech_stack": "Python 3.14 + FastAPI",
        })
        assert "TestProject" in ctx
        assert "Python" in ctx

    def test_context_layer_code_truncation(self):
        """context 层——代码上下文超长截断."""
        builder = PromptBuilder()
        long_code = "x" * 6000
        ctx = builder._build_context({"code_context": long_code})
        assert "截断" in ctx

    def test_volatile_layer_task(self):
        """volatile 层——当前任务."""
        builder = PromptBuilder()
        vol = builder._build_volatile({"task": "修复 BUG-42"})
        assert "BUG-42" in vol

    def test_volatile_layer_constraints(self):
        """volatile 层——约束条件."""
        builder = PromptBuilder()
        vol = builder._build_volatile({
            "task": "实现登录",
            "constraints": ["不能使用 OAuth", "JWT 过期时间 24h"],
        })
        assert "OAuth" in vol
        assert "JWT" in vol

    def test_all_roles_have_description(self):
        """所有 AgentRole 都有角色描述."""
        for role in AgentRole:
            assert role in ROLE_DESCRIPTIONS, f"缺少 {role} 的角色描述"

    def test_build_stable_only(self):
        """build_stable_only——只返回 stable 层."""
        builder = PromptBuilder()
        stable = builder.build_stable_only(AgentRole.DEVELOPER)
        # stable 层有角色 + 工具 + 规则
        assert "开发者" in stable or "Developer" in stable
        # 不包含任务
        assert "当前任务" not in stable

    def test_build_system_and_user(self):
        """便捷方法——一次返回 system + user."""
        builder = PromptBuilder()
        result = builder.build_system_and_user(
            role=AgentRole.DEVELOPER,
            task="写个测试",
        )
        assert "system" in result
        assert "user" in result
        assert result["user"] == "写个测试"
