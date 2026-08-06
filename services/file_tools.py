from __future__ import annotations
import io, zipfile
from typing import Optional, Tuple, List, Dict

ALLOWED = {"txt","md","py","js","ts","html","css","json","csv","xml","yaml","yml","sh","sql","env","log"}

def _safe(name: str, default="txt") -> str:
    name = (name or "file").replace("\\","/").split("/")[-1]
    name = "".join(c for c in name if c.isalnum() or c in "._- ") or "file"
    if "." not in name:
        name += f".{default}"
    ext = name.rsplit(".",1)[-1].lower()
    if ext not in ALLOWED and ext != "zip":
        name = name.rsplit(".",1)[0] + ".txt"
    return name[:80]

async def execute_create_file(filename: str, content: str):
    fn = _safe(filename)
    data = (content or "").encode("utf-8")
    if len(data) > 20*1024*1024:
        return "Too large", None, None
    return f"Created `{fn}` ({len(data)} bytes).", None, (fn, data)

async def execute_create_zip(archive_name: str, files: list):
    an = _safe(archive_name if (archive_name or "").endswith(".zip") else (archive_name or "archive")+".zip", "zip")
    if not an.endswith(".zip"):
        an += ".zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in files or []:
            zf.writestr(_safe(item.get("filename") or "file.txt"), (item.get("content") or "").encode("utf-8"))
    data = buf.getvalue()
    return f"Created zip `{an}` ({len(data)} bytes).", None, (an, data)
