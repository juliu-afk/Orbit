"""ocr_tools.py unit tests — helpers + async ocr_document with mocked httpx.
Coverage sprint B1-6: 0% → >=60%.

WHY mock at module level: global imports (httpx, settings) + _register() side effect.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock heavy deps before module import
sys.modules["httpx"] = MagicMock()

# Import module under test
from orbit.tools.ocr_tools import (  # noqa: E402
    _estimate_pages,
    _extract_error,
    _mime_type,
    ocr_document,
)


def _cleanup():
    sys.modules.pop("httpx", None)


# ── _mime_type ────────────────────────────────────────────


class TestMimeType:
    """Test _mime_type() — file extension → MIME type mapping."""

    def test_jpg(self):
        assert _mime_type(".jpg") == "image/jpeg"
        assert _mime_type(".jpeg") == "image/jpeg"

    def test_png(self):
        assert _mime_type(".png") == "image/png"

    def test_webp(self):
        assert _mime_type(".webp") == "image/webp"

    def test_bmp(self):
        assert _mime_type(".bmp") == "image/bmp"

    def test_pdf(self):
        assert _mime_type(".pdf") == "application/pdf"

    def test_unknown_extension(self):
        """Unknown extension → octet-stream fallback."""
        assert _mime_type(".xyz") == "application/octet-stream"
        assert _mime_type("") == "application/octet-stream"


# ── _extract_error ────────────────────────────────────────


class TestExtractError:
    """Test _extract_error() — extract error message from httpx Response."""

    def test_json_error_message(self):
        """Response with JSON error.message."""
        resp = MagicMock()
        resp.json.return_value = {"error": {"message": "API key invalid"}}
        assert _extract_error(resp) == "API key invalid"

    def test_json_no_error_key(self):
        """Response JSON without 'error' key → raw text."""
        resp = MagicMock()
        resp.json.return_value = {"other": "data"}
        resp.text = "raw response text"
        assert _extract_error(resp) == "raw response text"

    def test_not_json(self):
        """Non-JSON response → text[:200]."""
        resp = MagicMock()
        resp.json.side_effect = ValueError("not json")
        resp.text = "plain error text longer than 200 chars" * 20
        assert _extract_error(resp) == resp.text[:200]

    def test_long_error_truncated(self):
        """Long text truncated to 200 chars."""
        resp = MagicMock()
        long_text = "x" * 300
        resp.json.return_value = {}
        resp.text = long_text
        assert len(_extract_error(resp)) == 200


# ── _estimate_pages ───────────────────────────────────────


class TestEstimatePages:
    """Test _estimate_pages() — API pages field or default 1."""

    def test_pages_present(self):
        assert _estimate_pages({"pages": 5}) == 5

    def test_pages_absent(self):
        """No 'pages' key → default 1."""
        assert _estimate_pages({}) == 1

    def test_pages_zero(self):
        """pages=0 → returned as-is (caller handles)."""
        assert _estimate_pages({"pages": 0}) == 0


# ── ocr_document (async, mocked httpx) ────────────────────


class TestOcrDocument:
    """Test ocr_document() — async with mocked httpx + settings."""

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            await ocr_document("/nonexistent/img.jpg")

    @pytest.mark.asyncio
    async def test_unsupported_extension(self):
        """Unsupported extension → ValueError."""
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises(ValueError):
                await ocr_document("/fake/file.gif")

    @pytest.mark.asyncio
    async def test_file_too_large(self):
        """File > 50MB → ValueError."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 60 * 1024 * 1024  # 60MB
                with patch("builtins.open"):
                    with patch("base64.b64encode", return_value=b"fake"):
                        with pytest.raises(ValueError):
                            await ocr_document("/fake/large.pdf")

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """No DEEPSEEK_API_KEY → RuntimeError."""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 1024
                with patch("builtins.open"):
                    with patch("base64.b64encode", return_value=b"fake"):
                        with patch("orbit.tools.ocr_tools.settings") as mock_settings:
                            mock_settings.DEEPSEEK_API_KEY = ""
                            with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
                                await ocr_document("/fake/file.png")

    @pytest.mark.asyncio
    async def test_successful_ocr(self):
        """Happy path — valid file, valid response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "## Extracted Text\n\nHello world"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post.return_value = mock_resp
        mock_client.__aexit__ = AsyncMock()

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 1024
                with patch("builtins.open"):
                    with patch("base64.b64encode", return_value=b"fake"):
                        with patch("orbit.tools.ocr_tools.settings") as mock_settings:
                            mock_settings.DEEPSEEK_API_KEY = "sk-test"
                            with patch("httpx.AsyncClient", return_value=mock_client):
                                result = await ocr_document("/fake/file.png")
                                assert result["text"] == "## Extracted Text\n\nHello world"
                                assert result["tokens"] == 150
                                assert result["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_api_error(self):
        """Non-200 response → RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "Unauthorized"}}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post.return_value = mock_resp
        mock_client.__aexit__ = AsyncMock()

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 1024
                with patch("builtins.open"):
                    with patch("base64.b64encode", return_value=b"fake"):
                        with patch("orbit.tools.ocr_tools.settings") as mock_settings:
                            mock_settings.DEEPSEEK_API_KEY = "sk-test"
                            with patch("httpx.AsyncClient", return_value=mock_client):
                                with pytest.raises(RuntimeError, match="OCR"):
                                    await ocr_document("/fake/file.png")

    @pytest.mark.asyncio
    async def test_language_param(self):
        """language param modifies prompt."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "text"}}],
            "usage": {"total_tokens": 10},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post.return_value = mock_resp
        mock_client.__aexit__ = AsyncMock()

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 500
                with patch("builtins.open"):
                    with patch("base64.b64encode", return_value=b"fake"):
                        with patch("orbit.tools.ocr_tools.settings") as mock_settings:
                            mock_settings.DEEPSEEK_API_KEY = "sk-test"
                            with patch("httpx.AsyncClient", return_value=mock_client):
                                result = await ocr_document("/fake/file.png", language="zh")
                                assert result["text"] == "text"
