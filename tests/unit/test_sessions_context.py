import pytest
class TestSessions:
    def test_fts(self):
        from orbit.sessions.fts import SessionFTS
        assert SessionFTS() is not None
class TestContext:
    def test_relevance(self):
        from orbit.context.relevance import extract_relevant_context
        r = extract_relevant_context("def a(): pass\ndef b(): pass", ["a"])
        assert "a" in r
class TestKnowledgeTemplates:
    def test_registry(self):
        from orbit.knowledge.templates.registry import TemplateRegistry
        assert TemplateRegistry() is not None
class TestFiles:
    def test_handler(self):
        from orbit.files.handler import FileHandler
        assert FileHandler() is not None
class TestPromptPonytail:
    def test_rules(self):
        from orbit.prompt.ponytail_rules import PONYTAIL_RULES
        assert isinstance(PONYTAIL_RULES, (dict, list))
