"""file_parser.py unit tests — PDF/DOCX/XLSX/PPTX/TXT parsing + edge cases.
Coverage sprint B1-1: 0% → >=60%.

WHY: local imports (from pypdf import PdfReader inside function body)
require sys.modules mocking, not module-level patch.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orbit.tools.file_parser import (
    _parse_docx,
    _parse_pdf,
    _parse_pptx,
    _parse_text,
    _parse_xlsx,
    file_parser,
)


# ── Helpers ───────────────────────────────────────────────


def _mock_pypdf():
    """Insert mock pypdf module into sys.modules."""
    mock = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "page content"
    mock.PdfReader.return_value.pages = [mock_page]
    mock.PdfReader.return_value.__len__ = lambda self: len(mock.PdfReader.return_value.pages)
    sys.modules["pypdf"] = mock
    return mock


def _mock_docx():
    """Insert mock docx module into sys.modules."""
    mock = MagicMock()
    mock.Document.return_value.paragraphs = []
    mock.Document.return_value.tables = []
    sys.modules["docx"] = mock
    return mock


def _mock_openpyxl():
    """Insert mock openpyxl module into sys.modules."""
    mock = MagicMock()
    mock_ws = MagicMock()
    mock_ws.iter_rows.return_value = []
    mock_wb = MagicMock()
    mock_wb.sheetnames = ["Sheet1"]
    mock_wb.__getitem__.return_value = mock_ws
    mock.load_workbook.return_value.__enter__ = MagicMock(return_value=mock_wb)
    mock.load_workbook.return_value.__exit__ = MagicMock(return_value=False)
    sys.modules["openpyxl"] = mock
    return mock


def _mock_pptx():
    """Insert mock pptx module into sys.modules."""
    mock_pptx = MagicMock()
    sys.modules["pptx"] = mock_pptx
    sys.modules["pptx.util"] = MagicMock()
    return mock_pptx


def _cleanup_modules(*names):
    """Remove mock modules from sys.modules after test."""
    for name in names:
        sys.modules.pop(name, None)


# ── file_parser async entry ───────────────────────────────


class TestFileParserEntry:
    """Test file_parser() async entry — routes to correct parser."""

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            await file_parser("/nonexistent/file.pdf")

    @pytest.mark.asyncio
    async def test_unsupported_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"binary data")
            path = f.name
        try:
            with pytest.raises(ValueError):
                await file_parser(path)
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_pdf_route(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake pdf")
            path = f.name
        try:
            with patch("orbit.tools.file_parser._parse_pdf", return_value={"text": "mock", "pages": 1, "file_type": "pdf"}) as mock_fn:
                result = await file_parser(path)
                mock_fn.assert_called_once()
                assert result["file_type"] == "pdf"
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_docx_route(self):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"PK\x03\x04 fake docx")
            path = f.name
        try:
            with patch("orbit.tools.file_parser._parse_docx", return_value={"text": "mock", "pages": 1, "file_type": "docx"}) as mock_fn:
                result = await file_parser(path)
                mock_fn.assert_called_once()
                assert result["file_type"] == "docx"
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_xlsx_route(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(b"PK\x03\x04 fake xlsx")
            path = f.name
        try:
            with patch("orbit.tools.file_parser._parse_xlsx", return_value={"text": "mock", "pages": 1, "file_type": "xlsx"}) as mock_fn:
                result = await file_parser(path)
                mock_fn.assert_called_once()
                assert result["file_type"] == "xlsx"
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_pptx_route(self):
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            f.write(b"PK\x03\x04 fake pptx")
            path = f.name
        try:
            with patch("orbit.tools.file_parser._parse_pptx", return_value={"text": "mock", "pages": 1, "file_type": "pptx"}) as mock_fn:
                result = await file_parser(path)
                mock_fn.assert_called_once()
                assert result["file_type"] == "pptx"
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_text_route(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello world")
            path = f.name
        try:
            result = await file_parser(path)
            assert result["file_type"] == "txt"
            assert "hello world" in result["text"]
        finally:
            Path(path).unlink()

    @pytest.mark.asyncio
    async def test_code_file_routes_to_text(self):
        for ext in [".py", ".js", ".ts", ".json", ".yaml", ".md"]:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(b"content")
                path = f.name
            try:
                result = await file_parser(path)
                assert result["file_type"] == ext.lstrip(".")
            finally:
                Path(path).unlink()


# ── _parse_text ───────────────────────────────────────────


class TestParseText:
    """Test _parse_text() — plain text parsing."""

    def test_read_text(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
            f.write("hello\nworld")
            path = Path(f.name)
        try:
            result = _parse_text(path)
            assert result["pages"] == 1
            assert result["file_type"] == "txt"
            assert "hello" in result["text"]
        finally:
            path.unlink()

    def test_read_binary_as_replace(self):
        """Non-decodable bytes use U+FFFD replacement, no crash."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello\xffworld")
            path = Path(f.name)
        try:
            result = _parse_text(path)
            assert result["file_type"] == "txt"
        finally:
            Path(path).unlink()

    def test_file_type_from_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{"a":1}')
            path = Path(f.name)
        try:
            result = _parse_text(path)
            assert result["file_type"] == "json"
        finally:
            Path(path).unlink()


# ── _parse_pdf (sys.modules mock) ─────────────────────────


