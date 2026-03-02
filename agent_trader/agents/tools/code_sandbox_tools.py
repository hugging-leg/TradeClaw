"""
Code Execution Sandbox — OpenSandbox (Docker) with RestrictedPython fallback

Provides a secure Python code execution environment, allowing the Agent to:
- Execute data analysis code (pandas, numpy, etc.)
- Perform mathematical calculations
- Process and transform data
- Generate simple visualization descriptions

Security strategy (layered):
1. **OpenSandbox (preferred)**: Full Docker-based isolation via opensandbox-server.
   Each execution runs in a disposable container with network/filesystem isolation.
   Requires opensandbox-server running (locally or remote).
2. **RestrictedPython (fallback)**: In-process restricted execution when OpenSandbox
   is unavailable. Uses AST-level restrictions and whitelisted modules.
   NOT suitable for untrusted arbitrary code.
3. **Simple exec() (last resort)**: When neither OpenSandbox nor RestrictedPython
   is installed. Minimal restrictions via manual builtins filtering.

Dependencies:
- OpenSandbox: pip install opensandbox opensandbox-code-interpreter
- RestrictedPython: pip install RestrictedPython
"""

import asyncio
import io
import json
import math
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Dict, List, Optional, Tuple

from langchain.tools import tool

from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)


# ==================================================================
# OpenSandbox backend
# ==================================================================

class OpenSandboxBackend:
    """
    Manages an OpenSandbox code interpreter container.

    Lifecycle:
    - On first code execution, creates a sandbox container + code interpreter.
    - Reuses the same container for subsequent calls (session persistence).
    - Must be explicitly shut down via shutdown() to kill the container.
    """

    _instance: Optional["OpenSandboxBackend"] = None

    def __init__(self):
        self._sandbox = None
        self._interpreter = None
        self._context = None
        self._initialized = False
        self._available: Optional[bool] = None  # None = not checked yet
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "OpenSandboxBackend":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def is_available(self) -> bool:
        """Check if OpenSandbox server is reachable."""
        if self._available is not None:
            return self._available

        try:
            from opensandbox import Sandbox
            from opensandbox.config.connection import ConnectionConfig
            from config import settings

            server_url = getattr(settings, "opensandbox_server_url", "")
            if not server_url:
                self._available = False
                return False

            # Try to connect by creating a minimal sandbox
            conn = ConnectionConfig(domain=server_url)
            sandbox = await Sandbox.create(
                "opensandbox/code-interpreter:v1.0.1",
                entrypoint=["/opt/opensandbox/code-interpreter.sh"],
                env={"PYTHON_VERSION": "3.11"},
                connection_config=conn,
                skip_health_check=True,
            )
            await sandbox.kill()
            await sandbox.close()
            self._available = True
            logger.info("OpenSandbox server is reachable at %s", server_url)
            return True
        except ImportError:
            self._available = False
            logger.info("opensandbox SDK not installed, OpenSandbox unavailable")
            return False
        except Exception as e:
            self._available = False
            logger.info("OpenSandbox server not reachable: %s", e)
            return False

    async def _ensure_initialized(self) -> bool:
        """Create sandbox container and code interpreter if not yet initialized."""
        if self._initialized and self._sandbox:
            return True

        async with self._lock:
            if self._initialized and self._sandbox:
                return True

            try:
                from opensandbox import Sandbox
                from opensandbox.config.connection import ConnectionConfig
                from code_interpreter import CodeInterpreter, SupportedLanguage
                from config import settings
                from datetime import timedelta

                server_url = getattr(settings, "opensandbox_server_url", "")
                if not server_url:
                    return False

                conn = ConnectionConfig(domain=server_url)

                self._sandbox = await Sandbox.create(
                    "opensandbox/code-interpreter:v1.0.1",
                    entrypoint=["/opt/opensandbox/code-interpreter.sh"],
                    env={"PYTHON_VERSION": "3.11"},
                    timeout=timedelta(minutes=30),
                    connection_config=conn,
                )

                self._interpreter = await CodeInterpreter.create(self._sandbox)
                self._context = await self._interpreter.codes.create_context(
                    SupportedLanguage.PYTHON
                )

                self._initialized = True
                logger.info("OpenSandbox code interpreter initialized")
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
        """Execute code in the OpenSandbox container."""
        if not await self._ensure_initialized():
            raise RuntimeError("OpenSandbox not initialized")

        try:
            execution = await asyncio.wait_for(
                self._interpreter.codes.run(code, context=self._context),
                timeout=timeout_seconds,
            )

            # Collect stdout
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

            # Collect results
            results = {}
            for r in execution.result:
                if r.text:
                    results["result"] = r.text

            return {
                "success": True,
                "output": output,
                "stderr": stderr,
                "variables": results,
                "backend": "opensandbox",
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Code execution timed out after {timeout_seconds}s",
                "backend": "opensandbox",
            }

    async def _cleanup(self):
        """Clean up sandbox resources."""
        self._initialized = False
        self._context = None
        self._interpreter = None
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
# RestrictedPython fallback backend
# ==================================================================

