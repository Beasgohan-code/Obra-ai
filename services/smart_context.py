"""Conversation intelligence — titles, follow-ups, topic memory."""
from __future__ import annotations

import re
from typing import Optional


def suggest_title(user_text: str) -> str:
    t = (user_text or "").strip()
    t = re.sub(r"\s+", " ", t)[:60]
    if not t:
        return "Chat"
    # strip filler
    t = re.sub(r"^(please|pls|can you|could you|help me)\s+", "", t, flags=re.I)
    return t[:48] + ("…" if len(t) > 48 else "")


def needs_tools(text: str) -> bool:
    low = (text or "").lower()
    keys = (
        "search", "weather", "news", "latest", "http", "url",
        "file", "zip", "code", "bot", "script", "calculate", "math",
        "remember", "schedule", "remind", "poll", "github", "wiki",
        "download", "create", "make", "build", "generate",
    )
    return any(k in low for k in keys)


def is_followup(text: str) -> bool:
    low = (text or "").strip().lower()
    if len(low) < 40 and any(
        low.startswith(p)
        for p in ("yes", "no", "ok", "more", "continue", "and", "also", "what about", "explain")
    ):
        return True
    return bool(re.match(r"^(that|this|it|those)\b", low))


def force_file_delivery(text: str) -> bool:
    low = (text or "").lower()
    return any(
        k in low
        for k in (
            "make", "build", "create", "write a", "full code", "as a file",
            "downloadable", "telegram bot", "discord bot", "script", "project",
            "downloader", "scraper", "complete code",
        )
    )
