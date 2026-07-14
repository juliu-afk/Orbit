"""SemanticTransfer tests (P2-2 — Fable 5 cross-language equivalence)."""

from orbit.graph.meta_graph import MetaGraph, RelationType, SemanticTransfer


class TestRelationType:
    def test_semantic_equivalent_added(self):
        assert hasattr(RelationType, "SEMANTICALLY_EQUIVALENT_TO")
        assert RelationType.SEMANTICALLY_EQUIVALENT_TO == "SEMANTICALLY_EQUIVALENT_TO"


class TestMetaGraphEquivalence:
    def test_add_and_find_equivalent(self):
        mg = MetaGraph(":memory:")
        mg.add_semantic_equivalent(
            source_id="vendor/rate-limiter/src/lib.rs",
            target_id="src/gateway/rate_limiter.py",
            source_language="rust",
            target_language="python",
            description="Exponential backoff with jitter",
        )
        results = mg.find_equivalents("rate-limiter")
        assert len(results) == 1
        assert results[0]["language"] == "python"
        assert "jitter" in results[0]["description"]

    def test_find_filter_by_language(self):
        mg = MetaGraph(":memory:")
        mg.add_semantic_equivalent("ref/rust", "impl/python", "rust", "python", "desc")
        mg.add_semantic_equivalent("ref/rust", "impl/typescript", "rust", "typescript", "desc")
        py_results = mg.find_equivalents("ref/rust", target_language="python")
        assert len(py_results) == 1
        assert py_results[0]["language"] == "python"
        ts_results = mg.find_equivalents("ref/rust", target_language="typescript")
        assert len(ts_results) == 1
        assert ts_results[0]["language"] == "typescript"

    def test_find_no_match(self):
        mg = MetaGraph(":memory:")
        results = mg.find_equivalents("nonexistent")
        assert results == []


class TestSemanticTransfer:
    def test_link_and_find(self):
        st = SemanticTransfer(meta_graph=MetaGraph(":memory:"))
        st.link(
            source="lib/auth.go",
            target="src/auth.py",
            source_lang="go", target_lang="python",
            description="JWT validation middleware",
        )
        results = st.find("auth.go")
        assert len(results) == 1
        assert results[0]["language"] == "python"

    def test_build_reference_context(self):
        st = SemanticTransfer(meta_graph=MetaGraph(":memory:"))
        st.link("ref/x.rs", "impl/y.py", "rust", "python", "async retry")
        ctx = st.build_reference_context("ref/x.rs", target_language="python")
        assert "Semantic Reference" in ctx
        assert "y.py" in ctx
        assert "async retry" in ctx

    def test_build_reference_context_empty(self):
        st = SemanticTransfer(meta_graph=MetaGraph(":memory:"))
        ctx = st.build_reference_context("nonexistent")
        assert ctx == ""

    def test_multiple_equivalents(self):
        st = SemanticTransfer(meta_graph=MetaGraph(":memory:"))
        st.link("ref/pattern", "impl/a.py", "rust", "python", "A")
        st.link("ref/pattern", "impl/b.ts", "rust", "typescript", "B")
        st.link("ref/pattern", "impl/c.go", "rust", "go", "C")
        all_results = st.find("ref/pattern")
        assert len(all_results) == 3
        py_only = st.find("ref/pattern", target_language="python")
        assert len(py_only) == 1
