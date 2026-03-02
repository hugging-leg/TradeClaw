"""
Browser Automation Agent Tools — Playwright

Provides browser automation capabilities via Playwright, allowing the Agent to:
- Visit web pages that require JavaScript rendering
- Take page screenshots
- Extract dynamically loaded content
- Interact with forms, buttons, etc.

Architecture:
- BrowserManager: Manages the Playwright browser instance (singleton, lazy init)
- Three tools:
  1. browser_goto: Navigate to a URL and extract page content
  2. browser_screenshot: Take a screenshot of the current page
  3. browser_action: Perform page interactions (click, fill, etc.)

Backend options (selected automatically):
1. **OpenSandbox (preferred)**: Launches a browser container via opensandbox-server
   and connects to it via CDP. Full Docker-based isolation.
2. **Local Playwright (fallback)**: Runs Playwright in the host process with
   --no-sandbox. Less secure but works without Docker.

Dependencies:
- pip install playwright && playwright install chromium
- For OpenSandbox: pip install opensandbox (+ opensandbox-server running)
"""

import asyncio
import base64
import json
from typing import Any, Dict, List, Optional, Tuple

from langchain.tools import tool

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Browser Manager (Singleton)
# ------------------------------------------------------------------

class BrowserManager:
    """
    Playwright Browser Manager

    Lazy initialization — the browser is started on first use.
    Supports single-page reuse to avoid frequent create/destroy cycles.

    Backend selection:
    - If opensandbox_server_url is configured, tries to launch a browser
      container in OpenSandbox and connect via CDP.
    - Otherwise, falls back to local Playwright (headless Chromium).
    """

    _instance: Optional["BrowserManager"] = None

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self._backend = "none"  # "opensandbox" or "local"
        # OpenSandbox resources
        self._sandbox = None

    @classmethod
    def get_instance(cls) -> "BrowserManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _try_opensandbox(self) -> bool:
        """Try to initialize browser via OpenSandbox container."""
        try:
            from opensandbox import Sandbox
            from opensandbox.config.connection import ConnectionConfig
            from playwright.async_api import async_playwright
            from config import settings
            from datetime import timedelta

            server_url = getattr(settings, "opensandbox_server_url", "")
            if not server_url:
                return False

            conn = ConnectionConfig(domain=server_url)

            # Create a sandbox with a Playwright-capable image
            self._sandbox = await Sandbox.create(
                "opensandbox/playwright:v1.0.0",
                entrypoint=["chromium", "--headless", "--remote-debugging-port=9222",
                             "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
                timeout=timedelta(minutes=30),
                connection_config=conn,
            )

            # Get the CDP endpoint from the sandbox
            endpoint = await self._sandbox.get_endpoint(9222)
            cdp_url = f"ws://{endpoint.host}:{endpoint.port}"

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)

            contexts = self._browser.contexts
            if contexts:
                self._page = contexts[0].pages[0] if contexts[0].pages else await contexts[0].new_page()
            else:
                context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                )
                self._page = await context.new_page()

            self._backend = "opensandbox"
            logger.info("Browser initialized via OpenSandbox container (CDP)")
            return True

        except ImportError:
            return False
        except Exception as e:
            logger.info("OpenSandbox browser init failed (will try local): %s", e)
            # Clean up partial state
            if self._sandbox:
                try:
                    await self._sandbox.kill()
                    await self._sandbox.close()
                except Exception:
                    pass
                self._sandbox = None
            return False

    async def _try_local_playwright(self) -> bool:
        """Initialize browser using local Playwright."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._page = await context.new_page()
            self._backend = "local"
            logger.info("Browser initialized (local Playwright + Chromium headless)")
            return True

        except ImportError:
            logger.warning(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
            return False
        except Exception as e:
            logger.error("Failed to initialize local browser: %s", e)
            return False

    async def _ensure_initialized(self) -> bool:
        """Ensure the browser is initialized."""
        if self._initialized and self._browser and self._browser.is_connected():
            return True

        async with self._lock:
            if self._initialized and self._browser and self._browser.is_connected():
                return True

            # Try OpenSandbox first, then local
            if await self._try_opensandbox():
                self._initialized = True
                return True

            if await self._try_local_playwright():
                self._initialized = True
                return True

            return False

    @property
    def backend(self) -> str:
        """Return the current backend name."""
        return self._backend

    async def goto(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout_ms: int = 30000,
    ) -> Dict[str, Any]:
        """
        Navigate to a URL.

        Returns:
            {"success": bool, "url": str, "title": str, "content": str, "backend": str}
        """
        if not await self._ensure_initialized():
            return {"success": False, "error": "Browser not available"}

        try:
            response = await self._page.goto(
                url,
                wait_until=wait_until,
                timeout=timeout_ms,
            )
            # Wait for page to stabilize
            await self._page.wait_for_load_state("networkidle", timeout=10000)

            title = await self._page.title()
            # Extract main content
            content = await self._page.evaluate("""
                () => {
                    // Remove scripts and styles
                    const scripts = document.querySelectorAll('script, style, nav, header, footer');
                    scripts.forEach(el => el.remove());
                    
                    // Get main content
                    const main = document.querySelector('main, article, [role="main"], .content, #content');
                    if (main) return main.innerText;
                    return document.body.innerText;
                }
            """)

            return {
                "success": True,
                "url": self._page.url,
                "title": title,
                "status": response.status if response else None,
                "content": content[:8000] if content else "",
                "backend": self._backend,
            }

        except Exception as e:
            logger.error("Browser goto failed for %s: %s", url, e)
            return {"success": False, "url": url, "error": str(e)}

    async def screenshot(self, *, full_page: bool = False) -> Dict[str, Any]:
        """
        Take a screenshot of the current page.

        Returns:
            {"success": bool, "url": str, "image_base64": str}
        """
        if not await self._ensure_initialized():
            return {"success": False, "error": "Browser not available"}

        try:
            screenshot_bytes = await self._page.screenshot(
                full_page=full_page,
                type="png",
            )
            image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            return {
                "success": True,
                "url": self._page.url,
                "title": await self._page.title(),
                "image_base64": image_b64[:200] + "...",  # Truncate base64 (too long)
                "image_size_bytes": len(screenshot_bytes),
                "backend": self._backend,
            }

        except Exception as e:
            logger.error("Browser screenshot failed: %s", e)
            return {"success": False, "error": str(e)}

    async def click(self, selector: str) -> Dict[str, Any]:
        """Click an element."""
        if not await self._ensure_initialized():
            return {"success": False, "error": "Browser not available"}

        try:
            await self._page.click(selector, timeout=5000)
            await self._page.wait_for_load_state("networkidle", timeout=5000)
            return {
                "success": True,
                "selector": selector,
                "url": self._page.url,
            }
        except Exception as e:
            return {"success": False, "selector": selector, "error": str(e)}

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """Fill an input field."""
        if not await self._ensure_initialized():
            return {"success": False, "error": "Browser not available"}

        try:
            await self._page.fill(selector, value, timeout=5000)
            return {"success": True, "selector": selector}
        except Exception as e:
            return {"success": False, "selector": selector, "error": str(e)}

    async def evaluate(self, script: str) -> Dict[str, Any]:
        """Execute JavaScript."""
        if not await self._ensure_initialized():
            return {"success": False, "error": "Browser not available"}

        try:
            result = await self._page.evaluate(script)
            return {"success": True, "result": str(result)[:5000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_page_info(self) -> Dict[str, Any]:
        """Get current page information."""
        if not self._initialized or not self._page:
            return {"url": None, "title": None}
        try:
            return {
                "url": self._page.url,
                "title": await self._page.title(),
                "backend": self._backend,
            }
        except Exception:
            return {"url": None, "title": None}

    async def shutdown(self) -> None:
        """Close the browser and clean up all resources."""
        try:
            if self._page:
                await self._page.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.error("Error closing browser: %s", e)
        finally:
            self._page = None
            self._browser = None
            self._playwright = None
            self._initialized = False

        # Clean up OpenSandbox container
        if self._sandbox:
            try:
                await self._sandbox.kill()
                await self._sandbox.close()
            except Exception as e:
                logger.warning("Error killing OpenSandbox browser container: %s", e)
            finally:
                self._sandbox = None

        self._backend = "none"
        logger.info("Browser manager shut down")

    # Keep backward-compatible alias
    close = shutdown


# ------------------------------------------------------------------
# LangChain Tools
# ------------------------------------------------------------------

def create_browser_tools(workflow) -> List[Tuple[Any, str]]:
    """
    Create browser automation tools.

    Args:
        workflow: WorkflowBase subclass instance

    Returns:
        [(tool_obj, "browser"), ...] for ToolRegistry.register_many()
    """
    tools: List[Tuple[Any, str]] = []

    # Check if Playwright is available
    try:
        import playwright  # noqa: F401
    except ImportError:
        logger.info(
            "Playwright not installed, browser tools not registered. "
            "Install: pip install playwright && playwright install chromium"
        )
        return tools

    tools.append((_create_browser_goto(workflow), "browser"))
    tools.append((_create_browser_screenshot(workflow), "browser"))
    tools.append((_create_browser_action(workflow), "browser"))

    logger.info("Browser automation tools registered (OpenSandbox > local Playwright)")
    return tools


def _create_browser_goto(wf):
    @tool
    async def browser_goto(
        url: str,
        wait_until: str = "domcontentloaded",
    ) -> str:
        """
        Visit a web page using a real browser and extract its content.
        Suitable for pages that require JavaScript rendering.

        When OpenSandbox is configured, the browser runs in an isolated Docker
        container for security. Otherwise, falls back to local Playwright.

        Difference from web_read:
        - browser_goto uses a real browser, can handle JS-rendered dynamic content
        - web_read uses HTTP requests + Trafilatura, faster but only handles static HTML

        Use cases:
        - Pages requiring JavaScript rendering (SPAs, dynamic charts)
        - Content requiring authentication (use browser_action to log in first)
        - Pages where web_read fails to extract content correctly

        Args:
            url: The web page URL to visit
            wait_until: Wait condition. "domcontentloaded" (DOM loaded) or "networkidle" (network idle)

        Returns:
            JSON with page info (title, URL, body content)
        """
        try:
            await wf.message_manager.send_message(
                f"🌐 Browsing: {url[:80]}...",
                "info",
            )

            manager = BrowserManager.get_instance()
            result = await manager.goto(url, wait_until=wait_until)

            if result.get("success"):
                content_len = len(result.get("content", ""))
                backend = result.get("backend", "unknown")
                await wf.message_manager.send_message(
                    f"✅ Page loaded [{backend}]: {result.get('title', '')[:60]}\n"
                    f"Extracted {content_len} characters",
                    "info",
                )
            else:
                await wf.message_manager.send_message(
                    f"⚠️ Page load failed: {result.get('error', 'Unknown error')}",
                    "warning",
                )

            return json.dumps(result, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error("browser_goto failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return browser_goto


def _create_browser_screenshot(wf):
    @tool
    async def browser_screenshot(
        full_page: bool = False,
    ) -> str:
        """
        Take a screenshot of the current browser page. Must use browser_goto first.

        Use cases:
        - Record current page state
        - View charts and visualizations
        - Debug page loading issues

        Args:
            full_page: Whether to capture the full page (including scroll area). Default False (visible area only)

        Returns:
            JSON with screenshot info (image size, etc.; base64 data is truncated)
        """
        try:
            manager = BrowserManager.get_instance()
            result = await manager.screenshot(full_page=full_page)

            if result.get("success"):
                size_kb = result.get("image_size_bytes", 0) / 1024
                await wf.message_manager.send_message(
                    f"📸 Screenshot taken ({size_kb:.1f} KB)",
                    "info",
                )
            else:
                await wf.message_manager.send_message(
                    f"⚠️ Screenshot failed: {result.get('error', 'Unknown error')}",
                    "warning",
                )

            return json.dumps(result, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error("browser_screenshot failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return browser_screenshot


def _create_browser_action(wf):
    @tool
    async def browser_action(
        action: str,
        selector: str = "",
        value: str = "",
    ) -> str:
        """
        Perform an interaction on the current browser page. Must use browser_goto first.

        Use cases:
        - Click buttons or links
        - Fill search boxes or forms
        - Execute JavaScript to extract specific data

        Args:
            action: Action type. Options:
                - "click": Click an element (requires selector)
                - "fill": Fill an input field (requires selector and value)
                - "evaluate": Execute JavaScript (value is JS code)
                - "get_text": Get element text (requires selector)
            selector: CSS selector, e.g. "#search-input", ".submit-btn", "button[type=submit]"
            value: Input value or JavaScript code

        Returns:
            JSON with action result
        """
        try:
            manager = BrowserManager.get_instance()

            if action == "click":
                if not selector:
                    return json.dumps({"success": False, "error": "selector is required for click"})
                result = await manager.click(selector)

            elif action == "fill":
                if not selector or not value:
                    return json.dumps({"success": False, "error": "selector and value are required for fill"})
                result = await manager.fill(selector, value)

            elif action == "evaluate":
                if not value:
                    return json.dumps({"success": False, "error": "value (JS code) is required for evaluate"})
                result = await manager.evaluate(value)

            elif action == "get_text":
                if not selector:
                    return json.dumps({"success": False, "error": "selector is required for get_text"})
                result = await manager.evaluate(
                    f'document.querySelector("{selector}")?.innerText || "Element not found"'
                )

            else:
                result = {"success": False, "error": f"Unknown action: {action}"}

            action_desc = f"{action}"
            if selector:
                action_desc += f" ({selector})"
            if result.get("success"):
                await wf.message_manager.send_message(
                    f"✅ Browser action completed: {action_desc}",
                    "info",
                )
            else:
                await wf.message_manager.send_message(
                    f"⚠️ Browser action failed: {action_desc} - {result.get('error', '')}",
                    "warning",
                )

            return json.dumps(result, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error("browser_action failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return browser_action
