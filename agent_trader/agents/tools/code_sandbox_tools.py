"""
Code Execution Sandbox — OpenSandbox only (Docker-based isolation)

Provides secure Python code execution and terminal access via OpenSandbox,
allowing the Agent to:
- Execute data analysis code (pandas, numpy, etc.)
- Perform mathematical calculations
- Process and transform data
- Run arbitrary shell commands
- Install packages on-the-fly

Security strategy:
- **OpenSandbox (required)**: Full Docker-based isolation via opensandbox-server.
  Each execution runs in a disposable container with network/filesystem isolation.
  Requires opensandbox-server running (locally or remote).
- No local fallback — if OpenSandbox is unavailable, tools report an error.

Note on proxy workaround:
  OpenSandbox Server (as of v0.1.x) has a known bug where its proxy endpoint
  constructs an incorrect URL (host-mapped port + container IP).  We work around
  this by:
    1. Creating the sandbox with ``skip_health_check=True``
    2. Using the SDK's ``get_endpoint(port, use_server_proxy=False)`` to obtain
       the direct container_ip:port endpoint
    3. Rebuilding the SDK's internal adapters with the corrected endpoint
  This works in docker-compose (same Docker network) and local-dev (host network).

Dependencies:
- pip install opensandbox
- opensandbox-server must be running and reachable
"""

import asyncio
import base64
import json
from typing import Any, Dict, List, Optional, Tuple

from langchain.tools import tool

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


# ==================================================================
# OpenSandbox backend
# ==================================================================

