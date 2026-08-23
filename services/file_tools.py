
"""Generate text/code/html/zip files for Telegram document sends."""

from __future__ import annotations
import io
import zipfile
from typing import Optional, Tuple, List, Dict, Any


ALLOWED_EXT = {
    "txt", "md", "py", "js", "ts", "html", "css", "json", "csv",
    "xml", "yaml", "yml", "toml", "sh", "sql", "rs", "go", "java",
    "c", "cpp", "h", "hpp", "env", "ini", "log",
}


def _safe_name(name: str, default_ext: str = "txt") -> str:
    name = (name or "file").strip().replace("\\", "/").split("/")[-1]
    name = "".join(c for c in name if c.isalnum() or c in "._- ")
    name = name.strip(" .") or "file"
    if "." not in name:
        name = f"{name}.{default_ext}"
    ext = name.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT and ext != "zip":
        name = name.rsplit(".", 1)[0] + ".txt"
    return name[:80]


def make_text_file(filename: str, content: str) -> Tuple[str, bytes]:
    fn = _safe_name(filename, "txt")
    data = (content or "").encode("utf-8")
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("File too large (max 15MB)")
    return fn, data


def make_zip(archive_name: str, files: List[Dict[str, str]]) -> Tuple[str, bytes]:
    """
    files: [{"filename": "a.py", "content": "..."}, ...]
    """
    an = _safe_name(archive_name if archive_name.endswith(".zip") else archive_name + ".zip", "zip")
    if not an.endswith(".zip"):
        an += ".zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in files or []:
            fn = _safe_name(item.get("filename") or "file.txt")
            content = item.get("content") or ""
            zf.writestr(fn, content.encode("utf-8"))
    data = buf.getvalue()
    if len(data) > 15 * 1024 * 1024:
        raise ValueError("Zip too large (max 15MB)")
    return an, data


async def execute_create_file(filename: str, content: str) -> Tuple[str, Optional[bytes], Optional[Tuple[str, bytes]]]:
    try:
        fn, data = make_text_file(filename, content)
        return f"Created file `{fn}` ({len(data)} bytes). Sending as document.", None, (fn, data)
    except Exception as e:
        return f"create_file failed: {e}", None, None


async def execute_create_zip(archive_name: str, files: list) -> Tuple[str, Optional[bytes], Optional[Tuple[str, bytes]]]:
    try:
        if not files:
            return "create_zip needs at least one file entry.", None, None
        fn, data = make_zip(archive_name or "archive.zip", files)
        return f"Created zip `{fn}` with {len(files)} file(s), {len(data)} bytes.", None, (fn, data)
    except Exception as e:
        return f"create_zip failed: {e}", None, None
