"""
Browser Automation Agent Tools — Playwright MCP

Provides browser automation capabilities by connecting to a Playwright MCP
Server (https://github.com/microsoft/playwright-mcp) running as a sidecar
Docker container.  The MCP server manages a headless Chromium instance and
exposes 20+ browser tools over an HTTP/SSE transport.

This module bridges a subset of those MCP tools into LangChain tools so
the trading Agent can:
- Navigate to web pages (including JS-rendered SPAs)
- Take accessibility snapshots (structured, LLM-friendly)
- Take screenshots
- Click / type / interact with page elements
- Manage browser tabs

Architecture:
- PlaywrightMCPClient: Async HTTP client that connects to the Playwright MCP
  server via its **legacy SSE transport** (GET /sse + POST /sse?sessionId=…).
  This is more reliable than the Streamable HTTP transport for long-running
  browser operations.
- Five LangChain tools exposed to the Agent:
  1. browser_navigate  — go to a URL
  2. browser_snapshot  — get an accessibility snapshot of the page
  3. browser_click     — click an element by ref
  4. browser_type_text — type text into an element
  5. browser_screenshot— take a screenshot

No local Playwright installation is required.  The browser runs entirely
inside the ``mcr.microsoft.com/playwright/mcp`` Docker container.

Configuration:
- ``PLAYWRIGHT_MCP_URL`` env var or ``playwright_mcp_url`` in Settings
  (e.g. ``http://localhost:8931`` for dev, ``http://playwright-mcp:8931``
  in docker-compose).
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from langchain.tools import tool

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Playwright MCP Client (Legacy SSE Transport)
# ------------------------------------------------------------------

class PlaywrightMCPClient:
    """
    Async HTTP client for the Playwright MCP Server using the **legacy SSE
    transport** (``/sse`` endpoint).

    Protocol:
    1. ``GET /sse`` → establishes a persistent SSE stream.  The first event
       is ``event: endpoint`` with ``data: /sse?sessionId=<id>``.
    2. ``POST /sse?sessionId=<id>`` with JSON-RPC body → sends a request.
    3. The response comes back on the SSE stream as ``event: message``.

    This approach keeps a single persistent connection, so the MCP server
    maintains browser state across tool calls.
    """

    _instance: Optional["PlaywrightMCPClient"] = None

    def __init__(self) -> None:
        self._base_url: str = ""
        self._session: Optional[aiohttp.ClientSession] = None
        self._available: Optional[bool] = None
        self._lock = asyncio.Lock()
        self._request_id = 0

        # SSE connection state
        self._sse_response: Optional[aiohttp.ClientResponse] = None
        self._messages_path: Optional[str] = None  # e.g. "/sse?sessionId=xxx"
        self._pending: Dict[int, asyncio.Future] = {}  # id → Future[result]
        self._reader_task: Optional[asyncio.Task] = None
        self._connected = False

    @classmethod
    def get_instance(cls) -> "PlaywrightMCPClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_base_url(self) -> str:
        """Resolve the Playwright MCP server URL from settings / env."""
        if self._base_url:
            return self._base_url
        try:
            from config import settings
            url = getattr(settings, "playwright_mcp_url", "") or ""
            if url:
                self._base_url = url.rstrip("/")
                return self._base_url
        except Exception:
            pass
        import os
        url = os.environ.get("PLAYWRIGHT_MCP_URL", "")
        if url:
            self._base_url = url.rstrip("/")
        return self._base_url

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Use a large read_bufsize so that SSE data lines carrying big
            # payloads (accessibility snapshots, base64 screenshots) don't
            # trigger aiohttp's "Chunk too big" ValueError.  Default is 64 KB;
            # we raise it to 16 MB.
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
                read_bufsize=16 * 1024 * 1024,  # 16 MB
            )
        return self._session

    async def is_available(self) -> bool:
        """Check if the Playwright MCP server is reachable."""
        if self._available is not None:
            return self._available

        base = self._get_base_url()
        if not base:
            self._available = False
            logger.info("Playwright MCP URL not configured — browser tools disabled")
            return False

        try:
            session = await self._ensure_session()
            # Quick connectivity check: GET /sse should return 200 with SSE stream
            async with session.get(
                f"{base}/sse",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    self._available = True
                    logger.info("Playwright MCP server reachable at %s", base)
                    return True
                else:
                    self._available = False
                    logger.info("Playwright MCP /sse returned %d", resp.status)
                    return False
        except Exception as e:
            self._available = False
            logger.info("Playwright MCP server not reachable at %s: %s", base, e)
            return False

    def reset_availability(self) -> None:
        """Clear cached availability (call after settings change)."""
        self._available = None
        self._base_url = ""

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    # ------------------------------------------------------------------
    # SSE Connection Management
    # ------------------------------------------------------------------

    async def _connect_sse(self) -> bool:
        """
        Establish the SSE connection and start the background reader.

        Returns True if the connection was established successfully.
        """
        if self._connected and self._reader_task and not self._reader_task.done():
            return True

        async with self._lock:
            if self._connected and self._reader_task and not self._reader_task.done():
                return True

            base = self._get_base_url()
            if not base:
                return False

            try:
                session = await self._ensure_session()

                # Open SSE stream
                self._sse_response = await session.get(
                    f"{base}/sse",
                    timeout=aiohttp.ClientTimeout(
                        total=None,  # No total timeout for SSE stream
                        sock_read=None,
                    ),
                )

                if self._sse_response.status != 200:
                    logger.warning("Playwright MCP /sse returned %d", self._sse_response.status)
                    self._sse_response.close()
                    self._sse_response = None
                    return False

                # Read the first event to get the messages endpoint
                endpoint = await self._read_endpoint_event()
                if not endpoint:
                    logger.warning("Failed to read endpoint from Playwright MCP /sse")
                    self._sse_response.close()
                    self._sse_response = None
                    return False

                self._messages_path = endpoint
                logger.info("Playwright MCP SSE connected, messages path: %s", endpoint)

                # Start background reader
                self._reader_task = asyncio.create_task(self._sse_reader_loop())
                self._connected = True

                # Send initialize + initialized notification
                await self._do_initialize()

                return True

            except Exception as e:
                logger.error("Failed to connect Playwright MCP SSE: %s", e)
                await self._disconnect_sse()
                return False

    async def _read_endpoint_event(self) -> Optional[str]:
        """Read the initial 'endpoint' event from the SSE stream."""
        if not self._sse_response:
            return None

        event_type = ""
        async for line_bytes in self._sse_response.content:
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")

            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
                if event_type == "endpoint" and data:
                    return data
            elif line == "":
                # Empty line = end of event
                if event_type == "endpoint":
                    break
                event_type = ""

        return None

    async def _read_sse_line(self) -> Optional[str]:
        """Read a single SSE line, handling arbitrarily large payloads.

        ``aiohttp``'s ``StreamReader.readline()`` raises ``ValueError`` when a
        line exceeds the internal buffer (default 64 KB).  Playwright MCP can
        return very large ``data:`` lines (accessibility snapshots, base64
        screenshots).  We work around this by catching the error and falling
        back to reading the stream in fixed-size chunks until we hit ``\\n``.
        """
        if not self._sse_response:
            return None
        content = self._sse_response.content
        try:
            raw = await content.readline()
            return raw.decode("utf-8", errors="replace").rstrip("\n\r")
        except ValueError:
            # Line too long for readline — read in 256 KB chunks
            parts: list[bytes] = []
            while True:
                chunk = await content.read(256 * 1024)
                if not chunk:
                    break
                parts.append(chunk)
                if b"\n" in chunk:
                    break
            return b"".join(parts).decode("utf-8", errors="replace").rstrip("\n\r")

    async def _sse_reader_loop(self) -> None:
        """Background task that reads SSE events and resolves pending futures."""
        if not self._sse_response:
            return

        event_type = ""
        try:
            while True:
                line = await self._read_sse_line()
                if line is None:
                    break  # stream ended

                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_str = line[5:].strip()
                    if event_type == "message" and data_str:
                        try:
                            data = json.loads(data_str)
                            req_id = data.get("id")
                            if req_id is not None and req_id in self._pending:
                                future = self._pending.pop(req_id)
                                if not future.done():
                                    if "result" in data:
                                        future.set_result(data["result"])
                                    elif "error" in data:
                                        future.set_result({"error": data["error"]})
                                    else:
                                        future.set_result(data)
                        except json.JSONDecodeError:
                            pass
                elif line == "":
                    event_type = ""

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Playwright MCP SSE reader stopped: %s", e)
        finally:
            self._connected = False
            # Resolve any pending futures with errors
            for req_id, future in self._pending.items():
                if not future.done():
                    future.set_result({"error": "SSE connection closed"})
            self._pending.clear()

    async def _disconnect_sse(self) -> None:
        """Close the SSE connection and cancel the reader task."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        self._reader_task = None

        if self._sse_response:
            self._sse_response.close()
            self._sse_response = None

        self._messages_path = None
        self._connected = False
        self._pending.clear()

    async def _do_initialize(self) -> None:
        """Send the MCP initialize handshake + notification."""
        try:
            result = await self.call_tool_raw(
                method="initialize",
                params={
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "TradeClaw-Agent", "version": "1.0.0"},
                },
            )
            server_info = result.get("serverInfo", {}) if isinstance(result, dict) else {}
            logger.info("Playwright MCP initialized: %s", server_info)

            # Send initialized notification (no response expected)
            await self._send_notification("notifications/initialized")

        except Exception as e:
            logger.warning("Playwright MCP initialize handshake failed: %s", e)

    async def _send_notification(self, method: str, params: Optional[Dict] = None) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        base = self._get_base_url()
        if not base or not self._messages_path:
            return

        session = await self._ensure_session()
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params

        try:
            async with session.post(
                f"{base}{self._messages_path}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=5),
            ):
                pass
        except Exception as e:
            logger.debug("Failed to send notification %s: %s", method, e)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call_tool_raw(
        self,
        method: str,
        params: Dict[str, Any],
        timeout_seconds: float = 60,
    ) -> Dict[str, Any]:
        """
        Send a JSON-RPC request and wait for the response on the SSE stream.

        Automatically reconnects once if the SSE connection was lost.
        """
        max_retries = 2  # 1 initial attempt + 1 reconnect
        for attempt in range(max_retries):
            if not await self._connect_sse():
                return {"error": "Playwright MCP SSE connection not established"}

            base = self._get_base_url()
            if not base or not self._messages_path:
                return {"error": "Playwright MCP not connected"}

            session = await self._ensure_session()
            req_id = self._next_id()

            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }

            # Create a future to receive the response
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()
            self._pending[req_id] = future

            try:
                # POST the request
                async with session.post(
                    f"{base}{self._messages_path}",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status not in (200, 202, 204):
                        self._pending.pop(req_id, None)
                        body = await resp.text()
                        # Session expired — force reconnect on next attempt
                        if resp.status == 404 and attempt < max_retries - 1:
                            logger.info("Playwright MCP session expired, reconnecting...")
                            await self._disconnect_sse()
                            continue
                        return {"error": f"HTTP {resp.status}: {body[:200]}"}

                # Wait for the response on the SSE stream
                result = await asyncio.wait_for(future, timeout=timeout_seconds)

                # If we got "SSE connection closed", try reconnecting once
                if (
                    isinstance(result, dict)
                    and result.get("error") == "SSE connection closed"
                    and attempt < max_retries - 1
                ):
                    logger.info("Playwright MCP SSE connection lost, reconnecting...")
                    await self._disconnect_sse()
                    continue

                return result

            except asyncio.TimeoutError:
                self._pending.pop(req_id, None)
                return {"error": f"Timeout waiting for response (method={method})"}
            except Exception as e:
                self._pending.pop(req_id, None)
                # Connection error — try reconnecting once
                if attempt < max_retries - 1:
                    logger.info("Playwright MCP request error, reconnecting: %s", e)
                    await self._disconnect_sse()
                    continue
                logger.error("Playwright MCP request failed: %s", e)
                return {"error": str(e)}

        return {"error": "Playwright MCP: max retries exceeded"}

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the Playwright MCP server.

        Returns the tool result as a dict with ``content`` list.
        """
        return await self.call_tool_raw(
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
            timeout_seconds=60,
        )

    async def shutdown(self) -> None:
        """Close the SSE connection and HTTP session."""
        await self._disconnect_sse()
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._available = None
        logger.info("Playwright MCP client shut down")

    # Keep backward-compatible alias
    close = shutdown


# ------------------------------------------------------------------
# Helper: extract text content from MCP tool result
# ------------------------------------------------------------------

def _extract_text(result: Dict[str, Any]) -> str:
    """
    MCP tool results have a ``content`` list with typed entries.
    Extract all text entries and concatenate them.
    """
    if "error" in result:
        err = result["error"]
        if isinstance(err, dict):
            return json.dumps(err, ensure_ascii=False)
        return str(err)

    content = result.get("content", [])
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "image":
                    parts.append(f"[image: {item.get('mimeType', 'image/png')}]")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)

    # Fallback
    return json.dumps(result, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------
# LangChain Tools
# ------------------------------------------------------------------

def create_browser_tools(workflow) -> List[Tuple[Any, str]]:
    """
    Create browser automation tools backed by Playwright MCP Server.

    Args:
        workflow: WorkflowBase subclass instance

    Returns:
        [(tool_obj, "browser"), ...] for ToolRegistry.register_many()
    """
    tools: List[Tuple[Any, str]] = []

    # Always register tools — they will check availability at call time
    tools.append((_create_browser_navigate(workflow), "browser"))
    tools.append((_create_browser_snapshot(workflow), "browser"))
    tools.append((_create_browser_click(workflow), "browser"))
    tools.append((_create_browser_type_text(workflow), "browser"))
    tools.append((_create_browser_screenshot(workflow), "browser"))

    logger.info("Browser tools registered (Playwright MCP backend)")
    return tools


def _create_browser_navigate(wf):
    @tool
    async def browser_navigate(url: str) -> str:
        """
        Navigate to a URL in the browser and return the page accessibility snapshot.

        Uses a real headless browser that can render JavaScript, handle SPAs, etc.

        Difference from web_read:
        - browser_navigate uses a real browser, can handle JS-rendered dynamic content
        - web_read uses HTTP requests + Trafilatura, faster but only handles static HTML

        Use cases:
        - Pages requiring JavaScript rendering (SPAs, dynamic charts)
        - Content requiring authentication (use browser_click / browser_type to log in first)
        - Pages where web_read fails to extract content correctly

        Args:
            url: The web page URL to visit

        Returns:
            Accessibility snapshot of the page (structured text, LLM-friendly)
        """
        client = PlaywrightMCPClient.get_instance()
        if not await client.is_available():
            return json.dumps({
                "success": False,
                "error": "Playwright MCP server is not configured or reachable. "
                         "Set PLAYWRIGHT_MCP_URL in Settings.",
            }, ensure_ascii=False)

        try:
            await wf.message_manager.send_message(
                f"🌐 Browsing: {url[:80]}...", "info",
            )

            result = await client.call_tool("browser_navigate", {"url": url})
            text = _extract_text(result)

            await wf.message_manager.send_message(
                f"✅ Page loaded: {url[:60]}\nContent: {len(text)} chars",
                "info",
            )

            return text[:10000]  # Truncate to avoid token explosion

        except Exception as e:
            logger.error("browser_navigate failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return browser_navigate


def _create_browser_snapshot(wf):
    @tool
    async def browser_snapshot() -> str:
        """
        Capture an accessibility snapshot of the current browser page.

        Returns a structured text representation of the page content,
        optimized for LLM understanding. Much more token-efficient than
        screenshots. Each interactive element has a [ref] you can use
        with browser_click or browser_type_text.

        Use this after browser_navigate to understand page structure,
        or after performing actions to see the updated state.

        Returns:
            Accessibility tree as structured text
        """
        client = PlaywrightMCPClient.get_instance()
        if not await client.is_available():
            return json.dumps({
                "success": False,
                "error": "Playwright MCP server not available.",
            }, ensure_ascii=False)

        try:
            result = await client.call_tool("browser_snapshot", {})
            text = _extract_text(result)

            await wf.message_manager.send_message(
                f"📋 Page snapshot captured ({len(text)} chars)", "info",
            )

            return text[:15000]

        except Exception as e:
            logger.error("browser_snapshot failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return browser_snapshot


def _create_browser_click(wf):
    @tool
    async def browser_click(
        ref: str,
        element: str = "",
    ) -> str:
        """
        Click an element on the current browser page.

        Use browser_snapshot first to get element refs.
        Each element in the snapshot has a [ref] identifier.

        Args:
            ref: Exact element reference from the page snapshot (e.g. "s1e45")
            element: Human-readable element description (for logging)

        Returns:
            Result of the click action
        """
        client = PlaywrightMCPClient.get_instance()
        if not await client.is_available():
            return json.dumps({
                "success": False,
                "error": "Playwright MCP server not available.",
            }, ensure_ascii=False)

        try:
            args: Dict[str, Any] = {"ref": ref}
            if element:
                args["element"] = element

            result = await client.call_tool("browser_click", args)
            text = _extract_text(result)

            desc = element or ref
            await wf.message_manager.send_message(
                f"🖱️ Clicked: {desc}", "info",
            )

            return text[:10000]

        except Exception as e:
            logger.error("browser_click failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return browser_click


def _create_browser_type_text(wf):
    @tool
    async def browser_type_text(
        ref: str,
        text: str,
        element: str = "",
        submit: bool = False,
    ) -> str:
        """
        Type text into an editable element on the current browser page.

        Use browser_snapshot first to find the element ref.

        Args:
            ref: Exact element reference from the page snapshot
            text: Text to type into the element
            element: Human-readable element description (for logging)
            submit: Whether to press Enter after typing (e.g. to submit a search)

        Returns:
            Result of the type action
        """
        client = PlaywrightMCPClient.get_instance()
        if not await client.is_available():
            return json.dumps({
                "success": False,
                "error": "Playwright MCP server not available.",
            }, ensure_ascii=False)

        try:
            args: Dict[str, Any] = {"ref": ref, "text": text}
            if element:
                args["element"] = element
            if submit:
                args["submit"] = True

            result = await client.call_tool("browser_type", args)
            text_result = _extract_text(result)

            desc = element or ref
            await wf.message_manager.send_message(
                f"⌨️ Typed into {desc}: {text[:40]}...", "info",
            )

            return text_result[:10000]

        except Exception as e:
            logger.error("browser_type_text failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return browser_type_text


def _create_browser_screenshot(wf):
    @tool
    async def browser_screenshot() -> str:
        """
        Take a screenshot of the current browser page.

        Use this when you need to see the visual state of the page,
        such as charts, images, or layout issues. For most tasks,
        prefer browser_snapshot which returns structured text.

        Returns:
            Screenshot result (image info or base64 data)
        """
        client = PlaywrightMCPClient.get_instance()
        if not await client.is_available():
            return json.dumps({
                "success": False,
                "error": "Playwright MCP server not available.",
            }, ensure_ascii=False)

        try:
            result = await client.call_tool("browser_take_screenshot", {})
            text = _extract_text(result)

            await wf.message_manager.send_message(
                "📸 Screenshot taken", "info",
            )

            return text[:5000]

        except Exception as e:
            logger.error("browser_screenshot failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return browser_screenshot