# Whitelisted modules — only these modules can be imported by the Agent
_SAFE_MODULES = {
    "math",
    "statistics",
    "decimal",
    "fractions",
    "random",
    "datetime",
    "json",
    "re",
    "collections",
    "itertools",
    "functools",
    "operator",
    "string",
    "textwrap",
    "csv",
    "io",
}

# Optional data analysis modules (if installed)
_OPTIONAL_MODULES = {
    "numpy",
    "pandas",
    "scipy",
}


def _safe_import(name, *args, **kwargs):
    """Safe import function — only allows whitelisted modules."""
    allowed = _SAFE_MODULES | _OPTIONAL_MODULES
    # Allow submodules (e.g. numpy.linalg)
    top_level = name.split(".")[0]
    if top_level not in allowed:
        raise ImportError(
            f"Module '{name}' is not allowed in the sandbox. "
            f"Allowed modules: {', '.join(sorted(allowed))}"
        )
    return __builtins__["__import__"](name, *args, **kwargs) if isinstance(__builtins__, dict) else __import__(name, *args, **kwargs)


def _build_restricted_globals() -> Optional[Dict[str, Any]]:
    """Build restricted global namespace using RestrictedPython."""
    try:
        from RestrictedPython import safe_globals, compile_restricted
        from RestrictedPython.Eval import default_guarded_getattr
        from RestrictedPython.Guards import (
            guarded_unpack_sequence,
            safer_getattr,
        )

        restricted = dict(safe_globals)

        # Safe getattr
        restricted["_getattr_"] = safer_getattr
        restricted["_getiter_"] = iter
        restricted["_getitem_"] = lambda obj, key: obj[key]

        # Allow unpack
        restricted["_iter_unpack_sequence_"] = guarded_unpack_sequence

        # Safe import
        restricted["__import__"] = _safe_import
        restricted["__builtins__"]["__import__"] = _safe_import

        # Common safe built-in functions
        safe_builtins_extra = {
            "abs", "all", "any", "bin", "bool", "bytes", "chr", "complex",
            "dict", "dir", "divmod", "enumerate", "filter", "float",
            "format", "frozenset", "hash", "hex", "id", "int", "isinstance",
            "issubclass", "iter", "len", "list", "map", "max", "min",
            "next", "oct", "ord", "pow", "print", "range", "repr",
            "reversed", "round", "set", "slice", "sorted", "str", "sum",
            "tuple", "type", "zip",
        }
        for name in safe_builtins_extra:
            if name in dir(__builtins__) if isinstance(__builtins__, type) else name in __builtins__:
                restricted["__builtins__"][name] = getattr(__builtins__, name) if not isinstance(__builtins__, dict) else __builtins__[name]

        return restricted

    except ImportError:
        return None


def _build_simple_globals() -> Dict[str, Any]:
    """
    Build simplified restricted global namespace (fallback when RestrictedPython is unavailable).

    Uses exec() + manual restrictions. Lower security but functional.
    """
    safe_builtins = {
        "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
        "bytes": bytes, "chr": chr, "complex": complex, "dict": dict,
        "divmod": divmod, "enumerate": enumerate, "filter": filter,
        "float": float, "format": format, "frozenset": frozenset,
        "hash": hash, "hex": hex, "int": int, "isinstance": isinstance,
        "issubclass": issubclass, "iter": iter, "len": len, "list": list,
        "map": map, "max": max, "min": min, "next": next, "oct": oct,
        "ord": ord, "pow": pow, "print": print, "range": range,
        "repr": repr, "reversed": reversed, "round": round, "set": set,
        "slice": slice, "sorted": sorted, "str": str, "sum": sum,
        "tuple": tuple, "type": type, "zip": zip,
        "True": True, "False": False, "None": None,
        "__import__": _safe_import,
    }

    return {"__builtins__": safe_builtins}


