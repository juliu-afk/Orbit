"""gui_tools.py unit tests — each action branch + error handling.
Coverage sprint B1-7: 0% → >=60%.

WHY sys.modules: mss/pyautogui/PIL not installed in test env.
Module-level imports require mocking before import.
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock heavy GUI deps before module import
sys.modules["mss"] = MagicMock()
sys.modules["pyautogui"] = MagicMock()
sys.modules["pyperclip"] = MagicMock()
sys.modules["PIL"] = MagicMock()
sys.modules["PIL.Image"] = MagicMock()

# Import module under test
from orbit.tools.gui_tools import _capture_screen, gui_agent  # noqa: E402


# ── _capture_screen ───────────────────────────────────────


class TestCaptureScreen:
    """Test _capture_screen() — mss screenshot → PIL Image."""

    def test_success(self):
        """Valid screenshot — returns PIL Image."""
        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        with patch("orbit.tools.gui_tools.Image.frombytes", return_value=mock_img):
            result = _capture_screen()
            assert result is mock_img

    def test_mss_failure(self):
        """mss.mss() throws → RuntimeError with descriptive message."""
        import mss as mss_module
        mss_module.mss.side_effect = OSError("no display")

        with pytest.raises(RuntimeError):
            _capture_screen()


# ── gui_agent action branches ─────────────────────────────


class TestGuiAgent:
    """Test gui_agent() — all 6 action types + error handling."""

    @pytest.mark.asyncio
    async def test_screenshot(self):
        """screenshot action → base64 PNG image."""
        mock_img = MagicMock()
        mock_img.width = 800
        mock_img.height = 600
        with patch("orbit.tools.gui_tools._capture_screen", return_value=mock_img):
            result = await gui_agent("screenshot")
            assert result["action"] == "screenshot"
            assert result["width"] == 800
            assert result["height"] == 600
            assert "image_base64" in result

    @pytest.mark.asyncio
    async def test_click(self):
        """click action → pyautogui.click(x, y)."""
        import pyautogui
        result = await gui_agent("click", x=100, y=200)
        pyautogui.click.assert_called_once_with(100, 200)
        assert result["action"] == "click"

    @pytest.mark.asyncio
    async def test_type_ascii(self):
        """type with ASCII text → pyautogui.typewrite."""
        import pyautogui
        result = await gui_agent("type", text="hello")
        pyautogui.typewrite.assert_called_once_with("hello", interval=0.05)
        assert result["action"] == "type"
        assert result["text_len"] == 5

    @pytest.mark.asyncio
    async def test_type_chinese(self):
        """type with CJK text → clipboard paste via pyperclip."""
        import pyautogui
        with patch("pyperclip.copy") as mock_copy:
            result = await gui_agent("type", text="你好")
            mock_copy.assert_called_once_with("你好")
            pyautogui.hotkey.assert_called_once_with('ctrl', 'v')
            assert result["action"] == "type"

    @pytest.mark.asyncio
    async def test_scroll(self):
        """scroll action → pyautogui.scroll(amount)."""
        import pyautogui
        result = await gui_agent("scroll", amount=3)
        pyautogui.scroll.assert_called_once_with(3)
        assert result["action"] == "scroll"

    @pytest.mark.asyncio
    async def test_move(self):
        """move action → pyautogui.moveTo(x, y)."""
        import pyautogui
        result = await gui_agent("move", x=300, y=400)
        pyautogui.moveTo.assert_called_once_with(300, 400, duration=0.3)
        assert result["action"] == "move"

    @pytest.mark.asyncio
    async def test_analyze(self):
        """analyze action → screenshot + LLM analysis."""
        mock_img = MagicMock()
        mock_img.width = 1024
        mock_img.height = 768

        mock_resp = MagicMock()
        mock_resp.content = "This screen shows a dashboard with charts."
        mock_resp.model = "gpt-4o"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.generate.return_value = mock_resp
        mock_client.__aexit__ = AsyncMock()

        with patch("orbit.tools.gui_tools._capture_screen", return_value=mock_img):
            with patch("orbit.gateway.client.LLMClient", return_value=mock_client):
                result = await gui_agent("analyze", question="What is on screen?")
                assert result["action"] == "analyze"
                assert "dashboard" in result["analysis"]
                assert result["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_unsupported_action(self):
        """Unknown action → error dict (exception caught internally)."""
        result = await gui_agent("unknown_action")
        assert result["action"] == "unknown_action"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_action_exception_handled(self):
        """Exception during action → error dict, not raised."""
        import pyautogui
        pyautogui.click.side_effect = RuntimeError("display disconnected")

        result = await gui_agent("click", x=0, y=0)
        assert result["action"] == "click"
        assert "error" in result
