"""office_tools.py unit tests — path whitelist + 3 Office output types + error paths.
Coverage sprint B1-2: 0% → >=60%.

WHY monkeypatch _ALLOWED_DIRS: relative paths (./output, ./data, ./exports)
don't resolve to tmp_path on any OS. Test with tmp_path added to whitelist.
WHY touch file before create: sys.modules mock means no real file written,
so path.stat().st_size fails without the file existing.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orbit.tools import office_tools


# ── Helpers ───────────────────────────────────────────────


def _mock_openpyxl():
    mock = MagicMock()
    sys.modules["openpyxl"] = mock
    return mock


def _mock_docx():
    mock = MagicMock()
    sys.modules["docx"] = mock
    return mock


def _mock_pptx():
    mock = MagicMock()
    sys.modules["pptx"] = mock
    sys.modules["pptx.util"] = MagicMock()
    return mock


def _cleanup(*names):
    for name in names:
        sys.modules.pop(name, None)


@pytest.fixture
def allowed_dirs(tmp_path, monkeypatch):
    """Add tmp_path to _ALLOWED_DIRS so validate passes."""
    monkeypatch.setattr(office_tools, "_ALLOWED_DIRS", (str(tmp_path), "/tmp"))


# ── _validate_output_path ─────────────────────────────────


class TestValidateOutputPath:
    """Test output path whitelist validation."""

    def test_allowed_path(self, allowed_dirs, tmp_path):
        """Path under allowed dir → passes."""
        f = tmp_path / "output.xlsx"
        f.write_text("")
        result = office_tools._validate_output_path(str(f))
        assert result == f.resolve()

    def test_disallowed_path(self):
        """Path not in whitelist → ValueError."""
        with pytest.raises(ValueError):
            office_tools._validate_output_path("/etc/passwd")

    def test_nonexistent_path_still_validated(self, allowed_dirs, tmp_path):
        """Validation checks directory, not file existence."""
        f = tmp_path / "subdir" / "report.xlsx"
        f.parent.mkdir(parents=True, exist_ok=True)
        # file doesn't exist but path is under allowed dir
        result = office_tools._validate_output_path(str(f))
        assert result == f.resolve()


# ── office_create async entry ─────────────────────────────


class TestOfficeCreate:
    """Test office_create() async entry — routing + path validation."""

    @pytest.mark.asyncio
    async def test_disallowed_path(self):
        """Disallowed path → ValueError before routing."""
        with pytest.raises(ValueError):
            await office_tools.office_create("xlsx", "/etc/output.xlsx", {"rows": [["a"]]})

    @pytest.mark.asyncio
    async def test_xlsx_route(self, allowed_dirs, tmp_path):
        """Valid xlsx path → routes to _create_xlsx."""
        f = tmp_path / "result.xlsx"
        f.touch()
        with patch.object(office_tools, "_create_xlsx", return_value={"path": str(f), "file_type": "xlsx", "size_bytes": 100}) as mock_fn:
            result = await office_tools.office_create("xlsx", str(f), {"rows": [["h1"]]})
            mock_fn.assert_called_once()
            assert result["file_type"] == "xlsx"

    @pytest.mark.asyncio
    async def test_docx_route(self, allowed_dirs, tmp_path):
        """Valid docx path → routes to _create_docx."""
        f = tmp_path / "result.docx"
        f.touch()
        with patch.object(office_tools, "_create_docx", return_value={"path": str(f), "file_type": "docx", "size_bytes": 50}) as mock_fn:
            result = await office_tools.office_create("docx", str(f), {"paragraphs": ["Hello"]})
            mock_fn.assert_called_once()
            assert result["file_type"] == "docx"

    @pytest.mark.asyncio
    async def test_pptx_route(self, allowed_dirs, tmp_path):
        """Valid pptx path → routes to _create_pptx."""
        f = tmp_path / "result.pptx"
        f.touch()
        with patch.object(office_tools, "_create_pptx", return_value={"path": str(f), "file_type": "pptx", "size_bytes": 300}) as mock_fn:
            result = await office_tools.office_create("pptx", str(f), {"slides": [{"title": "T1"}]})
            mock_fn.assert_called_once()
            assert result["file_type"] == "pptx"

    @pytest.mark.asyncio
    async def test_unsupported_type_routes_to_error(self, allowed_dirs, tmp_path):
        """Unsupported type → ValueError after path validation."""
        f = tmp_path / "out.pdf"
        f.touch()
        with pytest.raises(ValueError):
            await office_tools.office_create("pdf", str(f), {"rows": [["a"]]})


# ── _create_xlsx ──────────────────────────────────────────


class TestCreateXlsx:
    """Test _create_xlsx() — mock openpyxl via sys.modules."""

    def test_create_with_list_of_rows(self, tmp_path):
        mock = _mock_openpyxl()
        path = tmp_path / "test.xlsx"
        path.touch()  # WHY: mock openpyxl won't actually create file, stat() needs it
        try:
            result = office_tools._create_xlsx(path, [["Name", "Age"], ["Alice", 30]])
            assert result["file_type"] == "xlsx"
            assert result["size_bytes"] == 0  # touched empty file
        finally:
            _cleanup("openpyxl")

    def test_create_with_dict_rows(self, tmp_path):
        mock = _mock_openpyxl()
        path = tmp_path / "test2.xlsx"
        path.touch()
        try:
            result = office_tools._create_xlsx(path, {"rows": [["a", 1]]})
            assert result["file_type"] == "xlsx"
        finally:
            _cleanup("openpyxl")

    def test_create_single_column(self, tmp_path):
        mock = _mock_openpyxl()
        path = tmp_path / "single.xlsx"
        path.touch()
        try:
            result = office_tools._create_xlsx(path, ["row1", "row2"])
            assert result["file_type"] == "xlsx"
        finally:
            _cleanup("openpyxl")


# ── _create_docx ──────────────────────────────────────────


class TestCreateDocx:
    """Test _create_docx() — mock python-docx via sys.modules."""

    def test_create_with_paragraphs(self, tmp_path):
        mock = _mock_docx()
        path = tmp_path / "test.docx"
        path.touch()
        try:
            result = office_tools._create_docx(path, {"paragraphs": ["p1", "p2"]})
            assert result["file_type"] == "docx"
        finally:
            _cleanup("docx")

    def test_create_with_title(self, tmp_path):
        mock = _mock_docx()
        path = tmp_path / "titled.docx"
        path.touch()
        try:
            result = office_tools._create_docx(path, {"title": "Report", "paragraphs": ["content"]})
            assert result["file_type"] == "docx"
        finally:
            _cleanup("docx")

    def test_create_list_format(self, tmp_path):
        mock = _mock_docx()
        path = tmp_path / "list.docx"
        path.touch()
        try:
            result = office_tools._create_docx(path, ["p1", "p2"])
            assert result["file_type"] == "docx"
        finally:
            _cleanup("docx")


# ── _create_pptx ──────────────────────────────────────────


class TestCreatePptx:
    """Test _create_pptx() — mock python-pptx via sys.modules."""

    def test_create_with_slides(self, tmp_path):
        mock = _mock_pptx()
        path = tmp_path / "test.pptx"
        path.touch()
        try:
            content = {"slides": [{"title": "Cover", "bullets": ["p1", "p2"]}]}
            result = office_tools._create_pptx(path, content)
            assert result["file_type"] == "pptx"
        finally:
            _cleanup("pptx", "pptx.util")

    def test_create_slide_no_bullets(self, tmp_path):
        mock = _mock_pptx()
        path = tmp_path / "nobullet.pptx"
        path.touch()
        try:
            content = {"slides": [{"title": "Title Only"}]}
            result = office_tools._create_pptx(path, content)
            assert result["file_type"] == "pptx"
        finally:
            _cleanup("pptx", "pptx.util")

    def test_create_list_format(self, tmp_path):
        mock = _mock_pptx()
        path = tmp_path / "list.pptx"
        path.touch()
        try:
            content = [{"title": "T1", "bullets": ["b1"]}]
            result = office_tools._create_pptx(path, content)
            assert result["file_type"] == "pptx"
        finally:
            _cleanup("pptx", "pptx.util")
