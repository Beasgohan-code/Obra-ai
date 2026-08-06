from __future__ import annotations
import io, contextlib, traceback
from typing import Tuple
_SAFE = {"abs":abs,"all":all,"any":any,"bool":bool,"dict":dict,"enumerate":enumerate,"float":float,"int":int,"len":len,"list":list,"max":max,"min":min,"print":print,"range":range,"round":round,"set":set,"sorted":sorted,"str":str,"sum":sum,"tuple":tuple,"zip":zip}
_BANNED = ("import","open(","exec(","eval(","__","os.","sys.","subprocess","socket")

def run_python(code: str) -> Tuple[str, bool]:
    src = (code or "").strip()
    if not src or len(src) > 8000:
        return "Empty or too long", False
    low = src.lower()
    for b in _BANNED:
        if b in low:
            return f"Blocked ({b})", False
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(src, "<obra>", "exec"), {"__builtins__": _SAFE}, {})
        return (out.getvalue() or "(ok, no output)")[:4000], True
    except Exception:
        return traceback.format_exc()[-2500:], False