async def _execute_code_local(
    code: str,
    *,
    timeout_seconds: int = 30,
    max_output_chars: int = 10000,
) -> Dict[str, Any]:
    """
    Execute Python code in a local restricted environment (RestrictedPython or simple exec).

    Returns:
        {"success": bool, "output": str, "error": str?, "variables": dict?, "backend": str}
    """
    use_restricted = True
    try:
        from RestrictedPython import compile_restricted
    except ImportError:
        use_restricted = False
        logger.info("RestrictedPython not installed, using simple sandbox")

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    def _run():
        if use_restricted:
            from RestrictedPython import compile_restricted

            restricted_globals = _build_restricted_globals()
            if restricted_globals is None:
                raise RuntimeError("Failed to build restricted globals")

            byte_code = compile_restricted(
                code,
                filename="<sandbox>",
                mode="exec",
            )

            if byte_code.errors:
                return {
                    "success": False,
                    "error": "Compilation errors:\n" + "\n".join(byte_code.errors),
                    "backend": "restricted_python",
                }

            local_vars: Dict[str, Any] = {}
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(byte_code.code, restricted_globals, local_vars)

        else:
            simple_globals = _build_simple_globals()
            local_vars: Dict[str, Any] = {}

            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code, simple_globals, local_vars)

        # Collect user-defined variables (exclude internal ones)
        user_vars = {}
        for k, v in local_vars.items():
            if k.startswith("_"):
                continue
            try:
                json.dumps(v, default=str)
                user_vars[k] = v
            except (TypeError, ValueError):
                user_vars[k] = repr(v)[:500]

        backend = "restricted_python" if use_restricted else "simple_exec"
        return {
            "success": True,
            "output": stdout_capture.getvalue()[:max_output_chars],
            "stderr": stderr_capture.getvalue()[:2000],
            "variables": user_vars,
            "backend": backend,
        }

    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _run),
            timeout=timeout_seconds,
        )
        return result

    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": f"Code execution timed out after {timeout_seconds} seconds",
            "output": stdout_capture.getvalue()[:max_output_chars],
            "backend": "local",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[-2000:],
            "output": stdout_capture.getvalue()[:max_output_chars],
            "backend": "local",
        }


# ==================================================================
# Unified execute_code dispatcher
# ==================================================================

async def execute_code(
    code: str,
    *,
    timeout_seconds: int = 30,
    max_output_chars: int = 10000,
) -> Dict[str, Any]:
    """
    Execute Python code using the best available backend.

    Priority: OpenSandbox (Docker) > RestrictedPython > simple exec.
    """
    # Try OpenSandbox first
    backend = OpenSandboxBackend.get_instance()
    if await backend.is_available():
        try:
            return await backend.execute(
                code,
                timeout_seconds=timeout_seconds,
                max_output_chars=max_output_chars,
            )
        except Exception as e:
            logger.warning("OpenSandbox execution failed, falling back to local: %s", e)

    # Fallback to local execution
    return await _execute_code_local(
        code,
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
    )


# ==================================================================
# LangChain Tools
# ==================================================================

def create_code_sandbox_tools(workflow) -> List[Tuple[Any, str]]:
    """
    Create code execution sandbox tools.

    Args:
        workflow: WorkflowBase subclass instance

    Returns:
        [(tool_obj, "sandbox"), ...] for ToolRegistry.register_many()
    """
    tools: List[Tuple[Any, str]] = []

    tools.append((_create_execute_python(workflow), "sandbox"))

    # Log which backend will be used
    logger.info("Code sandbox tools registered (OpenSandbox > RestrictedPython > simple exec)")
    return tools


def _create_execute_python(wf):
    @tool
    async def execute_python(
        code: str,
        timeout_seconds: int = 30,
    ) -> str:
        """
        Execute Python code in a secure sandbox. Suitable for data analysis,
        mathematical calculations, and data processing tasks.

        When OpenSandbox is configured, code runs in an isolated Docker container
        with full Python environment (including pip packages). Otherwise, falls back
        to a restricted in-process sandbox.

        Available modules (local fallback):
        - Math: math, statistics, decimal, fractions, random
        - Data: json, csv, collections, itertools, functools
        - Text: re, string, textwrap
        - Time: datetime
        - Data analysis (if installed): numpy, pandas, scipy

        Use cases:
        - Calculate portfolio metrics (Sharpe ratio, volatility, correlation, etc.)
        - Process and analyze market data
        - Perform statistical calculations
        - Data format conversion

        Args:
            code: Python code to execute. Use print() for output.
                  Variables defined at the end are automatically returned.
            timeout_seconds: Maximum execution time (seconds), default 30

        Returns:
            JSON with execution results, including output (stdout) and variables (variable values)

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

            # Basic security check (still useful even with OpenSandbox for early rejection)
            dangerous_patterns = [
                "os.system", "subprocess", "shutil", "__import__('os')",
                "open(", "exec(", "eval(", "compile(",
                "globals()", "locals()", "__class__",
                "__subclasses__", "__bases__",
            ]
            code_lower = code.lower()
            for pattern in dangerous_patterns:
                if pattern.lower() in code_lower:
                    return json.dumps({
                        "success": False,
                        "error": f"Security violation: '{pattern}' is not allowed in sandbox",
                    }, ensure_ascii=False)

            await wf.message_manager.send_message(
                f"🔧 Executing Python code ({len(code)} chars)...",
                "info",
            )

            result = await execute_code(
                code,
                timeout_seconds=timeout_seconds,
            )

            backend_name = result.get("backend", "unknown")
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
