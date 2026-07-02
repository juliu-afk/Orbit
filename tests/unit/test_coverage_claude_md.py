"""覆盖率补测——knowledge/claude_md_generator.py (122行, 15%→85%)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from orbit.knowledge.claude_md_generator import ClaudeMdGenerator


# ════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════

@pytest.fixture
def mock_config():
    """Mock config graph——返回项目元数据。"""
    return {
        "name": "TestProject",
        "description": "测试项目自动化生成 CLAUDE.md",
        "dependencies": {
            "后端": ["FastAPI", "SQLAlchemy"],
            "前端": ["React", "Ant Design"],
        },
        "constraints": [
            "金额用 Decimal 禁止 float",
            "必须写注释",
        ],
        "test_dependencies": ["pytest", "pytest-asyncio"],
        "intercept_rules": [
            "禁止 git add -A",
            "密钥从环境变量读取",
        ],
    }


@pytest.fixture
def mock_code():
    """Mock code graph——返回目录树+主语言。"""
    code = MagicMock()
    code.get_directory_tree.return_value = {"text": "src/\n  api/\n  models/"}
    code.primary_language = "Python"
    return code


@pytest.fixture
def mock_knowledge():
    """Mock knowledge graph——返回概念列表。"""
    knowledge = MagicMock()
    knowledge.list_concepts.return_value = [
        {"name": "Task", "description": "任务实体"},
        {"name": "Agent", "description": "智能代理"},
    ]
    return knowledge


@pytest.fixture
def mock_graphs(mock_config, mock_code, mock_knowledge):
    """组装 GraphManagerProtocol mock。"""
    mgr = MagicMock()
    mgr.config = mock_config
    mgr.code = mock_code
    mgr.knowledge = mock_knowledge
    return mgr


# ════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════

class TestClaudeMdGenerator:
    def test_sections_count(self):
        """SECTIONS 包含 8 个章节。"""
        assert len(ClaudeMdGenerator.SECTIONS) == 8

    @pytest.mark.asyncio
    async def test_generate_full_document(self, mock_graphs):
        """完整 generate()——所有章节组装为 markdown。"""
        gen = ClaudeMdGenerator(mock_graphs)
        result = await gen.generate()

        assert "# 项目概述" in result
        assert "TestProject" in result
        assert "## 技术栈" in result
        assert "FastAPI" in result
        assert "## 项目结构" in result
        assert "src/" in result
        assert "## 术语定义" in result
        assert "Task" in result
        assert "## 实现约束" in result
        assert "Decimal" in result
        assert "## 编码约定" in result
        assert "Python" in result
        assert "## 测试框架" in result
        assert "pytest" in result
        assert "## 行为拦截清单" in result
        assert "git add -A" in result

    @pytest.mark.asyncio
    async def test_generate_overview_no_config(self):
        """无配置时返回默认概述。"""
        mgr = MagicMock()
        mgr.config = MagicMock()
        mgr.config.get.side_effect = Exception("no config")

        gen = ClaudeMdGenerator(mgr)
        result = await gen._extract_overview()
        assert "自动生成" in result

    def test_extract_constraints_empty(self):
        """无约束规则时返回默认提示。"""
        mgr = MagicMock()
        mgr.config = {}
        gen = ClaudeMdGenerator(mgr)
        result = gen._extract_constraints()
        assert "待项目配置后填充" in result

    def test_extract_constraints_with_rules(self, mock_graphs):
        """有约束规则时全部列出。"""
        gen = ClaudeMdGenerator(mock_graphs)
        result = gen._extract_constraints()
        assert "Decimal" in result
        assert "必须写注释" in result

    def test_extract_coding_conventions_no_code(self):
        """无代码图谱 → 返回默认约定。"""
        mgr = MagicMock()
        mgr.code = None
        gen = ClaudeMdGenerator(mgr)
        result = gen._extract_coding_conventions()
        assert "待项目配置后填充" in result

    def test_extract_coding_conventions_with_lang(self, mock_graphs):
        """有代码图谱 → 提取主语言。"""
        gen = ClaudeMdGenerator(mock_graphs)
        result = gen._extract_coding_conventions()
        assert "Python" in result
        assert "PascalCase" in result

    def test_extract_intercept_rules_empty(self):
        """无拦截规则 → 返回默认规则。"""
        mgr = MagicMock()
        mgr.config = {}
        gen = ClaudeMdGenerator(mgr)
        result = gen._extract_intercept_rules()
        assert "git add -A" in result
        assert "新依赖必须先确认" in result
        assert "密钥从环境变量读取" in result

    def test_extract_intercept_rules_with_rules(self, mock_graphs):
        """有拦截规则时列出。"""
        gen = ClaudeMdGenerator(mock_graphs)
        result = gen._extract_intercept_rules()
        assert "git add -A" in result
        assert "密钥从环境变量读取" in result

    def test_assemble_preserves_section_order(self):
        """_assemble() 按 SECTIONS 顺序输出。"""
        gen = ClaudeMdGenerator(MagicMock())
        sections = {
            "项目名称与概述": "# Title\n",
            "技术栈": "## Stack\n",
            "项目结构": "## Structure\n",
            "术语定义": "## Terms\n",
            "实现约束": "## Constraints\n",
            "编码约定": "## Conventions\n",
            "测试框架": "## Tests\n",
            "行为拦截清单": "## Intercepts\n",
        }
        result = gen._assemble(sections)
        idx_title = result.index("# Title")
        idx_stack = result.index("## Stack")
        idx_structure = result.index("## Structure")
        idx_intercepts = result.index("## Intercepts")
        assert idx_title < idx_stack < idx_structure < idx_intercepts

    @pytest.mark.asyncio
    async def test_tech_stack_handles_exception(self):
        """配置图谱异常时优雅降级。"""
        mgr = MagicMock()
        mgr.config = MagicMock()
        mgr.config.get.side_effect = RuntimeError("broken")
        gen = ClaudeMdGenerator(mgr)
        result = await gen._extract_tech_stack()
        assert "自动提取" in result
