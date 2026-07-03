"""template_selector.py 单元测试——关键词匹配+模板选择+渲染。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import orbit.scheduler.template_selector  # noqa: F401 — 确保 coverage 追踪模块
from orbit.scheduler.template_selector import TemplateMatch, TemplateSelector


class TestTemplateMatch:
    """TemplateMatch 数据类。"""

    def test_creation(self):
        m = TemplateMatch(
            name="api_route_get",
            file="api_route_get.py.j2",
            description="GET 路由模板",
            confidence=0.8,
            parameters={"entity": "User"},
        )
        assert m.name == "api_route_get"
        assert m.confidence == 0.8

    def test_confidence_bounds(self):
        """confidence 可以是任意 float。"""
        m = TemplateMatch(name="t", file="f", description="d", confidence=1.0, parameters={})
        assert m.confidence == 1.0
        m2 = TemplateMatch(name="t", file="f", description="d", confidence=0.0, parameters={})
        assert m2.confidence == 0.0


class TestMatchScore:
    """_match_score 纯函数——关键词匹配打分。"""

    def test_exact_match_single_condition(self):
        """applicable_when 完全命中 → 0.5。"""
        tpl = {"applicable_when": ["新增 API"]}
        score = TemplateSelector._match_score("新增 api 端点", tpl)
        assert score == 0.5

    def test_exact_match_multiple_conditions(self):
        """多个 keywords 各 0.5。"""
        tpl = {"applicable_when": ["新增", "API", "路由"]}
        score = TemplateSelector._match_score("新增 api 路由", tpl)
        assert score == 1.5  # 3 × 0.5

    def test_token_match(self):
        """applicable_when 含 "/" 时走分词匹配——每个 token ≥2 字符命中 +0.2。"""
        tpl = {"applicable_when": ["新增/查询/删除"]}
        # "新增" 在 task 中 → +0.2, "查询" → +0.2, "删除" → +0.2
        score = TemplateSelector._match_score("新增查询删除功能", tpl)
        assert abs(score - 0.6) < 0.001

    def test_token_partial(self):
        """只有部分 token 命中。"""
        tpl = {"applicable_when": ["新增/查询/删除"]}
        # "新增" hit, "查询" hit, "删除" not in task
        score = TemplateSelector._match_score("新增查询api", tpl)
        assert abs(score - 0.4) < 0.001  # 2 × 0.2

    def test_token_short_filtered(self):
        """≤1 字符的 token 不参与匹配。"""
        tpl = {"applicable_when": ["a/b/c"]}
        score = TemplateSelector._match_score("a b c", tpl)
        assert score == 0.0  # 所有 token 都 <2 字符

    def test_no_match(self):
        """没有任何关键词命中。"""
        tpl = {"applicable_when": ["ORM", "数据库"]}
        score = TemplateSelector._match_score("api 路由 前端", tpl)
        assert score == 0.0

    def test_empty_applicable_when(self):
        """没有 applicable_when → 0 分。"""
        tpl = {}
        score = TemplateSelector._match_score("anything", tpl)
        assert score == 0.0

    def test_exact_beats_token(self):
        """精确匹配(0.5)和分词匹配(0.2)可共存。"""
        tpl = {"applicable_when": ["API", "新增/查询"]}
        # "API" exact → 0.5, "新增" token → 0.2, "查询" token → 0.2
        score = TemplateSelector._match_score("api 新增查询", tpl)
        assert abs(score - 0.9) < 0.001

    def test_exact_match_case_insensitive(self):
        """task_lower 和 cond_lower 都已转小写。"""
        tpl = {"applicable_when": ["ORM Model"]}
        score = TemplateSelector._match_score("orm model test", tpl)
        assert score == 0.5


class TestSelect:
    """TemplateSelector.select 方法——纯逻辑，mock manifest。"""

    def _make_selector(self) -> TemplateSelector:
        """创建一个不读文件的 TemplateSelector，手动注入 _manifest。"""
        sel = TemplateSelector.__new__(TemplateSelector)
        sel._manifest = {
            "templates": [
                {
                    "name": "api_route_get",
                    "file": "api_route_get.py.j2",
                    "description": "GET 路由模板",
                    "applicable_when": ["API", "路由", "GET"],
                    "parameters": [{"name": "entity", "example": "User"}],
                },
                {
                    "name": "db_model",
                    "file": "db_model.py.j2",
                    "description": "SQLAlchemy 模型模板",
                    "applicable_when": ["ORM", "模型", "数据库"],
                    "parameters": [{"name": "table_name", "example": "users"}],
                },
                {
                    "name": "service_layer",
                    "file": "service.py.j2",
                    "description": "Service 层模板",
                    "applicable_when": ["Service", "业务逻辑"],
                    "parameters": [],
                },
            ]
        }
        return sel

    def test_select_returns_top_n(self):
        sel = self._make_selector()
        # "API" + "路由" + "GET" 全部匹配 api_route_get，其他模板不匹配
        matches = sel.select("新增 API 路由 GET 数据库 ORM", top_n=2)
        assert len(matches) == 2  # api_route_get + db_model

    def test_select_returns_all_when_fewer_than_top_n(self):
        sel = self._make_selector()
        matches = sel.select("新增 API 路由", top_n=5)
        assert len(matches) <= 3  # manifest 只有 3 个模板

    def test_select_sorted_by_confidence(self):
        sel = self._make_selector()
        matches = sel.select("API 路由 GET ORM 模型 数据库")
        assert len(matches) >= 2
        # 按 confidence 降序排列
        for i in range(len(matches) - 1):
            assert matches[i].confidence >= matches[i + 1].confidence

    def test_select_confidence_clamped(self):
        """confidence > 1.0 时被 min(score, 1.0) 截断。"""
        sel = TemplateSelector.__new__(TemplateSelector)
        sel._manifest = {
            "templates": [
                {
                    "name": "t",
                    "file": "t.j2",
                    "description": "d",
                    "applicable_when": ["a", "b", "c", "d"],  # 4 × 0.5 = 2.0 → clamped to 1.0
                    "parameters": [],
                },
            ]
        }
        matches = sel.select("a b c d")
        assert len(matches) == 1
        assert matches[0].confidence == 1.0  # min(2.0, 1.0)

    def test_select_rounds_to_two_decimals(self):
        """confidence 四舍五入到 2 位小数。"""
        sel = TemplateSelector.__new__(TemplateSelector)
        sel._manifest = {
            "templates": [
                {
                    "name": "t",
                    "file": "t.j2",
                    "description": "d",
                    "applicable_when": ["新增/查询"],  # 2 tokens × 0.2 = 0.4
                    "parameters": [],
                },
            ]
        }
        matches = sel.select("新增查询")
        assert len(matches) == 1
        assert abs(matches[0].confidence - 0.4) < 0.001  # round(0.4, 2) == 0.4

    def test_select_fills_parameters(self):
        """匹配结果包含模板参数及 example。"""
        sel = self._make_selector()
        matches = sel.select("API 路由 GET")
        assert len(matches) > 0
        api = [m for m in matches if m.name == "api_route_get"][0]
        assert api.parameters == {"entity": "User"}

    def test_select_no_match_returns_empty(self):
        sel = self._make_selector()
        matches = sel.select("完全不相关的关键词")
        assert matches == []


class TestLoadManifest:
    """_load_manifest 内部逻辑。"""

    def test_manifest_missing(self, tmp_path):
        """无 MANIFEST.yaml → _manifest 为空。"""
        sel = TemplateSelector.__new__(TemplateSelector)
        sel._dir = tmp_path
        sel._load_manifest()
        assert sel._manifest == {"templates": []}

    def test_manifest_exists(self, tmp_path):
        """有 MANIFEST.yaml → 正确加载。"""
        manifest_content = """templates:
  - name: t1
    file: t1.j2
    description: d1
    applicable_when:
      - api
    parameters: []
