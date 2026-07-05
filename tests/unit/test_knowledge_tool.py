"""load_knowledge tool 单元测试——Agent 按需加载知识（Inkeep 借鉴 #3）。

覆盖: 找到知识/未找到/空参数/query_structured 方法。
"""

from __future__ import annotations


class TestLoadKnowledgeHandler:
    """load_knowledge_handler 函数。"""

    def test_handler_found(self):
        """已知概念返回结构化知识。"""
        from orbit.tools.knowledge_tools import load_knowledge_handler

        # "CurrentRatio" 应存在于 accounting 领域的种子数据中
        result = load_knowledge_handler({
            "domain": "accounting",
            "concept": "CurrentRatio",
        })
        assert result["found"] is True
        assert "流动比率" in result["content"] or "CurrentRatio" in result["content"]
        assert "source_uri" in result
        assert "confidence" in result

    def test_handler_not_found(self):
        """不存在的概念返回 found=False。"""
        from orbit.tools.knowledge_tools import load_knowledge_handler

        result = load_knowledge_handler({
            "domain": "accounting",
            "concept": "NonExistentConceptXYZ",
        })
        assert result["found"] is False
        assert "未找到" in result["message"]
        assert "NonExistentConceptXYZ" in result["message"]

    def test_handler_empty_domain(self):
        """空 domain 返回 found=False。"""
        from orbit.tools.knowledge_tools import load_knowledge_handler

        result = load_knowledge_handler({"domain": "", "concept": "Test"})
        assert result["found"] is False
        assert "必填" in result["message"]

    def test_handler_empty_concept(self):
        """空 concept 返回 found=False。"""
        from orbit.tools.knowledge_tools import load_knowledge_handler

        result = load_knowledge_handler({"domain": "accounting", "concept": ""})
        assert result["found"] is False

    def test_handler_missing_params(self):
        """缺少必填参数返回 found=False。"""
        from orbit.tools.knowledge_tools import load_knowledge_handler

        result = load_knowledge_handler({})
        assert result["found"] is False


class TestLoadKnowledgeSchema:
    """Tool JSON Schema 合法性。"""

    def test_schema_valid_openai_format(self):
        from orbit.tools.knowledge_tools import LOAD_KNOWLEDGE_SCHEMA

        assert LOAD_KNOWLEDGE_SCHEMA["type"] == "function"
        func = LOAD_KNOWLEDGE_SCHEMA["function"]
        assert func["name"] == "load_knowledge"
        params = func["parameters"]
        assert "domain" in params["properties"]
        assert "concept" in params["properties"]
        assert set(params["required"]) == {"domain", "concept"}


class TestKnowledgeEngineQueryStructured:
    """KnowledgeEngine.query_structured() 方法。"""

    def test_query_structured_found(self):
        from orbit.knowledge.engine import KnowledgeEngine

        engine = KnowledgeEngine()
        result = engine.query_structured("accounting", "CurrentRatio")
        assert result["found"] is True
        assert "content" in result
        assert "source_uri" in result

    def test_query_structured_not_found(self):
        from orbit.knowledge.engine import KnowledgeEngine

        engine = KnowledgeEngine()
        result = engine.query_structured("nonexistent_domain", "NoConcept")
        assert result["found"] is False
        assert "未找到" in result["message"]