class OpenSandboxBackend:
    """
    Manages an OpenSandbox container for code execution and terminal access.

    Lifecycle:
    - On first code execution, creates a sandbox container.
    - Reuses the same container for subsequent calls (session persistence).
    - Must be explicitly shut down via shutdown() to kill the container.
    """

    _instance: Optional["OpenSandboxBackend"] = None

    def __init__(self):
        self._sandbox = None
        self._initialized = False
        self._available: Optional[bool] = None  # None = not checked yet
        self._lock = asyncio.Lock()
        self._python_bin_dir: str = ""
        self._execd_fallback: Optional[str] = None
        self._execd_resolved: Optional[str] = None

    @classmethod
    def get_instance(cls) -> "OpenSandboxBackend":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def is_available(self) -> bool:
        """Check if OpenSandbox server is reachable (lightweight HTTP health check)."""
        if self._available is not None:
            return self._available

        try:
            from config import settings
            import aiohttp

            server_url = getattr(settings, "opensandbox_server_url", "")
            if not server_url:
                self._available = False
                return False

            # Lightweight health check — just hit /health endpoint
            url = server_url if server_url.startswith("http") else f"http://{server_url}"
            url = url.rstrip("/") + "/health"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        self._available = True
                        logger.info("OpenSandbox server is reachable at %s", server_url)
                        return True
                    else:
                        self._available = False
                        logger.info("OpenSandbox health check returned %d", resp.status)
                        return False

        except ImportError:
            self._available = False
            logger.info("aiohttp not installed, cannot check OpenSandbox availability")
            return False
        except Exception as e:
            self._available = False
            logger.info("OpenSandbox server not reachable: %s", e)
            return False

    def reset_availability(self):
        """Reset cached availability — forces re-check on next call."""
        self._available = None

    # ------------------------------------------------------------------
    # Proxy-bug workaround helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_server_url(server_url: str) -> Tuple[str, str]:
        """Extract (protocol, domain) from a URL like ``http://localhost:8080``."""
        domain = server_url
        protocol = "http"
        if domain.startswith("https://"):
            protocol = "https"
            domain = domain[len("https://"):]
        elif domain.startswith("http://"):
            domain = domain[len("http://"):]
        return protocol, domain.rstrip("/")

    async def _resolve_execd_endpoint(self, sandbox) -> Optional[str]:
        """Resolve the direct execd endpoint (host:port) via the SDK.

        Calls the OpenSandbox API with ``use_server_proxy=False``.  The API
        returns something like ``host.docker.internal:42711/proxy/44772`` — the
        ``/proxy/…`` suffix is an OpenSandbox Server bug; the real execd is
        listening directly on the mapped port.  We strip the suffix and return
        just ``host:port``.

        For local-dev (agent running on host), ``host.docker.internal`` may not
        resolve, so we also try ``localhost`` as a fallback.

        Returns the ``host:port`` string or None.
        """
        try:
            ep = await sandbox._sandbox_service.get_sandbox_endpoint(
                sandbox.id, 44772, use_server_proxy=False
            )
            if not ep or not ep.endpoint:
                return None

            raw = ep.endpoint
            logger.debug("SDK get_endpoint (direct) raw: %s", raw)

            # Strip the bogus /proxy/… suffix
            host_port = raw.split("/proxy/")[0] if "/proxy/" in raw else raw
            logger.debug("Resolved execd endpoint: %s", host_port)

            # If the host is host.docker.internal, also prepare a localhost
            # fallback for local-dev where the agent runs on the host directly.
            if "host.docker.internal" in host_port:
                self._execd_fallback = host_port.replace(
                    "host.docker.internal", "localhost"
                )
            else:
                self._execd_fallback = None

            return host_port

        except Exception as e:
            logger.debug("SDK get_endpoint(44772, proxy=False) failed: %s", e)
        return None

    async def _wait_for_execd(self, endpoint: str, timeout: float = 60) -> bool:
        """Poll ``http://<endpoint>/ping`` until execd is ready.

        If the primary endpoint is unreachable and a localhost fallback was
        stored by ``_resolve_execd_endpoint``, tries that too and updates
        ``endpoint`` in-place (returned via the ``_execd_resolved`` attr).
        """
        import aiohttp

        candidates = [endpoint]
        fallback = getattr(self, "_execd_fallback", None)
        if fallback and fallback != endpoint:
            candidates.append(fallback)

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            for candidate in candidates:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"http://{candidate}/ping",
                            timeout=aiohttp.ClientTimeout(total=2),
                        ) as resp:
                            if resp.status == 200:
                                # Store the working endpoint
                                self._execd_resolved = candidate
                                return True
                except Exception:
                    pass
            await asyncio.sleep(0.5)
        return False

    def _fix_sandbox_endpoint(self, sandbox, endpoint: str) -> None:
        """Rebuild SDK adapters with the correct direct endpoint."""
        from opensandbox.models.sandboxes import SandboxEndpoint
        from opensandbox.adapters.command_adapter import CommandsAdapter
        from opensandbox.adapters.health_adapter import HealthAdapter
        from opensandbox.adapters.filesystem_adapter import FilesystemAdapter
        from opensandbox.adapters.metrics_adapter import MetricsAdapter

        correct_ep = SandboxEndpoint(endpoint=endpoint)
        conn = sandbox.connection_config

        sandbox._command_service = CommandsAdapter(conn, correct_ep)
        sandbox._health_service = HealthAdapter(conn, correct_ep)
        sandbox._filesystem_service = FilesystemAdapter(conn, correct_ep)
        sandbox._metrics_service = MetricsAdapter(conn, correct_ep)

    # ------------------------------------------------------------------

    async def _ensure_initialized(self) -> bool:
        """Create sandbox container if not yet initialized."""
        if self._initialized and self._sandbox:
            return True

        async with self._lock:
            if self._initialized and self._sandbox:
                return True

            try:
                from opensandbox import Sandbox
                from opensandbox.config.connection import ConnectionConfig
                from config import settings
                from datetime import timedelta

                server_url = getattr(settings, "opensandbox_server_url", "")
                if not server_url:
                    return False

                protocol, domain = self._parse_server_url(server_url)

                conn = ConnectionConfig(
                    domain=domain,
                    protocol=protocol,
                    use_server_proxy=True,
                    request_timeout=timedelta(seconds=120),
                )

                # Create sandbox but skip the SDK's built-in health check
                # (it uses the buggy proxy endpoint and will always time out).
                # Sandbox lifetime: 24 hours — persistent across agent sessions.
                self._sandbox = await Sandbox.create(
                    "opensandbox/code-interpreter:v1.0.1",
                    timeout=timedelta(hours=24),
                    skip_health_check=True,
                    connection_config=conn,
                )
                logger.info("OpenSandbox container created: %s", self._sandbox.id)

                # Resolve the direct execd endpoint via SDK (no docker CLI needed)
                execd_endpoint = await self._resolve_execd_endpoint(self._sandbox)
                if not execd_endpoint:
                    logger.error(
                        "Could not resolve execd endpoint for sandbox %s.",
                        self._sandbox.id,
                    )
                    await self._cleanup()
                    return False

                # Wait for execd to become ready inside the container
                if not await self._wait_for_execd(execd_endpoint, timeout=60):
                    logger.error(
                        "Execd did not become ready at %s within 60s",
                        execd_endpoint,
                    )
                    await self._cleanup()
                    return False

                # Use the endpoint that actually responded to /ping
                working_endpoint = getattr(self, "_execd_resolved", execd_endpoint)

                # Patch SDK adapters with the correct direct endpoint
                self._fix_sandbox_endpoint(self._sandbox, working_endpoint)

                # Discover the Python bin directory that contains pip so we can
                # prepend it to PATH in every command.  The code-interpreter
                # image installs multiple Python versions under /opt/python/;
                # we pick the one matching the default ``python3``.
                self._python_bin_dir = ""
                try:
                    probe = await asyncio.wait_for(
                        self._sandbox.commands.run(
                            # 1) Try to find pip alongside the default python3
                            'PY=$(readlink -f $(which python3) 2>/dev/null) && '
                            'PYDIR=$(dirname "$PY") && '
                            'if [ -x "$PYDIR/pip" ]; then echo "$PYDIR"; exit 0; fi; '
                            # 2) Fallback: find any pip under /opt/python
                            'PIPPATH=$(find /opt/python -name pip -type f 2>/dev/null | head -1) && '
                            'if [ -n "$PIPPATH" ]; then dirname "$PIPPATH"; fi'
                        ),
                        timeout=10,
                    )
                    stdout = "\n".join(m.text for m in probe.logs.stdout).strip()
                    if stdout and "/" in stdout:
                        # Take the last non-empty line
                        self._python_bin_dir = stdout.strip().split("\n")[-1].strip()
                        logger.debug("Sandbox Python bin dir: %s", self._python_bin_dir)
                except Exception as e:
                    logger.debug("Failed to probe Python bin dir: %s", e)

                # Remove PEP 668 EXTERNALLY-MANAGED markers so that pip works
                # without --break-system-packages.  The sandbox is disposable
                # so there is no risk in doing this.
                try:
                    await asyncio.wait_for(
                        self._sandbox.commands.run(
                            'find / -name EXTERNALLY-MANAGED -delete 2>/dev/null; true'
                        ),
                        timeout=10,
                    )
                    logger.debug("Removed EXTERNALLY-MANAGED markers from sandbox")
                except Exception:
                    pass  # best-effort

                self._initialized = True
                logger.info(
                    "OpenSandbox ready (id=%s, execd=%s, ttl=24h)",
                    self._sandbox.id,
                    working_endpoint,
                )
                return True

            except Exception as e:
                logger.error("Failed to initialize OpenSandbox: %s", e)
                await self._cleanup()
                return False

    async def execute(
        self,
        code: str,
        *,
        timeout_seconds: int = 30,
        max_output_chars: int = 10000,
    ) -> Dict[str, Any]:
        """Execute Python code in the OpenSandbox container.

        Writes the code to a temp file inside the container and runs it with
        ``python3``, collecting stdout/stderr.
        """
        if not await self._ensure_initialized():
            raise RuntimeError(
                "OpenSandbox is not available. "
                "Please configure opensandbox_server_url in Settings and ensure "
                "the opensandbox-server is running."
            )

        try:
            # Encode code as base64 to avoid shell quoting issues
            b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
            cmd = self._with_path(
                f"echo {b64} | base64 -d > /tmp/_exec.py && "
                f"python3 /tmp/_exec.py"
            )

            execution = await asyncio.wait_for(
                self._sandbox.commands.run(cmd),
                timeout=timeout_seconds,
            )

            stdout_lines = [msg.text for msg in execution.logs.stdout]
            stderr_lines = [msg.text for msg in execution.logs.stderr]
            output = "\n".join(stdout_lines)[:max_output_chars]
            stderr = "\n".join(stderr_lines)[:2000]

            if execution.error:
                return {
                    "success": False,
                    "error": f"{execution.error.name}: {execution.error.value}",
                    "traceback": "\n".join(execution.error.traceback)[-2000:],
                    "output": output,
                    "stderr": stderr,
                    "backend": "opensandbox",
                }

            return {
                "success": True,
                "output": output,
                "stderr": stderr,
                "backend": "opensandbox",
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Code execution timed out after {timeout_seconds}s",
                "backend": "opensandbox",
            }

    def _with_path(self, command: str) -> str:
        """Prepend the discovered Python bin dir to PATH if available."""
        if self._python_bin_dir:
            return f'export PATH="{self._python_bin_dir}:$PATH" && {command}'
        return command

    async def run_command(
        self,
        command: str,
        *,
        timeout_seconds: int = 60,
        max_output_chars: int = 20000,
    ) -> Dict[str, Any]:
        """Execute an arbitrary shell command in the OpenSandbox container.

        This gives the agent full terminal access (install packages, run
        scripts, inspect the filesystem, etc.) inside the isolated sandbox.
        """
        if not await self._ensure_initialized():
            raise RuntimeError(
                "OpenSandbox is not available. "
                "Please configure opensandbox_server_url in Settings and ensure "
                "the opensandbox-server is running."
            )

        try:
            result = await asyncio.wait_for(
                self._sandbox.commands.run(self._with_path(command)),
                timeout=timeout_seconds,
            )

            stdout_lines = [msg.text for msg in result.logs.stdout]
            stderr_lines = [msg.text for msg in result.logs.stderr]
            stdout = "\n".join(stdout_lines)[:max_output_chars]
            stderr = "\n".join(stderr_lines)[:max_output_chars]
            exit_code = getattr(result, "exit_code", None)

            return {
                "success": exit_code == 0 if exit_code is not None else True,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "backend": "opensandbox",
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Command timed out after {timeout_seconds}s",
                "backend": "opensandbox",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "backend": "opensandbox",
            }

    async def _cleanup(self):
        """Clean up sandbox resources."""
        self._initialized = False
        if self._sandbox:
            try:
                await self._sandbox.kill()
                await self._sandbox.close()
            except Exception as e:
                logger.warning("Error cleaning up sandbox: %s", e)
            self._sandbox = None

    async def shutdown(self):
        """Shut down the sandbox container."""
        await self._cleanup()
        logger.info("OpenSandbox backend shut down")


