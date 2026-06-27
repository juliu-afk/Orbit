"""Compose 流水线单元测试——Parser + Orchestrator + SKILL.md 自发现.

Phase 3 组 3 (AC12): 覆盖 spec 解析、技能加载、任务编排、审查门禁。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def skills_dir():
    """临时 SKILL.md 目录——测试用。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_path = Path(tmpdir)
        # 写几个测试技能文件
        (skills_path / "plan.md").write_text("""---
name: compose:plan
description: write implementation plan
phase: plan
tools: [read_file, grep]
agent_role: architect
---
# compose:plan

## steps
1. read spec
2. write plan
""")
        (skills_path / "review.md").write_text("""---
name: compose:review
description: code review
phase: review
tools: [read_file, grep]
agent_role: reviewer
---
# compose:review

## steps
1. read diff
2. report issues
""")
        yield skills_path


@pytest.fixture
def sample_spec():
    """示例 spec YAML。"""
    return """title: "测试项目"
description: "一个简单的测试项目"
language: python
constraints:
  - "使用 pytest"
  - "覆盖率 >= 80%"
tasks:
  - id: "task-1"
    description: "写单元测试"
    agent_role: "developer"
    skill: "compose:tdd"
  - id: "task-2"
    description: "代码审查"
    agent_role: "reviewer"
    skill: "compose:review"
    depends_on: ["task-1"]
  - id: "task-3"
    description: "验证测试通过"
    agent_role: "qa"
    skill: "compose:verify"
    depends_on: ["task-2"]
"""


class TestComposeParser:
    """ComposeParser——SKILL.md 加载 + Spec 解析。"""

    def test_discover_skills(self, skills_dir):
        from orbit.compose.parser import ComposeParser

        parser = ComposeParser(skills_dir)
        skills = parser.discover_skills()
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"compose:plan", "compose:review"}

    def test_load_skill_by_name(self, skills_dir):
        from orbit.compose.parser import ComposeParser

        parser = ComposeParser(skills_dir)
        skill = parser.load_skill("compose:plan")
        assert skill is not None
        assert skill.name == "compose:plan"
        assert skill.phase.value == "plan"
        assert skill.agent_role == "architect"
        assert "read_file" in skill.tools
        assert "write plan" in skill.body

    def test_load_nonexistent_skill(self, skills_dir):
        from orbit.compose.parser import ComposeParser

        parser = ComposeParser(skills_dir)
        assert parser.load_skill("compose:nonexistent") is None

    def test_skill_cache(self, skills_dir):
        from orbit.compose.parser import ComposeParser

        parser = ComposeParser(skills_dir)
        skills1 = parser.discover_skills()
        skills2 = parser.discover_skills()
        assert skills1 == skills2  # 缓存返回相同内容
        assert len(skills1) == len(skills2)

    def test_parse_spec(self):
        from orbit.compose.parser import ComposeParser

        parser = ComposeParser()
        spec = parser.parse_spec("""title: "test"
description: "desc"
tasks:
  - id: "t1"
    description: "write code"
    agent_role: "developer"
    depends_on: []
""")
        assert spec.title == "test"
        assert len(spec.tasks) == 1
        assert spec.tasks[0].id == "t1"
        assert spec.tasks[0].agent_role == "developer"

    def test_parse_spec_with_dependencies(self):
        from orbit.compose.parser import ComposeParser

        parser = ComposeParser()
        spec = parser.parse_spec("""title: "multi-task"
tasks:
  - id: "t1"
    description: "first"
  - id: "t2"
    description: "second"
    depends_on: ["t1"]
  - id: "t3"
    description: "third"
    depends_on: ["t1", "t2"]
""")
        assert len(spec.tasks) == 3
        assert spec.tasks[2].depends_on == ["t1", "t2"]

    def test_parse_spec_invalid_yaml(self):
        import yaml

        from orbit.compose.parser import ComposeParser

        parser = ComposeParser()
        # yaml 解析失败抛出 YAMLError
        with pytest.raises((ValueError, yaml.YAMLError)):
            parser.parse_spec("- this\nis not a dict")


