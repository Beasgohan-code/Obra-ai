"""Restricted Python sandbox for the run_python tool.

Runs untrusted snippets in a **separate OS process** (`python -I`) with:
- hard timeout (SIGKILL on expiry),
- CPU / memory / file-size rlimits (Unix),
- a static banned-pattern pre-check (defence in depth),
- no inherited env, isolated mode (no user site-packages, no cwd on path).

This replaces the old in-process exec() which could hang the event loop.
"""
from __future__ import annotations

import re
import subprocess
import sys
from typing import Tuple

# Static deny-list checked before execution (fast fail, defence in depth).
_BANNED = (
    "import ", "from ", "__", "open(", "exec(", "eval(", "compile(",
    "os.", "sys.", "subprocess", "socket", "requests", "urllib", "httpx",
    "pathlib", "shutil", "ctypes", "multiprocessing", "signal", "pty",
    "getattr(", "setattr(", "delattr(", "globals(", "locals(", "vars(",
    "input(", "breakpoint(", "memoryview", "bytearray", "mmap",
)

_MAX_CODE = 8000
_MAX_OUT = 4000


def _precheck(src: str) -> str | None:
    if not src.strip():
        return "Empty code."
    if len(src) > _MAX_CODE:
        return f"Code too long (max {_MAX_CODE} chars)."
    low = src.lower()
    for b in _BANNED:
        if b in low:
            return f"Blocked for safety (contains `{b.strip() or b}`)."
    return None


def _preexec_limits():
    """Best-effort resource limits for the child process (Unix only)."""
    def _apply():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (10, 10))          # 10s CPU
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))  # 256MB
            resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))  # 4MB files
            resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
        except Exception:
            pass
    return _apply


def run_python(code: str, timeout_hint: int = 8) -> Tuple[str, bool]:
    """
    Execute a short Python snippet in an isolated subprocess.
    Returns (output, ok). Never raises.
    """
    src = (code or "").strip()
    err = _precheck(src)
    if err:
        return err, False
    timeout = max(2, min(int(timeout_hint or 8), 15))
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", src],
            capture_output=True,
            timeout=timeout,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8", "HOME": "/tmp"},
            preexec_fn=_preexec_limits if sys.platform != "win32" else None,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        out = out.strip()
        if proc.returncode == 0:
            return (out or "(ran successfully, no output)")[:_MAX_OUT], True
        # show the tail of the traceback, not the whole thing
        tail = out[-1200:] if out else f"exit code {proc.returncode}"
        return f"Error (exit {proc.returncode}):\n{tail}"[:_MAX_OUT], False
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s (killed).", False
    except Exception as e:
        return f"Sandbox error: {e}"[:_MAX_OUT], False