"""
        manifest_path = tmp_path / "MANIFEST.yaml"
        manifest_path.write_text(manifest_content, encoding="utf-8")

        sel = TemplateSelector.__new__(TemplateSelector)
        sel._dir = tmp_path
        sel._load_manifest()
        assert len(sel._manifest["templates"]) == 1
        assert sel._manifest["templates"][0]["name"] == "t1"
        assert sel._manifest["templates"][0]["file"] == "t1.j2"


class TestRender:
    """render 方法——mock Jinja2。"""

    def test_render_with_extra_params(self):
        """render 合并模板参数和额外参数。"""
        sel = TemplateSelector.__new__(TemplateSelector)
        # mock jinja_env
        mock_template = MagicMock()
        mock_template.render.return_value = "rendered output"
        mock_jinja_env = MagicMock()
        mock_jinja_env.get_template.return_value = mock_template
        sel._jinja_env = mock_jinja_env

        match = TemplateMatch(
            name="api_route",
            file="api.j2",
            description="API route",
            confidence=0.8,
            parameters={"entity": "User"},
        )
        result = sel.render(match, extra_params={"method": "GET"})
        assert result == "rendered output"
        # verify params merged
        mock_template.render.assert_called_once_with(entity="User", method="GET")

    def test_render_without_extra_params(self):
        """render 无额外参数时只用模板参数。"""
        sel = TemplateSelector.__new__(TemplateSelector)
        mock_template = MagicMock()
        mock_template.render.return_value = "rendered"
        mock_jinja_env = MagicMock()
        mock_jinja_env.get_template.return_value = mock_template
        sel._jinja_env = mock_jinja_env

        match = TemplateMatch(
            name="t", file="t.j2", description="d", confidence=0.5,
            parameters={"table": "users"},
        )
        result = sel.render(match)
        assert result == "rendered"
        mock_template.render.assert_called_once_with(table="users")


class TestInit:
    """__init__ 与默认模板目录。"""

    def test_default_templates_dir(self):
        """默认的 templates_dir 指向 knowledge/templates。"""
        sel = TemplateSelector()
        assert "knowledge" in str(sel._dir)
        assert "templates" in str(sel._dir)
