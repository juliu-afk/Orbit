"""MCP/A2A 抽象分层——TaskContext + AgentResult 单元测试。"""

from orbit.agents.context import AgentResult, TaskContext


class TestTaskContext:
    """TaskContext——L1-L5 五层上下文。"""

    def test_default_context_empty(self) -> None:
        ctx = TaskContext(task_id="t1")
        assert ctx.task_id == "t1"
        assert ctx.l1 == ""
        assert ctx.l2 == {}
        assert ctx.l3 == {}
        assert ctx.l4 == {}
        assert ctx.l5 == []

    def test_context_with_all_layers(self) -> None:
        ctx = TaskContext(
            task_id="t1",
            l1="遵循小企业会计准则, 禁止直接操作总账",
            l2={"code_graph": {"modules": 5}, "db_graph": {"tables": 3}},
            l3={"state": "CODING", "progress": 0.5},
            l4={"last_action": "verify_schema"},
            l5=[{"lesson": "超时重试用指数退避"}],
        )
        assert "小企业会计准则" in ctx.l1
        assert ctx.l2["code_graph"]["modules"] == 5
        assert ctx.l3["state"] == "CODING"
        assert ctx.l4["last_action"] == "verify_schema"
        assert len(ctx.l5) == 1

    def test_to_dict_includes_all_keys(self) -> None:
        ctx = TaskContext(task_id="t1", l1="rule", l3={"key": "val"})
        d = ctx.to_dict()
        assert d["task_id"] == "t1"
        assert "l1" in d
        assert "l2" in d
        assert "l3" in d
        assert "l4" in d
        assert "l5" in d


class TestAgentResult:
    """AgentResult——标准化返回。"""

    def test_success_result(self) -> None:
        r = AgentResult(success=True, output={"done": True}, duration_ms=100)
        assert r.success is True
        assert r.output == {"done": True}
        assert r.error == ""

    def test_error_result(self) -> None:
        r = AgentResult(success=False, error="Agent timeout", duration_ms=5000)
        assert r.success is False
        assert r.error == "Agent timeout"

    def test_to_dict(self) -> None:
        r = AgentResult(success=True, output="result", duration_ms=50)
        d = r.to_dict()
        assert d["success"] is True
        assert d["output"] == "result"
        assert d["duration_ms"] == 50
