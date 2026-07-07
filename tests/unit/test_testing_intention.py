"""testing/intention.py 单元测试。"""

from __future__ import annotations

from orbit.testing.intention import IntentionExtractor, TestIntention


class TestIntentionExtractor:
    """IntentionExtractor 从各输入源提取 TestIntention。"""

    def test_extract_from_code_simple_function(self):
        """从简单函数提取意图。"""
        code = """
def add(a: int, b: int) -> int:
    return a + b
"""
        extractor = IntentionExtractor()
        intention = extractor.extract_from_code(code, "math_utils")

        assert intention.target == "math_utils::add"
        assert len(intention.positive) >= 1
        assert "add" in intention.positive[0]
        assert len(intention.negative) >= 1
        assert "None" in intention.negative[0]

    def test_extract_from_code_with_defaults(self):
        """有默认值的参数 → 生成边界 case。"""
        code = """
def create_user(name: str, age: int = 18) -> dict:
    return {"name": name, "age": age}
"""
        extractor = IntentionExtractor()
        intention = extractor.extract_from_code(code, "users")

        assert len(intention.edge_cases) >= 1
        assert "age" in intention.edge_cases[0]

    def test_extract_from_code_syntax_error(self):
        """语法错误的代码 → 返回空意图（不崩溃）。"""
        extractor = IntentionExtractor()
        intention = extractor.extract_from_code("def broken( ", "bad")
        assert intention.target == "bad"  # 保留 module 名
        assert intention.positive == []

    def test_extract_from_code_skips_self_cls(self):
        """self/cls 参数不被当作测试参数。"""
        code = """
class UserService:
    def create(self, name: str) -> dict:
        return {"name": name}
"""
        extractor = IntentionExtractor()
        intention = extractor.extract_from_code(code, "services.user")
        assert "self" not in str(intention.positive)
        assert "self" not in str(intention.negative)

    def test_extract_from_prd_with_ac(self):
        """从含验收标准的 PRD 提取意图。"""
        prd = """# 用户管理

## 验收标准
- 用户可通过邮箱注册
- 密码必须 >= 8 位
- 邮箱不可重复
"""
        extractor = IntentionExtractor()
        intentions = extractor.extract_from_prd(prd)

        assert len(intentions) >= 1
        assert len(intentions[0].positive) >= 3

    def test_extract_from_prd_no_ac_section(self):
        """无验收标准段的 PRD → 返回空列表。"""
        extractor = IntentionExtractor()
        intentions = extractor.extract_from_prd("# 标题\n\n正文内容。")
        assert intentions == []

    def test_extract_gherkin_generates_scenarios(self):
        """Gherkin 场景骨架从 PRD 验收标准生成。"""
        prd = """## 验收标准
- 用户登录成功
- 密码错误拒绝登录
"""
        extractor = IntentionExtractor()
        scenarios = extractor.extract_gherkin(prd, "登录")
        assert len(scenarios) >= 2
        assert all(s.startswith("Scenario:") for s in scenarios)

    def test_extract_contract_tests_from_api_design(self):
        """从 API 设计文本提取契约测试。"""
        api_design = """
POST /api/v1/users
GET /api/v1/users/{id}
DELETE /api/v1/users/{id}
"""
        extractor = IntentionExtractor()
        contracts = extractor.extract_contract_tests(api_design)

        assert len(contracts) == 3
        assert contracts[0]["method"] == "POST"
        assert contracts[0]["path"] == "/api/v1/users"
        assert all("positive" in c for c in contracts)
        assert all("negative" in c for c in contracts)