# ==================================================================
# LangChain Tools
# ==================================================================

_OPENSANDBOX_UNAVAILABLE_MSG = (
    "OpenSandbox is not configured or not reachable. "
    "Set opensandbox_server_url in Settings and ensure opensandbox-server is running. "
    "Code execution requires OpenSandbox — no local fallback is available."
)


def create_code_sandbox_tools(workflow) -> List[Tuple[Any, str]]:
    """
    Create code execution sandbox tools (OpenSandbox only).

    Args:
        workflow: WorkflowBase subclass instance

    Returns:
        [(tool_obj, "sandbox"), ...] for ToolRegistry.register_many()
    """
    tools: List[Tuple[Any, str]] = []

    tools.append((_create_execute_python(workflow), "sandbox"))
    tools.append((_create_execute_terminal(workflow), "sandbox"))

    logger.info("Code sandbox tools registered (OpenSandbox required)")
    return tools


def _create_execute_python(wf):
    @tool
    async def execute_python(
        code: str,
        timeout_seconds: int = 30,
    ) -> str:
        """
        Execute Python code in an isolated OpenSandbox Docker container.

        The code runs in a secure, disposable container with full Python
        environment (including pip packages like pandas, numpy, scipy, etc.).
        The container is isolated from the host — no access to local files
        or network resources.

        Use cases:
        - Calculate portfolio metrics (Sharpe ratio, volatility, correlation, etc.)
        - Process and analyze market data
        - Perform statistical calculations
        - Data format conversion
        - Any Python computation

        Args:
            code: Python code to execute. Use print() for output.
                  Variables defined at the end are automatically returned.
            timeout_seconds: Maximum execution time (seconds), default 30, max 120

        Returns:
            JSON with execution results, including output (stdout) and variables

        Example:
            # Calculate Sharpe ratio
            import numpy as np
            returns = [0.02, -0.01, 0.03, 0.01, -0.02, 0.04]
            sharpe = np.mean(returns) / np.std(returns) * (252 ** 0.5)
            print(f"Annualized Sharpe Ratio: {sharpe:.4f}")
        """
        try:
            if timeout_seconds < 1:
                timeout_seconds = 1
            elif timeout_seconds > 120:
                timeout_seconds = 120

            backend = OpenSandboxBackend.get_instance()
            if not await backend.is_available():
                return json.dumps({
                    "success": False,
                    "error": _OPENSANDBOX_UNAVAILABLE_MSG,
                }, ensure_ascii=False)

            await wf.message_manager.send_message(
                f"🔧 Executing Python code ({len(code)} chars) in OpenSandbox...",
                "info",
            )

            result = await backend.execute(
                code,
                timeout_seconds=timeout_seconds,
            )

            backend_name = result.get("backend", "opensandbox")
            if result.get("success"):
                output_preview = (result.get("output", "") or "")[:200]
                var_count = len(result.get("variables", {}))
                await wf.message_manager.send_message(
                    f"✅ Code executed successfully [{backend_name}]\n"
                    f"Output: {output_preview or '(none)'}{'...' if len(result.get('output', '')) > 200 else ''}\n"
                    f"Variables: {var_count}",
                    "info",
                )
            else:
                error_msg = result.get("error", "Unknown error")[:200]
                await wf.message_manager.send_message(
                    f"⚠️ Code execution failed [{backend_name}]: {error_msg}",
                    "warning",
                )

            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error("execute_python failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return execute_python


def _create_execute_terminal(wf):
    @tool
    async def execute_terminal(
        command: str,
        timeout_seconds: int = 60,
    ) -> str:
        """
        Execute a shell command in an isolated OpenSandbox container.

        This tool provides full terminal access inside a secure Docker sandbox.
        You can install packages, run scripts, inspect files, compile code, etc.

        **Requires OpenSandbox to be configured** (opensandbox_server_url in
        settings). If OpenSandbox is not available, this tool will return an
        error.

        Use cases:
        - Install Python packages: ``pip install <package>`` (pip works directly)
        - Install via uv (faster): ``uv pip install <package>``
        - Run shell scripts or CLI tools
        - Inspect filesystem, download data with curl/wget
        - Compile and run programs in any language
        - Chain multiple commands with && or ;

        Note: The sandbox has a persistent container per session, so packages
        installed in one call are available in subsequent calls.

        Args:
            command: Shell command to execute (e.g. "pip install pandas && python script.py")
            timeout_seconds: Maximum execution time (seconds), default 60, max 300

        Returns:
            JSON with stdout, stderr, exit_code, and success status

        Example:
            pip install yfinance && python -c "import yfinance as yf; print(yf.download('AAPL', period='5d'))"
        """
        try:
            if timeout_seconds < 1:
                timeout_seconds = 1
            elif timeout_seconds > 300:
                timeout_seconds = 300

            backend = OpenSandboxBackend.get_instance()
            if not await backend.is_available():
                return json.dumps({
                    "success": False,
                    "error": _OPENSANDBOX_UNAVAILABLE_MSG,
                }, ensure_ascii=False)

            await wf.message_manager.send_message(
                f"🖥️ Running terminal command ({len(command)} chars) in OpenSandbox...",
                "info",
            )

            result = await backend.run_command(
                command,
                timeout_seconds=timeout_seconds,
            )

            if result.get("success"):
                stdout_preview = (result.get("stdout", "") or "")[:200]
                await wf.message_manager.send_message(
                    f"✅ Command completed (exit {result.get('exit_code', '?')})\n"
                    f"Output: {stdout_preview or '(none)'}{'...' if len(result.get('stdout', '')) > 200 else ''}",
                    "info",
                )
            else:
                error_msg = result.get("error") or result.get("stderr", "")[:200]
                await wf.message_manager.send_message(
                    f"⚠️ Command failed (exit {result.get('exit_code', '?')}): {error_msg}",
                    "warning",
                )

            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

        except Exception as e:
            logger.error("execute_terminal failed: %s", e)
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    return execute_terminal
