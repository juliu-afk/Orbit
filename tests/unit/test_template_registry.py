"""TemplateRegistry 单元测试——加载→解析→匹配→填充.

Phase 4 模板库减熵 P1。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orbit.knowledge.templates import Template, TemplateRegistry, get_registry

# ── 测试用 .tmpl 内容（模拟文件） ──────────────────────────

_TMPL_CRUD = """\
---
name: crud_endpoint
description: FastAPI CRUD endpoint
keywords: crud, endpoint, api, fastapi, route
parameters: model_name, model_name_lower, table_name, schema_name
---
@router.get("/{{table_name}}/")
async def list_{{model_name_lower}}(db: Session = Depends(get_db)):
    ...
"""

_TMPL_INVALID = """\
no frontmatter here
just body
"""

_TMPL_PARTIAL = """\
---
name: partial
---
"""

_TMPL_MULTI_KW = """\
---
name: multi_kw
description: multi keyword test
keywords: alpha, beta, gamma, delta
parameters: x
---
{{x}}
"""


# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def tmp_templates_dir(tmp_path: Path) -> Path:
    """创建临时模板目录，写入 3 个 .tmpl 文件."""
    (tmp_path / "crud.tmpl").write_text(_TMPL_CRUD, encoding="utf-8")
    (tmp_path / "multi_kw.tmpl").write_text(_TMPL_MULTI_KW, encoding="utf-8")
    (tmp_path / "partial.tmpl").write_text(_TMPL_PARTIAL, encoding="utf-8")
    return tmp_path


# ── 测试: 构造与加载 ──────────────────────────────────


class TestTemplateRegistryInit:
    """注册器初始化与模板加载."""

    def test_load_from_directory(self, tmp_templates_dir: Path):
        """从目录加载 .tmpl 文件."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        assert len(reg.templates) == 3
        assert "crud_endpoint" in reg.templates
        assert "multi_kw" in reg.templates
        assert "partial" in reg.templates

    def test_fallback_when_no_tmpl_files(self, tmp_path: Path):
        """无 .tmpl 文件时加载内置兜底模板."""
        reg = TemplateRegistry(templates_dir=str(tmp_path))
        # 兜底模板有 3 个: crud_endpoint, pydantic_schema, test_unit
        assert len(reg.templates) >= 3
        assert "crud_endpoint" in reg.templates
        assert "pydantic_schema" in reg.templates
        assert "test_unit" in reg.templates

    def test_singleton(self):
        """get_registry() 返回同一实例."""
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_template_dataclass(self):
        """Template dataclass 字段正确."""
        tmpl = Template(
            name="test",
            description="a test template",
            keywords=["a", "b"],
            template_text="hello {{name}}",
            parameters=["name"],
        )
        assert tmpl.name == "test"
        assert tmpl.keywords == ["a", "b"]
        assert tmpl.parameters == ["name"]


# ── 测试: 解析 ────────────────────────────────────────


class TestLoadTemplate:
    """load_template 解析逻辑."""

    def test_parse_frontmatter_and_body(self, tmp_templates_dir: Path):
        """正确解析 frontmatter 和正文."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        tmpl = reg.templates["crud_endpoint"]
        assert tmpl.name == "crud_endpoint"
        assert tmpl.description == "FastAPI CRUD endpoint"
        assert tmpl.keywords == ["crud", "endpoint", "api", "fastapi", "route"]
        assert tmpl.parameters == ["model_name", "model_name_lower", "table_name", "schema_name"]
        assert "@router.get" in tmpl.template_text
        assert "{{table_name}}" in tmpl.template_text

    def test_parse_invalid_no_frontmatter(self, tmp_path: Path):
        """无 frontmatter 的文件抛出 ValueError."""
        bad_file = tmp_path / "bad.tmpl"
        bad_file.write_text(_TMPL_INVALID, encoding="utf-8")
        reg = TemplateRegistry(templates_dir=str(tmp_path))
        # 注册器吞异常，不加载无效文件
        assert "bad" not in reg.templates

    def test_fill_placeholder(self, tmp_templates_dir: Path):
        """fill() 正确替换 {{param}} 占位符."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        result = reg.fill("crud_endpoint", {
            "model_name": "Item",
            "model_name_lower": "item",
            "table_name": "items",
            "schema_name": "ItemOut",
        })
        assert "@router.get(\"/items/\")" in result
        assert "list_item" in result
        assert "list_item" in result  # 测试模板含 list_{{model_name_lower}}

    def test_fill_unknown_template(self, tmp_templates_dir: Path):
        """fill() 不存在的模板抛出 KeyError."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        with pytest.raises(KeyError, match="not_found"):
            reg.fill("not_found", {})


# ── 测试: 匹配 ────────────────────────────────────────


class TestMatch:
    """match 关键词检索."""

    def test_match_by_keywords(self, tmp_templates_dir: Path):
        """按关键词匹配并返回按相关性降序的结果."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        results = reg.match(["crud", "api", "endpoint"])
        assert len(results) >= 1
        names = [t.name for t in results]
        assert "crud_endpoint" in names

    def test_match_empty_keywords(self, tmp_templates_dir: Path):
        """空关键词列表返回空列表."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        assert reg.match([]) == []

    def test_match_no_overlap(self, tmp_templates_dir: Path):
        """无重叠关键词返回空列表."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        results = reg.match(["unrelated", "nonsense"])
        assert results == []

    def test_match_rank_highest_first(self, tmp_templates_dir: Path):
        """匹配度最高的模板排在第一个."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        results = reg.match(["alpha", "beta", "gamma", "delta", "epsilon"])
        assert results
        assert results[0].name == "multi_kw"

    def test_match_case_insensitive(self, tmp_templates_dir: Path):
        """关键词匹配不区分大小写."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        results = reg.match(["CRUD", "ENDPOINT"])
        assert any(t.name == "crud_endpoint" for t in results)


# ── 测试: 边界情况 ────────────────────────────────────


class TestEdgeCases:
    """边界情况."""

    def test_partial_frontmatter(self, tmp_templates_dir: Path):
        """partial frontmatter（少字段）不报错."""
        reg = TemplateRegistry(templates_dir=str(tmp_templates_dir))
        tmpl = reg.templates["partial"]
        assert tmpl.name == "partial"
        assert tmpl.keywords == []
        assert tmpl.parameters == []

    def test_same_name_overwrite(self, tmp_path: Path):
        """同名模板后加载的覆盖先加载的."""
        a = tmp_path / "a.tmpl"
        b = tmp_path / "b.tmpl"
        a.write_text("---\nname: same\n---\nA", encoding="utf-8")
        b.write_text("---\nname: same\n---\nB", encoding="utf-8")
        reg = TemplateRegistry(templates_dir=str(tmp_path))
        assert reg.templates["same"].template_text.strip() == "B"

    def test_missing_parameters_key_still_works(self, tmp_path: Path):
        """parameters 字段缺失时默认空列表."""
        f = tmp_path / "no_params.tmpl"
        f.write_text("---\nname: np\nkeywords: a\n---\nbody", encoding="utf-8")
        reg = TemplateRegistry(templates_dir=str(tmp_path))
        assert reg.templates["np"].parameters == []
        assert reg.templates["np"].template_text.strip() == "body"
