"""
Rich Messages for Telegram Bot API 10.1+ (headings, tables, thinking, 32k).

Order:
1) Direct HTTPS sendRichMessage / sendRichMessageDraft (most reliable)
2) aiogram typed helpers if present
3) HTML sendMessage chunks
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from config.settings import settings
from services.rich_format import md_to_rich_html

logger = logging.getLogger("obra.rich")


def _clip_rich(text: str, limit: int = 32000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n\n…(truncated)"


async def _api(bot: Bot, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Direct call to api.telegram.org — bypasses aiogram method gaps."""
    url = f"https://api.telegram.org/bot{bot.token}/{method}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            data = await resp.json(content_type=None)
            if not data.get("ok"):
                raise RuntimeError(data.get("description") or str(data))
            return data.get("result") or data


async def send_thinking_draft(bot: Bot, chat_id: int, draft_id: int, stage: str = "Thinking…") -> bool:
    if not getattr(settings, "USE_RICH_MESSAGES", True):
        return False
    stage = (stage or "Thinking…")[:200]
    # Direct API first
    for rich in (
        {"html": f"<tg-thinking>{stage}</tg-thinking>"},
        {"markdown": f"*{stage}*"},
    ):
        try:
            await _api(
                bot,
                "sendRichMessageDraft",
                {
                    "chat_id": chat_id,
                    "draft_id": draft_id,
                    "rich_message": rich,
                },
            )
            return True
        except Exception as e:
            logger.debug("draft %s: %s", list(rich.keys()), e)
    # typed fallback
    try:
        from aiogram.types import InputRichMessage
        await bot.send_rich_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            rich_message=InputRichMessage(html=f"<tg-thinking>{stage}</tg-thinking>"),
        )
        return True
    except Exception:
        return False


async def send_rich(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    reply_to: Optional[int] = None,
    prefer_html: bool = True,
) -> bool:
    """Send final reply as Rich Message (up to 32k)."""
    text = _clip_rich(text or "")
    if not text.strip():
        text = "…"
    if not getattr(settings, "USE_RICH_MESSAGES", True):
        await _plain_chunks(bot, chat_id, text, reply_to)
        return False

    # Always prepare HTML with headings/tables for max polish
    try:
        html = md_to_rich_html(text) if not text.lstrip().startswith("<") else text
    except Exception:
        html = _md_to_simple_html(text)

    attempts = [
        {"html": html},
        {"markdown": text},
    ]

    for rich in attempts:
        body: Dict[str, Any] = {"chat_id": chat_id, "rich_message": rich}
        if reply_to:
            body["reply_parameters"] = {"message_id": reply_to}
        try:
            await _api(bot, "sendRichMessage", body)
            logger.info("RICH ok chat=%s via %s", chat_id, list(rich.keys())[0])
            return True
        except Exception as e:
            logger.warning("sendRichMessage %s failed: %s", list(rich.keys())[0], e)

    # typed aiogram
    try:
        from aiogram.types import InputRichMessage, ReplyParameters
        rm = InputRichMessage(html=html)
        kwargs: Dict[str, Any] = {"chat_id": chat_id, "rich_message": rm}
        if reply_to:
            try:
                kwargs["reply_parameters"] = ReplyParameters(message_id=reply_to)
            except Exception:
                kwargs["reply_to_message_id"] = reply_to
        await bot.send_rich_message(**kwargs)
        logger.info("RICH ok typed chat=%s", chat_id)
        return True
    except Exception as e:
        logger.debug("typed rich failed: %s", e)

    await _plain_chunks(bot, chat_id, html if "<" in html else text, reply_to)
    logger.warning("RICH_FALLBACK plain chat=%s", chat_id)
    return False


async def _plain_chunks(bot: Bot, chat_id: int, text: str, reply_to: Optional[int]):
    mode = ParseMode.HTML if "<" in (text or "")[:300] else None
    step = 3500 if mode else 4000
    for i in range(0, len(text), step):
        chunk = text[i : i + step]
        try:
            await bot.send_message(
                chat_id,
                chunk,
                reply_to_message_id=reply_to if i == 0 else None,
                parse_mode=mode,
            )
        except TelegramAPIError:
            await bot.send_message(
                chat_id,
                chunk,
                reply_to_message_id=reply_to if i == 0 else None,
            )


def _md_to_simple_html(text: str) -> str:
    import html
    import re
    t = html.escape(text)
    t = re.sub(r"^###### (.+)$", r"<h6>\1</h6>", t, flags=re.M)
    t = re.sub(r"^##### (.+)$", r"<h5>\1</h5>", t, flags=re.M)
    t = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", t, flags=re.M)
    t = re.sub(r"^### (.+)$", r"<h3>\1</h3>", t, flags=re.M)
    t = re.sub(r"^## (.+)$", r"<h2>\1</h2>", t, flags=re.M)
    t = re.sub(r"^# (.+)$", r"<h1>\1</h1>", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"```(\w*)\n([\s\S]*?)```", r"<pre><code>\2</code></pre>", t)
    t = t.replace("\n", "<br/>")
    return t


async def send_ephemeral(bot: Bot, chat_id: int, user_id: int, text: str) -> bool:
    text = _clip_rich(text, 4000)
    try:
        await _api(
            bot,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "receiver_user_id": user_id,
                "parse_mode": "HTML",
            },
        )
        return True
    except Exception:
        pass
    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
        return True
    except Exception:
        return False


async def react(bot: Bot, chat_id: int, message_id: int, emoji: str = "👍") -> bool:
    try:
        await bot.set_message_reaction(
            chat_id, message_id, reaction=[{"type": "emoji", "emoji": emoji}]
        )
        return True
    except Exception:
        return False