class TestParsePdf:
    """Test _parse_pdf() — mock pypdf via sys.modules."""

    def test_parse_pdf_basic(self):
        mock = _mock_pypdf()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "page content"
        mock.PdfReader.return_value.pages = [mock_page, mock_page]
        try:
            result = _parse_pdf(Path("test.pdf"))
            assert result["file_type"] == "pdf"
            assert result["pages"] == 2
            assert "page content" in result["text"]
        finally:
            _cleanup_modules("pypdf")

    def test_parse_pdf_exceeds_max_pages(self):
        """Exceeds MAX_PDF_PAGES — truncation marker appears."""
        mock = _mock_pypdf()
        pages = [MagicMock() for _ in range(5)]
        for p in pages:
            p.extract_text.return_value = "x"
        mock.PdfReader.return_value.pages = pages
        try:
            with patch("orbit.tools.file_parser.MAX_PDF_PAGES", 3):
                result = _parse_pdf(Path("big.pdf"))
                assert result["pages"] == 5  # original page count
                assert "..." in result["text"]  # truncation marker
        finally:
            _cleanup_modules("pypdf")


# ── _parse_docx (sys.modules mock) ────────────────────────


class TestParseDocx:
    """Test _parse_docx() — mock python-docx via sys.modules."""

    def test_parse_docx_basic(self):
        mock = _mock_docx()
        para1 = MagicMock()
        para1.text = "paragraph one"
        para2 = MagicMock()
        para2.text = ""
        para3 = MagicMock()
        para3.text = "paragraph two"
        mock.Document.return_value.paragraphs = [para1, para2, para3]
        try:
            result = _parse_docx(Path("test.docx"))
            assert result["file_type"] == "docx"
            assert "paragraph one" in result["text"]
            assert "paragraph two" in result["text"]
        finally:
            _cleanup_modules("docx")

    def test_parse_docx_with_table(self):
        mock = _mock_docx()
        cell1 = MagicMock()
        cell1.text = "A"
        cell2 = MagicMock()
        cell2.text = "B"
        row = MagicMock()
        row.cells = [cell1, cell2]
        table = MagicMock()
        table.rows = [row]
        mock.Document.return_value.tables = [table]
        try:
            result = _parse_docx(Path("test.docx"))
            assert "A | B" in result["text"]
        finally:
            _cleanup_modules("docx")


# ── _parse_xlsx (sys.modules mock) ────────────────────────


class TestParseXlsx:
    """Test _parse_xlsx() — mock openpyxl via sys.modules.
    WHY no context manager: _parse_xlsx calls load_workbook() directly,
    not as context manager. wb.close() called separately.
    """

    def test_parse_xlsx_basic(self):
        mock = _mock_openpyxl()
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [("Name", "Value"), ("foo", "bar")]
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__.return_value = mock_ws
        mock.load_workbook.return_value = mock_wb
        try:
            result = _parse_xlsx(Path("test.xlsx"))
            assert result["file_type"] == "xlsx"
            assert result["pages"] == 1
            assert "Name | Value" in result["text"]
        finally:
            _cleanup_modules("openpyxl")

    def test_parse_xlsx_max_rows(self):
        mock = _mock_openpyxl()
        rows = [("col",)] + [("data",)] * 10
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = rows
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["S1"]
        mock_wb.__getitem__.return_value = mock_ws
        mock.load_workbook.return_value = mock_wb
        try:
            with patch("orbit.tools.file_parser.MAX_XLSX_ROWS", 3):
                result = _parse_xlsx(Path("test.xlsx"))
                assert "..." in result["text"]
        finally:
            _cleanup_modules("openpyxl")

    def test_parse_xlsx_empty_cell(self):
        """None cell → empty string, no crash."""
        mock = _mock_openpyxl()
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [("a", None, "c")]
        mock_wb = MagicMock()
        mock_wb.sheetnames = ["S1"]
        mock_wb.__getitem__.return_value = mock_ws
        mock.load_workbook.return_value = mock_wb
        try:
            result = _parse_xlsx(Path("test.xlsx"))
            assert "a |  | c" in result["text"]
        finally:
            _cleanup_modules("openpyxl")


# ── _parse_pptx (sys.modules mock) ────────────────────────


class TestParsePptx:
    """Test _parse_pptx() — mock python-pptx via sys.modules."""

    def test_parse_pptx_basic(self):
        mock = _mock_pptx()
        mock.Presentation = MagicMock()
        shape1 = MagicMock()
        shape1.has_text_frame = True
        para1 = MagicMock()
        para1.text = "  Slide 1 Title  "
        shape1.text_frame.paragraphs = [para1]
        slide = MagicMock()
        slide.shapes = [shape1]
        mock.Presentation.return_value.slides = [slide]
        try:
            result = _parse_pptx(Path("test.pptx"))
            assert result["file_type"] == "pptx"
            assert result["pages"] == 1
            assert "Slide 1" in result["text"]
        finally:
            _cleanup_modules("pptx", "pptx.util")

    def test_parse_pptx_no_text_shapes(self):
        """Slide with no text shapes — no crash, empty output."""
        mock = _mock_pptx()
        mock.Presentation = MagicMock()
        shape = MagicMock()
        shape.has_text_frame = False
        slide = MagicMock()
        slide.shapes = [shape]
        mock.Presentation.return_value.slides = [slide]
        try:
            result = _parse_pptx(Path("empty.pptx"))
            assert result["file_type"] == "pptx"
            assert result["text"] == ""
        finally:
            _cleanup_modules("pptx", "pptx.util")

    def test_parse_pptx_empty_paragraph(self):
        """Empty paragraphs are filtered out."""
        mock = _mock_pptx()
        mock.Presentation = MagicMock()
        shape = MagicMock()
        shape.has_text_frame = True
        para = MagicMock()
        para.text = "  \n  "
        shape.text_frame.paragraphs = [para]
        slide = MagicMock()
        slide.shapes = [shape]
        mock.Presentation.return_value.slides = [slide]
        try:
            result = _parse_pptx(Path("empty.pptx"))
            assert result["text"] == ""
        finally:
            _cleanup_modules("pptx", "pptx.util")
