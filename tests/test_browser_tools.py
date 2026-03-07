"""
Tests for Browser Automation Tools (Playwright MCP backend)

Tests the Playwright MCP client including:
- Singleton pattern
- Availability detection (URL configured / not configured)
- Tool creation (5 tools registered)
- Tool behavior when MCP server is unavailable
- Tool behavior when MCP server is available (mocked)
- reset_availability
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_trader.agents.tools.browser_tools import (
    PlaywrightMCPClient,
    create_browser_tools,
    _extract_text,
)


class TestPlaywrightMCPClient:
    """Test PlaywrightMCPClient singleton and availability"""

    def setup_method(self):
        """Reset singleton between tests."""
        PlaywrightMCPClient._instance = None

    def test_singleton(self):
        a = PlaywrightMCPClient.get_instance()
        b = PlaywrightMCPClient.get_instance()
        assert a is b

    def test_initial_state(self):
        client = PlaywrightMCPClient()
        assert client._base_url == ""
        assert client._session is None
        assert client._available is None
        assert client._connected is False
        assert client._messages_path is None

    @pytest.mark.asyncio
    async def test_unavailable_when_no_url(self):
        """Test that client is unavailable when URL is empty"""
        client = PlaywrightMCPClient()
        with patch("config.settings") as mock_settings:
            mock_settings.playwright_mcp_url = ""
            result = await client.is_available()
            assert result is False
            assert client._available is False

    @pytest.mark.asyncio
    async def test_available_caching(self):
        """Test that availability result is cached"""
        client = PlaywrightMCPClient()
        client._available = True
        result = await client.is_available()
        assert result is True

    def test_reset_availability(self):
        """Test that reset clears cached state"""
        client = PlaywrightMCPClient()
        client._available = True
        client._base_url = "http://test:8931"
        client.reset_availability()
        assert client._available is None
        assert client._base_url == ""

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test shutdown clears state"""
        client = PlaywrightMCPClient()
        client._available = True
        client._connected = True
        mock_session = AsyncMock()
        mock_session.closed = False
        client._session = mock_session
        await client.shutdown()
        assert client._session is None
        assert client._available is None
        assert client._connected is False
        mock_session.close.assert_awaited_once()


class TestExtractText:
    """Test the _extract_text helper"""

    def test_text_content(self):
        result = {
            "content": [
                {"type": "text", "text": "Hello world"},
                {"type": "text", "text": "Second line"},
            ]
        }
        assert _extract_text(result) == "Hello world\nSecond line"

    def test_image_content(self):
        result = {
            "content": [
                {"type": "image", "mimeType": "image/png"},
            ]
        }
        assert "[image:" in _extract_text(result)

    def test_error_content(self):
        result = {"error": "Something went wrong"}
        assert "Something went wrong" in _extract_text(result)

    def test_error_dict(self):
        result = {"error": {"code": -1, "message": "fail"}}
        text = _extract_text(result)
        assert "fail" in text

    def test_empty_content(self):
        result = {"content": []}
        text = _extract_text(result)
        assert text  # Should return something (JSON fallback)

    def test_string_content_items(self):
        result = {"content": ["plain text"]}
        assert "plain text" in _extract_text(result)


class TestCreateBrowserTools:
    """Test tool creation and basic behavior"""

    def setup_method(self):
        PlaywrightMCPClient._instance = None

    def test_create_tools_returns_5(self):
        """Test that create_browser_tools returns 5 tools"""
        mock_wf = MagicMock()
        tools = create_browser_tools(mock_wf)
        assert len(tools) == 5
        names = {t[0].name for t in tools}
        assert names == {
            "browser_navigate",
            "browser_snapshot",
            "browser_click",
            "browser_type_text",
            "browser_screenshot",
        }
        # All should be in "browser" category
        for _, category in tools:
            assert category == "browser"

    @pytest.mark.asyncio
    async def test_navigate_unavailable(self):
        """Test that browser_navigate returns error when MCP is not available"""
        mock_wf = MagicMock()
        mock_wf.message_manager = MagicMock()
        tools = create_browser_tools(mock_wf)
        navigate_tool = next(t for t, _ in tools if t.name == "browser_navigate")

        with patch.object(PlaywrightMCPClient, "is_available", new_callable=AsyncMock, return_value=False):
            result_str = await navigate_tool.ainvoke({"url": "https://example.com"})
            result = json.loads(result_str)
            assert result["success"] is False
            assert "not configured" in result["error"].lower() or "not available" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_navigate_success(self):
        """Test browser_navigate with mocked MCP server"""
        mock_wf = MagicMock()
        mock_wf.message_manager = MagicMock()
        mock_wf.message_manager.send_message = AsyncMock()

        tools = create_browser_tools(mock_wf)
        navigate_tool = next(t for t, _ in tools if t.name == "browser_navigate")

        mock_result = {
            "content": [
                {"type": "text", "text": "- heading 'Example Domain'\n- paragraph: 'Illustrative examples.'"},
            ]
        }

        with patch.object(PlaywrightMCPClient, "is_available", new_callable=AsyncMock, return_value=True), \
             patch.object(PlaywrightMCPClient, "call_tool", new_callable=AsyncMock, return_value=mock_result):

            result_str = await navigate_tool.ainvoke({"url": "https://example.com"})
            assert "Example Domain" in result_str

    @pytest.mark.asyncio
    async def test_snapshot_unavailable(self):
        """Test that browser_snapshot returns error when MCP is not available"""
        mock_wf = MagicMock()
        tools = create_browser_tools(mock_wf)
        snapshot_tool = next(t for t, _ in tools if t.name == "browser_snapshot")

        with patch.object(PlaywrightMCPClient, "is_available", new_callable=AsyncMock, return_value=False):
            result_str = await snapshot_tool.ainvoke({})
            result = json.loads(result_str)
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_click_unavailable(self):
        """Test that browser_click returns error when MCP is not available"""
        mock_wf = MagicMock()
        tools = create_browser_tools(mock_wf)
        click_tool = next(t for t, _ in tools if t.name == "browser_click")

        with patch.object(PlaywrightMCPClient, "is_available", new_callable=AsyncMock, return_value=False):
            result_str = await click_tool.ainvoke({"ref": "s1e1"})
            result = json.loads(result_str)
            assert result["success"] is False