class TestComposeOrchestrator:
    """ComposeOrchestrator——spec 执行 + 门禁。"""

    @pytest.mark.asyncio
    async def test_run_spec_no_actor_spawn(self):
        """无 ActorSpawn——mock 模式执行所有任务。"""
        from orbit.compose.orchestrator import ComposeOrchestrator

        spec = """title: "simple"
tasks:
  - id: "t1"
    description: "do something"
  - id: "t2"
    description: "do another"
    depends_on: ["t1"]
"""
        orch = ComposeOrchestrator()  # 无 actor_spawn
        result = await orch.run_spec(spec)

        assert result["status"] == "ok"
        assert len(result["tasks"]) == 2
        assert result["tasks"]["t1"]["status"] == "ok"
        assert result["tasks"]["t2"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_spec_review_rejects_empty_title(self):
        from orbit.compose.orchestrator import ComposeOrchestrator

        spec = """title: ""
tasks:
  - id: "t1"
    description: "do something"
"""
        orch = ComposeOrchestrator()
        result = await orch.run_spec(spec)
        assert result["status"] == "error"
        assert "title" in str(result.get("error", ""))

    @pytest.mark.asyncio
    async def test_spec_review_rejects_empty_tasks(self):
        from orbit.compose.orchestrator import ComposeOrchestrator

        spec = """title: "test"
tasks: []
"""
        orch = ComposeOrchestrator()
        result = await orch.run_spec(spec)
        assert result["status"] == "error"
        assert "tasks" in str(result.get("error", ""))

    @pytest.mark.asyncio
    async def test_spec_review_unknown_dependency(self):
        from orbit.compose.orchestrator import ComposeOrchestrator

        spec = """title: "test"
tasks:
  - id: "t1"
    description: "do"
    depends_on: ["nonexistent"]
"""
        orch = ComposeOrchestrator()
        result = await orch.run_spec(spec)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_spec_yaml(self):
        from orbit.compose.orchestrator import ComposeOrchestrator

        orch = ComposeOrchestrator()
        result = await orch.run_spec("invalid: [")
        assert result["status"] == "error"

    def test_topological_sort_linear(self):
        from orbit.compose.models import Task
        from orbit.compose.orchestrator import ComposeOrchestrator

        orch = ComposeOrchestrator()
        tasks = [
            Task(id="t1", description="first"),
            Task(id="t2", description="second", depends_on=["t1"]),
            Task(id="t3", description="third", depends_on=["t2"]),
        ]
        sorted_tasks = orch._topological_sort(tasks)
        ids = [t.id for t in sorted_tasks]
        assert ids == ["t1", "t2", "t3"]

    def test_topological_sort_diamond(self):
        """菱形依赖——t1 → t2, t3 → t4。"""
        from orbit.compose.models import Task
        from orbit.compose.orchestrator import ComposeOrchestrator

        orch = ComposeOrchestrator()
        tasks = [
            Task(id="t1", description="base"),
            Task(id="t2", description="left", depends_on=["t1"]),
            Task(id="t3", description="right", depends_on=["t1"]),
            Task(id="t4", description="merge", depends_on=["t2", "t3"]),
        ]
        sorted_tasks = orch._topological_sort(tasks)
        ids = [t.id for t in sorted_tasks]
        assert ids[0] == "t1"
        assert ids[-1] == "t4"
        # t2 和 t3 在 t1 之后，t4 之前
        assert set(ids[1:3]) == {"t2", "t3"}

    def test_topological_sort_circular_dependency(self):
        """环形依赖——检测并打破。"""
        from orbit.compose.models import Task
        from orbit.compose.orchestrator import ComposeOrchestrator

        orch = ComposeOrchestrator()
        tasks = [
            Task(id="t1", description="a", depends_on=["t2"]),
            Task(id="t2", description="b", depends_on=["t1"]),
        ]
        sorted_tasks = orch._topological_sort(tasks)
        # 环形依赖被打破——所有任务都会在结果中
        assert len(sorted_tasks) == 2


class TestSkillModels:
    """Skill/Spec/Task 模型测试。"""

    def test_skill_creation(self):
        from orbit.compose.models import Skill, SkillPhase

        skill = Skill(
            name="compose:test",
            description="test skill",
            phase=SkillPhase.IMPLEMENT,
            tools=["read_file"],
            body="## test",
        )
        assert skill.name == "compose:test"
        assert skill.tools == ["read_file"]

    def test_spec_creation(self):
        from orbit.compose.models import Spec, Task

        spec = Spec(
            title="test project",
            tasks=[Task(id="t1", description="do it")],
            language="python",
            constraints=["pytest"],
        )
        assert spec.title == "test project"
        assert len(spec.tasks) == 1

    def test_task_max_retries_default(self):
        from orbit.compose.models import Task

        assert Task.MAX_RETRIES == 2
