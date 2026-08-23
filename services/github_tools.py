"""GitHub tools via token (GITHUB_TOKEN or per-user later)."""

from __future__ import annotations
import aiohttp
from typing import Optional
from config.settings import settings


def _token() -> str:
    return getattr(settings, "GITHUB_TOKEN", "") or ""


async def github_me() -> str:
    tok = _token()
    if not tok:
        return "GITHUB_TOKEN not set in .env"
    async with aiohttp.ClientSession() as s:
        async with s.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
        ) as r:
            data = await r.json()
            if r.status >= 400:
                return f"GitHub error: {data}"
            return f"GitHub user: {data.get('login')} — {data.get('html_url')}"


async def github_list_repos(limit: int = 10) -> str:
    tok = _token()
    if not tok:
        return "GITHUB_TOKEN not set"
    async with aiohttp.ClientSession() as s:
        async with s.get(
            "https://api.github.com/user/repos?per_page=" + str(min(limit, 20)) + "&&sort=updated",
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
        ) as r:
            data = await r.json()
            if r.status >= 400:
                return f"GitHub error: {data}"
            lines = [f"- {x.get('full_name')} ★{x.get('stargazers_count', 0)}" for x in data]
            return "\n".join(lines) or "No repos."


async def github_read_file(repo: str, path: str, ref: str = "main") -> str:
    """repo like owner/name"""
    tok = _token()
    if not tok:
        return "GITHUB_TOKEN not set"
    import base64
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
    async with aiohttp.ClientSession() as s:
        async with s.get(
            url,
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
        ) as r:
            data = await r.json()
            if r.status >= 400:
                return f"GitHub error: {data}"
            content = data.get("content") or ""
            if data.get("encoding") == "base64":
                try:
                    raw = base64.b64decode(content).decode("utf-8", errors="replace")
                except Exception as e:
                    return f"Decode error: {e}"
            else:
                raw = str(content)
            return raw[:12000]


async def github_create_issue(repo: str, title: str, body: str = "") -> str:
    tok = _token()
    if not tok:
        return "GITHUB_TOKEN not set"
    url = f"https://api.github.com/repos/{repo}/issues"
    async with aiohttp.ClientSession() as s:
        async with s.post(
            url,
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
            json={"title": title, "body": body or ""},
        ) as r:
            data = await r.json()
            if r.status >= 400:
                return f"GitHub error: {data}"
            return f"Issue created: {data.get('html_url')}"
