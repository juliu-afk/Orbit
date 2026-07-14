"""SemanticTransfer tests (P2-2 — Fable 5 cross-language equivalence)."""
from orbit.graph.meta_graph import MetaGraph, RelationType, SemanticTransfer


class TestRelationType:
    def test_semantic_added(self):
        assert hasattr(RelationType, "SEMANTICALLY_EQUIVALENT_TO")


class TestMetaGraph:
    def test_add_find(self):
        mg = MetaGraph(":memory:")
        mg.add_semantic_equivalent("ref/lib.rs", "impl/x.py", "rust", "python", "retry logic")
        results = mg.find_equivalents("lib.rs")
        assert len(results) == 1
        assert results[0]["language"] == "python"

    def test_filter_by_language(self):
        mg = MetaGraph(":memory:")
        mg.add_semantic_equivalent("ref/x", "impl/py", "rust", "python", "")
        mg.add_semantic_equivalent("ref/x", "impl/ts", "rust", "typescript", "")
        assert len(mg.find_equivalents("ref/x", target_language="python")) == 1
        assert len(mg.find_equivalents("ref/x")) == 2

    def test_no_match(self):
        assert MetaGraph(":memory:").find_equivalents("nope") == []


class TestSemanticTransfer:
    def test_link_find(self):
        st = SemanticTransfer(MetaGraph(":memory:"))
        st.link("lib/auth.go", "src/auth.py", "go", "python", "JWT middleware")
        r = st.find("auth.go")
        assert len(r) == 1
        assert r[0]["language"] == "python"

    def test_reference_context(self):
        st = SemanticTransfer(MetaGraph(":memory:"))
        st.link("ref/x.rs", "impl/y.py", "rust", "python", "async retry")
        ctx = st.build_reference_context("ref/x.rs", "python")
        assert "y.py" in ctx
        assert "async retry" in ctx

    def test_reference_context_empty(self):
        assert SemanticTransfer(MetaGraph(":memory:")).build_reference_context("x") == ""

    def test_reference_context_limit(self):
        """P3-2: verify 5-result cap when many equivalents exist."""
        st = SemanticTransfer(MetaGraph(":memory:"))
        for i in range(8):
            st.link("ref/x", f"impl/{i}.py", "rust", "python", f"variant {i}")
        ctx = st.build_reference_context("ref/x", "python")
        assert "impl/" in ctx
        assert ctx.count("impl/") <= 5
