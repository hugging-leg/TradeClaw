"""
Tests for Code Execution Sandbox (OpenSandbox-only mode)

Tests the sandbox including:
- OpenSandbox backend singleton, availability checks, caching
- Tool creation (execute_python + execute_terminal)
- Both tools return unavailable error when OpenSandbox is not configured
- Timeout clamping
- reset_availability
"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from agent_trader.agents.tools.code_sandbox_tools import (
    create_code_sandbox_tools,
    OpenSandboxBackend,
    _OPENSANDBOX_UNAVAILABLE_MSG,
)


class TestOpenSandboxBackend:
    """Test OpenSandbox backend detection and lifecycle"""

    def setup_method(self):
        """Reset singleton between tests."""
        OpenSandboxBackend._instance = None

    def test_singleton(self):
        """Test that OpenSandboxBackend is a singleton"""
        a = OpenSandboxBackend.get_instance()
        b = OpenSandboxBackend.get_instance()
        assert a is b

    def test_initial_state(self):
        """Test initial backend state"""
        backend = OpenSandboxBackend()
        assert backend._sandbox is None
        assert backend._initialized is False
        assert backend._available is None
        assert backend._python_bin_dir == ""

    @pytest.mark.asyncio
    async def test_unavailable_when_no_server_url(self):
        """Test that OpenSandbox is unavailable when server URL is empty"""
        backend = OpenSandboxBackend()
        backend._available = None
        with patch("config.settings") as mock_settings:
            mock_settings.opensandbox_server_url = ""
            result = await backend.is_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_unavailable_when_no_sdk(self):
        """Test that OpenSandbox is unavailable when SDK is not installed"""
        backend = OpenSandboxBackend()
        backend._available = None
        with patch("config.settings") as mock_settings:
            mock_settings.opensandbox_server_url = "http://localhost:9999"
            # Simulate SDK not installed by making the import fail
            import sys
            original = sys.modules.get("opensandbox")
            sys.modules["opensandbox"] = None  # type: ignore[assignment]
            try:
                result = await backend.is_available()
                assert result is False
            finally:
                if original is not None:
                    sys.modules["opensandbox"] = original
                else:
                    sys.modules.pop("opensandbox", None)

    @pytest.mark.asyncio
    async def test_caches_availability_result(self):
        """Test that availability result is cached after first check"""
        backend = OpenSandboxBackend()
        backend._available = False
        result = await backend.is_available()
        assert result is False

        backend._available = True
        result = await backend.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_reset_availability(self):
        """Test that reset_availability clears the cache"""
        backend = OpenSandboxBackend()
        backend._available = True
        backend.reset_availability()
        assert backend._available is None

    @pytest.mark.asyncio
    async def test_execute_raises_when_not_initialized(self):
        """Test that execute raises RuntimeError when sandbox can't init"""
        backend = OpenSandboxBackend()
        backend._available = True  # pretend available
        # _ensure_initialized will fail because no real server
        with patch.object(backend, "_ensure_initialized", return_value=False):
            with pytest.raises(RuntimeError, match="not available"):
                await backend.execute("print(1)")

    @pytest.mark.asyncio
    async def test_run_command_raises_when_not_initialized(self):
        """Test that run_command raises RuntimeError when sandbox can't init"""
        backend = OpenSandboxBackend()
        backend._available = True
        with patch.object(backend, "_ensure_initialized", return_value=False):
            with pytest.raises(RuntimeError, match="not available"):
                await backend.run_command("ls")

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test that shutdown cleans up state"""
        backend = OpenSandboxBackend()
        backend._initialized = True
        backend._sandbox = MagicMock()
        backend._sandbox.kill = AsyncMock()
        backend._sandbox.close = AsyncMock()

        await backend.shutdown()

        assert backend._initialized is False
        assert backend._sandbox is None


class TestCodeSandboxTools:
    """Test the LangChain tool creation"""

    @pytest.fixture
    def mock_workflow(self):
        """Create a mock workflow with message_manager"""
        wf = MagicMock()
        wf.message_manager = MagicMock()
        wf.message_manager.send_message = AsyncMock()
        wf.message_manager.send_error = AsyncMock()
        return wf

    def test_create_tools(self, mock_workflow):
        """Test that tools are created"""
        tools = create_code_sandbox_tools(mock_workflow)
        assert len(tools) == 2
        names = {t[0].name for t in tools}
        assert names == {"execute_python", "execute_terminal"}
        for _, category in tools:
            assert category == "sandbox"

    @pytest.mark.asyncio
    async def test_execute_python_unavailable(self, mock_workflow):
        """Test execute_python returns error when OpenSandbox is unavailable"""
        # Reset singleton to ensure clean state
        OpenSandboxBackend._instance = None
        tools = create_code_sandbox_tools(mock_workflow)
        tool_obj, _ = tools[0]  # execute_python

        # Patch the backend to be unavailable
        with patch.object(OpenSandboxBackend, "is_available", return_value=False):
            result_str = await tool_obj.ainvoke({"code": "x = 42", "timeout_seconds": 10})
            result = json.loads(result_str)
            assert result["success"] is False
            assert "not configured" in result["error"].lower() or "not available" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_terminal_unavailable(self, mock_workflow):
        """Test execute_terminal returns error when OpenSandbox is unavailable"""
        OpenSandboxBackend._instance = None
        tools = create_code_sandbox_tools(mock_workflow)
        tool_obj, _ = tools[1]  # execute_terminal

        with patch.object(OpenSandboxBackend, "is_available", return_value=False):
            result_str = await tool_obj.ainvoke({"command": "ls", "timeout_seconds": 10})
            result = json.loads(result_str)
            assert result["success"] is False
            assert "not configured" in result["error"].lower() or "not available" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_python_success(self, mock_workflow):
        """Test execute_python dispatches to OpenSandbox when available"""
        OpenSandboxBackend._instance = None
        tools = create_code_sandbox_tools(mock_workflow)
        tool_obj, _ = tools[0]

        mock_result = {
            "success": True,
            "output": "42",
            "stderr": "",
            "variables": {"x": 42},
            "backend": "opensandbox",
        }

        with patch.object(OpenSandboxBackend, "is_available", return_value=True), \
             patch.object(OpenSandboxBackend, "execute", return_value=mock_result):
            result_str = await tool_obj.ainvoke({"code": "x = 42\nprint(x)", "timeout_seconds": 10})
            result = json.loads(result_str)
            assert result["success"] is True
            assert result["backend"] == "opensandbox"
            assert "42" in result["output"]

    @pytest.mark.asyncio
    async def test_execute_terminal_success(self, mock_workflow):
        """Test execute_terminal dispatches to OpenSandbox when available"""
        OpenSandboxBackend._instance = None
        tools = create_code_sandbox_tools(mock_workflow)
        tool_obj, _ = tools[1]

        mock_result = {
            "success": True,
            "exit_code": 0,
            "stdout": "file1.txt\nfile2.txt",
            "stderr": "",
            "backend": "opensandbox",
        }

        with patch.object(OpenSandboxBackend, "is_available", return_value=True), \
             patch.object(OpenSandboxBackend, "run_command", return_value=mock_result):
            result_str = await tool_obj.ainvoke({"command": "ls", "timeout_seconds": 10})
            result = json.loads(result_str)
            assert result["success"] is True
            assert result["backend"] == "opensandbox"
            assert "file1.txt" in result["stdout"]

    @pytest.mark.asyncio
    async def test_timeout_clamped_python(self, mock_workflow):
        """Test that execute_python timeout is clamped to [1, 120]"""
        OpenSandboxBackend._instance = None
        tools = create_code_sandbox_tools(mock_workflow)
        tool_obj, _ = tools[0]

        mock_result = {"success": True, "output": "", "stderr": "", "variables": {}, "backend": "opensandbox"}

        with patch.object(OpenSandboxBackend, "is_available", return_value=True), \
             patch.object(OpenSandboxBackend, "execute", return_value=mock_result) as mock_exec:
            # timeout=0 should be clamped to 1
            await tool_obj.ainvoke({"code": "x = 1", "timeout_seconds": 0})
            call_kwargs = mock_exec.call_args
            assert call_kwargs[1]["timeout_seconds"] == 1 or call_kwargs.kwargs.get("timeout_seconds") == 1

            # timeout=999 should be clamped to 120
            await tool_obj.ainvoke({"code": "x = 1", "timeout_seconds": 999})
            call_kwargs = mock_exec.call_args
            assert call_kwargs[1]["timeout_seconds"] == 120 or call_kwargs.kwargs.get("timeout_seconds") == 120

    @pytest.mark.asyncio
    async def test_timeout_clamped_terminal(self, mock_workflow):
        """Test that execute_terminal timeout is clamped to [1, 300]"""
        OpenSandboxBackend._instance = None
        tools = create_code_sandbox_tools(mock_workflow)
        tool_obj, _ = tools[1]

        mock_result = {"success": True, "exit_code": 0, "stdout": "", "stderr": "", "backend": "opensandbox"}

        with patch.object(OpenSandboxBackend, "is_available", return_value=True), \
             patch.object(OpenSandboxBackend, "run_command", return_value=mock_result) as mock_cmd:
            # timeout=0 should be clamped to 1
            await tool_obj.ainvoke({"command": "echo hi", "timeout_seconds": 0})
            call_kwargs = mock_cmd.call_args
            assert call_kwargs[1]["timeout_seconds"] == 1 or call_kwargs.kwargs.get("timeout_seconds") == 1

            # timeout=999 should be clamped to 300
            await tool_obj.ainvoke({"command": "echo hi", "timeout_seconds": 999})
            call_kwargs = mock_cmd.call_args
            assert call_kwargs[1]["timeout_seconds"] == 300 or call_kwargs.kwargs.get("timeout_seconds") == 300

    @pytest.mark.asyncio
    async def test_execute_python_exception_handling(self, mock_workflow):
        """Test that exceptions in execute_python are caught and returned as JSON"""
        OpenSandboxBackend._instance = None
        tools = create_code_sandbox_tools(mock_workflow)
        tool_obj, _ = tools[0]

        with patch.object(OpenSandboxBackend, "is_available", return_value=True), \
             patch.object(OpenSandboxBackend, "execute", side_effect=Exception("boom")):
            result_str = await tool_obj.ainvoke({"code": "x = 1", "timeout_seconds": 10})
            result = json.loads(result_str)
            assert result["success"] is False
            assert "boom" in result["error"]


class TestResolveExecdEndpoint:
    """Test SDK-based endpoint resolution (replaces docker port CLI)"""

    def setup_method(self):
        OpenSandboxBackend._instance = None

    @pytest.mark.asyncio
    async def test_resolve_endpoint_success(self):
        """get_sandbox_endpoint returns a valid direct endpoint string"""
        backend = OpenSandboxBackend()
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox-id"
        mock_ep = MagicMock()
        mock_ep.endpoint = "172.17.0.5:44772"
        mock_sandbox._sandbox_service.get_sandbox_endpoint = AsyncMock(return_value=mock_ep)

        result = await backend._resolve_execd_endpoint(mock_sandbox)
        assert result == "172.17.0.5:44772"
        mock_sandbox._sandbox_service.get_sandbox_endpoint.assert_awaited_once_with(
            "test-sandbox-id", 44772, use_server_proxy=False
        )

    @pytest.mark.asyncio
    async def test_resolve_endpoint_failure(self):
        """get_sandbox_endpoint raises → returns None"""
        backend = OpenSandboxBackend()
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox-id"
        mock_sandbox._sandbox_service.get_sandbox_endpoint = AsyncMock(
            side_effect=Exception("not found")
        )

        result = await backend._resolve_execd_endpoint(mock_sandbox)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_endpoint_empty(self):
        """get_sandbox_endpoint returns empty endpoint → returns None"""
        backend = OpenSandboxBackend()
        mock_sandbox = MagicMock()
        mock_sandbox.id = "test-sandbox-id"
        mock_ep = MagicMock()
        mock_ep.endpoint = ""
        mock_sandbox._sandbox_service.get_sandbox_endpoint = AsyncMock(return_value=mock_ep)

        result = await backend._resolve_execd_endpoint(mock_sandbox)
        assert result is None


class TestUnavailableMessage:
    """Test the unavailable message constant"""

    def test_message_content(self):
        """Test that the unavailable message is informative"""
        assert "opensandbox_server_url" in _OPENSANDBOX_UNAVAILABLE_MSG.lower() or \
               "opensandbox" in _OPENSANDBOX_UNAVAILABLE_MSG.lower()
        assert "no local fallback" in _OPENSANDBOX_UNAVAILABLE_MSG.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
