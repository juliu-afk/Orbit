"""项目说明书数据模型单元测试。"""

from orbit.brief.models import (
    BasePackage,
    BoundaryRule,
    BriefRecord,
    BriefSection,
    BriefStatus,
    PackageDecision,
    ProjectAnalysis,
    REQUIRED_SECTIONS,
)


class TestBriefSection:
    def test_create_section(self) -> None:
        s = BriefSection(title="摘要", content="这是一个测试项目。")
        assert s.title == "摘要"
        assert s.content == "这是一个测试项目。"


class TestBriefRecord:
    def test_valid_record(self) -> None:
        sections = [BriefSection(title=t, content=f"{t} 内容") for t in REQUIRED_SECTIONS]
        record = BriefRecord(project_name="Test", sections=sections)
        assert record.is_valid()
        assert record.project_name == "Test"

    def test_missing_sections(self) -> None:
        record = BriefRecord(
            project_name="Test",
            sections=[BriefSection(title="摘要", content="...")],
        )
        assert not record.is_valid()

    def test_get_section(self) -> None:
        sections = [BriefSection(title="摘要", content="测试摘要")]
        record = BriefRecord(project_name="Test", sections=sections)
        s = record.get_section("摘要")
        assert s is not None
        assert s.content == "测试摘要"
        assert record.get_section("技术栈") is None

    def test_to_markdown_and_back(self) -> None:
        sections = [BriefSection(title=t, content=f"{t} 内容") for t in REQUIRED_SECTIONS]
        record = BriefRecord(
            project_name="测试项目",
            sections=sections,
            generated_at=1234567890.0,
            generated_by="openai/glm-5.2",
            project_language="python",
            project_framework="fastapi",
        )
        md = record.to_markdown()
        # 检查 HTML 注释中包含元数据
        assert "generated_at: 1234567890.0" in md
        assert "generated_by: openai/glm-5.2" in md
        assert "language: python" in md
        assert "framework: fastapi" in md

        # 反序列化
        parsed = BriefRecord.from_markdown(md, project_name="测试项目")
        assert parsed.project_name == "测试项目"
        assert parsed.is_valid()
        assert len(parsed.sections) == len(REQUIRED_SECTIONS)

    def test_from_markdown_skips_html_comments(self) -> None:
        md = """# Project Brief: Test

## 1. 摘要
测试摘要内容。

## 2. 技术栈
Python 3.11

<!-- generated_at: 123 -->
"""
        record = BriefRecord.from_markdown(md, project_name="Test")
        assert len(record.sections) == 2
        assert record.sections[0].title == "摘要"
        assert record.sections[1].title == "技术栈"


class TestBasePackage:
    def test_to_dict_and_back(self) -> None:
        pkg = BasePackage(
            id="test-pkg",
            language="python",
            framework="fastapi",
            features=["async", "pydantic"],
            description="测试包",
            file_count=5,
            estimated_tokens=1000,
        )
        d = pkg.to_dict()
        assert d["id"] == "test-pkg"
        assert d["language"] == "python"
        assert d["features"] == ["async", "pydantic"]

        pkg2 = BasePackage.from_dict(d)
        assert pkg2.id == pkg.id
        assert pkg2.language == pkg.language
        assert pkg2.features == pkg.features


class TestPackageDecision:
    def test_default_skip(self) -> None:
        d = PackageDecision(decision="skip", reason="无匹配")
        assert d.decision == "skip"
        assert d.package_ids == []

    def test_full_decision(self) -> None:
        d = PackageDecision(
            decision="full",
            package_ids=["pkg-1", "pkg-2"],
            reason="项目文件少，全量注入",
        )
        assert d.decision == "full"
        assert len(d.package_ids) == 2


class TestBriefStatus:
    def test_all_false_by_default(self) -> None:
        s = BriefStatus()
        assert not s.has_brief
        assert not s.has_base_package
        assert not s.has_boundaries

    def test_partial_status(self) -> None:
        s = BriefStatus(has_brief=True, brief_path="/path/to/brief.md")
        assert s.has_brief
        assert not s.has_base_package


class TestBoundaryRule:
    def test_create_rule(self) -> None:
        r = BoundaryRule(
            rule_id="no-eval",
            description="禁止 eval",
            severity="error",
            category="security",
            enforcement={"static_analysis": {"ruff_rules": ["S307"]}, "pre_commit": True},
        )
        assert r.rule_id == "no-eval"
        assert r.severity == "error"
        assert r.enforcement["pre_commit"] is True


class TestProjectAnalysis:
    def test_defaults(self) -> None:
        a = ProjectAnalysis()
        assert a.language == ""
        assert a.file_count == 0
        assert a.key_files == []

    def test_with_data(self) -> None:
        a = ProjectAnalysis(
            language="python",
            framework="fastapi",
            file_count=42,
            python_files=38,
            key_files=["pyproject.toml", "src/main.py"],
            dependencies=["fastapi", "sqlalchemy"],
        )
        assert a.language == "python"
        assert a.file_count == 42
        assert "pyproject.toml" in a.key_files
