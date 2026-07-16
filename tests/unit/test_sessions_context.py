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

class TestTokenFields:
    """V16.0 Phase E: Token持久化字段测试。"""

    def test_chat_message_has_token_fields(self):
        from orbit.sessions.models import ChatMessageRecord
        r = ChatMessageRecord()
        assert hasattr(r, "input_tokens")
        assert hasattr(r, "output_tokens")
        assert r.input_tokens == 0
        assert r.output_tokens == 0

    def test_token_fields_in_to_dict(self):
        from orbit.sessions.models import ChatMessageRecord
        r = ChatMessageRecord(input_tokens=1500, output_tokens=500)
        d = r.to_dict()
        assert d["input_tokens"] == 1500
        assert d["output_tokens"] == 500
