"""okf_importer.py unit tests — OkfImporter class + frontmatter parsing + edge cases.
Coverage sprint B1-3: 0% → >=70%.

WHY English test data: avoid GBK encoding issues on Windows CI.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orbit.knowledge.okf_importer import OkfImporter


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def mock_engine():
    """KnowledgeEngine with mock SQLite connection."""
    engine = MagicMock()
    conn = MagicMock(spec=sqlite3.Connection)
    engine._store._get_conn.return_value = conn
    return engine


@pytest.fixture
def importer(mock_engine):
    """OkfImporter with mock engine."""
    return OkfImporter(engine=mock_engine)


# ── Constructor ───────────────────────────────────────────


class TestOkfImporterInit:
    """Test __init__."""

    def test_default_engine(self):
        """No engine → creates default KnowledgeEngine."""
        with patch("orbit.knowledge.okf_importer.KnowledgeEngine") as MockEng:
            imp = OkfImporter()
            MockEng.assert_called_once()
            assert imp._engine is MockEng.return_value

    def test_custom_engine(self, mock_engine):
        """Custom engine injected."""
        imp = OkfImporter(engine=mock_engine)
        assert imp._engine is mock_engine


# ── _parse_concept ────────────────────────────────────────


class TestParseConcept:
    """Test _parse_concept() — OKF markdown frontmatter parsing."""

    def test_valid_concept(self, importer, tmp_path):
        """Full frontmatter — parses all fields."""
        md = tmp_path / "asset.md"
        md.write_text("""---
type: Orbit/accounting
title: Asset
description: Resource controlled by entity
x-orbit-formula: Assets = Liabilities + Equity
resource: https://example.com/asset
x-orbit-source-level: 1
---

# Asset

An asset is a resource controlled by the entity as a result of past events.
""", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is not None
        assert result["domain"] == "accounting"
        assert result["concept"] == "asset"
        assert result["name_zh"] == "Asset"
        # definition uses first 1000 chars of body
        assert "resource controlled" in result["definition"].lower()
        assert result["formula"] == "Assets = Liabilities + Equity"
        assert result["source_uri"] == "https://example.com/asset"
        assert result["source_level"] == "1"

    def test_minimal_concept(self, importer, tmp_path):
        """Minimal frontmatter — only type field."""
        md = tmp_path / "minimal.md"
        md.write_text("""---
type: Orbit/tax
---

Basic tax concept description.
""", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is not None
        assert result["domain"] == "tax"
        assert result["concept"] == "minimal"
        assert result["definition"] == "Basic tax concept description."

    def test_no_frontmatter(self, importer, tmp_path):
        """No frontmatter → None."""
        md = tmp_path / "no_fm.md"
        md.write_text("Plain document without frontmatter", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is None

    def test_missing_type(self, importer, tmp_path):
        """Frontmatter without type → None."""
        md = tmp_path / "no_type.md"
        md.write_text("""---
title: Some Concept
description: no type field
---

Content here.
""", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is None

    def test_type_without_slash(self, importer, tmp_path):
        """type without '/' → whole value is domain."""
        md = tmp_path / "simple_type.md"
        md.write_text("""---
type: accounting
---

Simple type
""", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is not None
        assert result["domain"] == "accounting"

    def test_empty_body_defaults_to_description(self, importer, tmp_path):
        """Empty body → uses description as definition."""
        md = tmp_path / "empty_body.md"
        md.write_text("""---
type: Orbit/test
description: test description value
---

""", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is not None
        assert result["definition"] == "test description value"

    def test_default_source_level(self, importer, tmp_path):
        """No source_level → defaults to 3."""
        md = tmp_path / "default_level.md"
        md.write_text("""---
type: Orbit/test
---

""", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is not None
        assert result["source_level"] == 3

    def test_quoted_value_stripped(self, importer, tmp_path):
        """Quoted values → quotes stripped."""
        md = tmp_path / "quoted.md"
        md.write_text('''---
type: "Orbit/finance"
title: "Financial Statement"
---

content
''', encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is not None
        assert result["domain"] == "finance"
        assert result["name_zh"] == "Financial Statement"

    def test_missing_closing_delimiter(self, importer, tmp_path):
        """Frontmatter missing closing '---' → None."""
        md = tmp_path / "malformed.md"
        md.write_text("""---
type: Orbit/test
no closing delimiter
""", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is None

    def test_line_without_colon_skipped(self, importer, tmp_path):
        """Line without colon → skipped, no crash."""
        md = tmp_path / "bad_line.md"
        md.write_text("""---
type: Orbit/test
no_colon_line
---

content
""", encoding="utf-8")

        result = importer._parse_concept(md)
        assert result is not None
        assert result["domain"] == "test"


# ── import_bundle ─────────────────────────────────────────


class TestImportBundle:
    """Test import_bundle() — batch OKF import."""

    def test_missing_bundle_dir(self, importer):
        """Missing bundle dir → returns 0."""
        count = importer.import_bundle("/nonexistent/bundle")
        assert count == 0

    def test_skip_index_and_log(self, importer, tmp_path):
        """index.md and log.md are skipped."""
        bundle = tmp_path / "okf"
        bundle.mkdir()
        (bundle / "index.md").write_text("---\ntype: Orbit/test\n---\n\nx", encoding="utf-8")
        (bundle / "log.md").write_text("---\ntype: Orbit/test\n---\n\nx", encoding="utf-8")

        count = importer.import_bundle(str(bundle))
        assert count == 0

    def test_import_valid_concepts(self, importer, tmp_path):
        """Valid concepts → imported."""
        bundle = tmp_path / "okf"
        bundle.mkdir()
        (bundle / "asset.md").write_text("""---
type: Orbit/accounting
title: Asset
---

Entity resource
""", encoding="utf-8")
        (bundle / "liability.md").write_text("""---
type: Orbit/accounting
title: Liability
---

Entity obligation
""", encoding="utf-8")

        count = importer.import_bundle(str(bundle))
        assert count == 2

    def test_import_nested_dirs(self, importer, tmp_path):
        """Recursive subdirectory import."""
        bundle = tmp_path / "okf"
        bundle.mkdir()
        sub = bundle / "tax"
        sub.mkdir()
        (sub / "vat.md").write_text("""---
type: Orbit/tax
title: VAT
---

VAT description
""", encoding="utf-8")

        count = importer.import_bundle(str(bundle))
        assert count == 1

    def test_import_mixed_valid_invalid(self, importer, tmp_path):
        """Mixed valid/invalid — only valid counted."""
        bundle = tmp_path / "okf"
        bundle.mkdir()
        (bundle / "valid.md").write_text("---\ntype: Orbit/test\n---\n\nOK", encoding="utf-8")
        (bundle / "invalid.md").write_text("No frontmatter", encoding="utf-8")
        (bundle / "index.md").write_text("---\ntype: Orbit/test\n---\n\nx", encoding="utf-8")

        count = importer.import_bundle(str(bundle))
        assert count == 1

    def test_import_parse_error_skipped(self, importer, tmp_path):
        """Parse exception skipped — other files still processed."""
        bundle = tmp_path / "okf"
        bundle.mkdir()
        (bundle / "bad.md").write_text("---\ntype: Orbit/test\n---\n\nOK", encoding="utf-8")

        with patch.object(importer, "_parse_concept", side_effect=Exception("parse error")):
            count = importer.import_bundle(str(bundle))
            assert count == 0  # exception caught, not counted
