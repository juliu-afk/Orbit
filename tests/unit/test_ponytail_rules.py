"""Ponytail 决策阶梯 单元测试。"""

from orbit.prompt.ponytail_rules import (
    determine_mode,
    get_ladder,
    LADDER_BY_MODE,
    PONYTAIL_LADDER_FULL,
    PONYTAIL_LADDER_LITE,
    PONYTAIL_LADDER_ULTRA,
    VALID_MODES,
)


class TestGetLadder:
    def test_off_returns_empty(self) -> None:
        assert get_ladder("off") == ""

    def test_lite_returns_lite_ladder(self) -> None:
        result = get_ladder("lite")
        assert result == PONYTAIL_LADDER_LITE
        assert len(result) > 0

    def test_full_returns_full_ladder(self) -> None:
        result = get_ladder("full")
        assert "第 1 级" in result
        assert "第 6 级" in result
        assert "安全底线" in result
        assert "删除优先于新增" in result

    def test_ultra_returns_ultra_ladder(self) -> None:
        result = get_ladder("ultra")
        assert "极简模式" in result
        assert "挑战需求本身" in result

    def test_invalid_mode_falls_back_to_full(self) -> None:
        result = get_ladder("invalid")
        assert result == PONYTAIL_LADDER_FULL

    def test_all_valid_modes_in_ladder_map(self) -> None:
        for mode in VALID_MODES:
            assert mode in LADDER_BY_MODE, f"Missing mode: {mode}"


class TestDetermineMode:
    def test_user_override_takes_priority(self) -> None:
        result = determine_mode(
            task_type="feature",
            project_files=100,
            user_override="ultra",
        )
        assert result == "ultra"

    def test_new_project_defaults_to_ultra(self) -> None:
        result = determine_mode(project_files=2)
        assert result == "ultra"

    def test_bugfix_defaults_to_lite(self) -> None:
        result = determine_mode(task_type="bugfix", project_files=20)
        assert result == "lite"

    def test_refactor_defaults_to_ultra(self) -> None:
        result = determine_mode(task_type="refactor", project_files=20)
        assert result == "ultra"

    def test_feature_with_mature_project_defaults_to_full(self) -> None:
        result = determine_mode(task_type="feature", project_files=50)
        assert result == "full"

    def test_unknown_with_mature_project_defaults_to_full(self) -> None:
        result = determine_mode(project_files=50)
        assert result == "full"

    def test_invalid_user_override_ignored(self) -> None:
        result = determine_mode(
            task_type="feature",
            project_files=10,
            user_override="garbage",
        )
        assert result == "full"  # 忽略无效覆盖值，回归自适应


class TestLadderContent:
    def test_full_ladder_has_all_six_rungs(self) -> None:
        for i in range(1, 7):
            assert f"第 {i} 级" in PONYTAIL_LADDER_FULL, f"Missing rung {i}"

    def test_full_ladder_has_safety_section(self) -> None:
        assert "安全底线" in PONYTAIL_LADDER_FULL
        assert "输入验证" in PONYTAIL_LADDER_FULL
        assert "SQL 注入" in PONYTAIL_LADDER_FULL

    def test_full_ladder_has_supporting_rules(self) -> None:
        assert "删除优先于新增" in PONYTAIL_LADDER_FULL
        assert "无聊胜过聪明" in PONYTAIL_LADDER_FULL
        assert "治根不治标" in PONYTAIL_LADDER_FULL
        assert "ponytail:" in PONYTAIL_LADDER_FULL  # 标记捷径指令

    def test_lite_ladder_is_shorter(self) -> None:
        assert len(PONYTAIL_LADDER_LITE) < len(PONYTAIL_LADDER_FULL)

    def test_ultra_mentions_0_dependency(self) -> None:
        assert "0 依赖原则" in PONYTAIL_LADDER_ULTRA
        assert "删删删" in PONYTAIL_LADDER_ULTRA
