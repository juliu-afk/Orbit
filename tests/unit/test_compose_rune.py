"""Compose Spec RUNE 增强 单元测试。"""

from orbit.compose.models import Task


class TestTaskRuneFields:
    def test_task_without_rune(self) -> None:
        task = Task(id="test", description="do something")
        assert not task.has_rune_spec()
        assert task.build_acceptance_prompt() == ""

    def test_task_with_signature(self) -> None:
        task = Task(
            id="create-user",
            description="创建用户",
            signature="async def create_user(db: AsyncSession, data: UserCreate) -> User",
        )
        assert task.has_rune_spec()
        prompt = task.build_acceptance_prompt()
        assert "函数签名" in prompt
        assert "create_user" in prompt

    def test_task_with_behavior(self) -> None:
        task = Task(
            id="validate",
            description="验证输入",
            behavior=[
                "WHEN email 已存在 THEN raise DuplicateError",
                "WHEN password < 8 字符 THEN raise ValidationError",
            ],
        )
        assert task.has_rune_spec()
        prompt = task.build_acceptance_prompt()
        assert "行为契约" in prompt
        assert "WHEN email" in prompt
        assert "WHEN password" in prompt

    def test_task_with_tests(self) -> None:
        task = Task(
            id="tested",
            description="有测试的任务",
            tests=[
                "assert (await create_user(db, valid_data)).email == valid_data.email",
                "await create_user(db, duplicate_email_data)  # expect DuplicateError",
            ],
        )
        assert task.has_rune_spec()
        prompt = task.build_acceptance_prompt()
        assert "验收测试" in prompt
        assert "以下断言必须全部通过" in prompt
        assert "valid_data" in prompt
        assert "DuplicateError" in prompt

    def test_task_full_rune(self) -> None:
        """完整 RUNE 规范——signature + behavior + tests。"""
        task = Task(
            id="full-rune",
            description="完整任务",
            signature="async def process() -> Result",
            behavior=["WHEN X THEN Y"],
            tests=["assert result.ok"],
        )
        assert task.has_rune_spec()
        prompt = task.build_acceptance_prompt()
        assert "函数签名" in prompt
        assert "行为契约" in prompt
        assert "验收测试" in prompt
        assert "## 验收标准" in prompt

    def test_empty_lists_no_rune(self) -> None:
        task = Task(
            id="empty",
            description="空列表",
            signature="",
            behavior=[],
            tests=[],
        )
        assert not task.has_rune_spec()
        assert task.build_acceptance_prompt() == ""


class TestTaskBackwardCompatibility:
    """验证向后兼容——现有 spec 不受影响。"""

    def test_minimal_task_still_works(self) -> None:
        task = Task(id="minimal", description="做最小的事")
        assert task.id == "minimal"
        assert task.description == "做最小的事"
        assert task.agent_role == "developer"  # 默认值
        assert task.depends_on == []
        assert not task.has_rune_spec()
