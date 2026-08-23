"""Restricted Python sandbox for short snippets."""

from __future__ import annotations
import io
import contextlib
import traceback
from typing import Tuple

# Very small builtin allowlist
_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "float": float, "int": int, "len": len,
    "list": list, "max": max, "min": min, "print": print, "range": range,
    "reversed": reversed, "round": round, "set": set, "sorted": sorted,
    "str": str, "sum": sum, "tuple": tuple, "zip": zip, "map": map, "filter": filter,
    "isinstance": isinstance, "type": type, "None": None, "True": True, "False": False,
}

_BANNED = (
    "import", "open(", "exec(", "eval(", "__", "os.", "sys.", "subprocess",
    "socket", "requests", "pathlib", "shutil", "ctypes", "multiprocessing",
)


def run_python(code: str, timeout_hint: int = 3) -> Tuple[str, bool]:
    """
    Execute a short Python snippet in a restricted globals dict.
    Not a perfect jail — good enough for demos; do not expose to untrusted public without stronger isolation.
    """
    src = (code or "").strip()
    if not src:
        return "Empty code.", False
    if len(src) > 8000:
        return "Code too long (max 8000 chars).", False
    low = src.lower()
    for b in _BANNED:
        if b in low:
            return f"Blocked for safety (contains `{b}`).", False

    stdout = io.StringIO()
    glb = {"__builtins__": _SAFE_BUILTINS}
    loc = {}
    try:
        with contextlib.redirect_stdout(stdout):
            exec(compile(src, "<obra_sandbox>", "exec"), glb, loc)
        out = stdout.getvalue()
        # show last assigned expr-ish values lightly
        extras = []
        for k, v in list(loc.items())[-5:]:
            if not k.startswith("_"):
                try:
                    extras.append(f"{k} = {repr(v)[:200]}")
                except Exception:
                    pass
        text = out
        if extras and not out:
            text = "\n".join(extras)
        return (text or "(ran successfully, no output)")[:4000], True
    except Exception:
        return traceback.format_exc()[-2500:], False
