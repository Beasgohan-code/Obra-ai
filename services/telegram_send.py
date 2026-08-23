"""
Reliable Rich Message sender for Bot API 10.1+.

Why normal messages appeared before:
- aiogram typed helpers can fail / be missing on older wheels
- exceptions were swallowed → always fell back to sendMessage (4096)

This module tries, in order:
1) bot.send_rich_message / send_rich_message_draft (aiogram 3.29+)
2) raw HTTP session call to sendRichMessage / sendRichMessageDraft
3) HTML send_message chunks (best-effort structure)
"""

from __future__ import annotations

import logging
from typing import Optional

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


async def _raw_api(bot: Bot, method: str, **payload) -> dict:
    """Call Bot API method via aiogram session (works even without typed methods)."""
    session = bot.session
    # aiogram 3: session.make_request(bot, method, data)
    if hasattr(session, "make_request"):
        return await session.make_request(bot, method, payload)
    if hasattr(session, "request"):
        return await session.request(method=method, data=payload)
    # last resort: bot.__call__ style
    return await bot(method, **payload)  # may not work on all versions


async def send_thinking_draft(bot: Bot, chat_id: int, draft_id: int, stage: str = "Thinking…") -> bool:
    if not settings.USE_RICH_MESSAGES:
        return False
    # Prefer HTML thinking tag (Bot API supports <tg-thinking> in drafts)
    rich = {"html": f"<tg-thinking>{stage}</tg-thinking>"}
    # 1) typed
    try:
        from aiogram.types import InputRichMessage
        await bot.send_rich_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            rich_message=InputRichMessage(html=f"<tg-thinking>{stage}</tg-thinking>"),
        )
        return True
    except Exception as e:
        logger.debug("typed draft failed: %s", e)
    # 2) raw
    try:
        await _raw_api(
            bot,
            "sendRichMessageDraft",
            chat_id=chat_id,
            draft_id=draft_id,
            rich_message=rich,
        )
        return True
    except Exception as e:
        logger.debug("raw draft failed: %s", e)
    return False


async def send_rich(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    reply_to: Optional[int] = None,
    prefer_html: bool = False,
) -> bool:
    """
    Send final reply as Rich Message (up to 32k).
    Returns True if rich path succeeded.
    """
    text = _clip_rich(text)
    if not prefer_html and ("<details>" in text or "<tg-" in text or "<h1>" in text or "<table>" in text):
        prefer_html = True
    if not settings.USE_RICH_MESSAGES:
        await _plain_chunks(bot, chat_id, text, reply_to)
        return False

    payload_md = {"markdown": text}
    payload_html = None
    if prefer_html or text.lstrip().startswith("<") or "<details>" in text:
        payload_html = {"html": text if text.lstrip().startswith("<") else md_to_rich_html(text)}
    else:
        # always try a converted html as secondary path
        try:
            payload_html = {"html": md_to_rich_html(text)}
        except Exception:
            payload_html = None

    # 1) typed aiogram
    try:
        from aiogram.types import InputRichMessage
        from aiogram.types import ReplyParameters

        rm = InputRichMessage(html=text) if payload_html else InputRichMessage(markdown=text)
        kwargs = {"chat_id": chat_id, "rich_message": rm}
        if reply_to:
            try:
                kwargs["reply_parameters"] = ReplyParameters(message_id=reply_to)
            except Exception:
                kwargs["reply_to_message_id"] = reply_to
        await bot.send_rich_message(**kwargs)
        logger.info("rich send via typed aiogram ok chat=%s", chat_id)
        return True
    except Exception as e:
        logger.debug("typed send_rich_message failed: %s", e)

    # 2) raw API
    for rich in ([payload_html, payload_md] if payload_html else [payload_md, {"html": _md_to_simple_html(text)}]):
        if not rich:
            continue
        try:
            body = {
                "chat_id": chat_id,
                "rich_message": rich,
            }
            if reply_to:
                body["reply_parameters"] = {"message_id": reply_to}
            await _raw_api(bot, "sendRichMessage", **body)
            logger.info("rich send via raw API ok chat=%s keys=%s", chat_id, list(rich.keys()))
            return True
        except Exception as e:
            logger.warning("raw sendRichMessage failed (%s): %s", list(rich.keys()), e)

    # 3) plain fallback
    await _plain_chunks(bot, chat_id, text, reply_to)
    logger.warning("RICH_FALLBACK plain sendMessage chat=%s — install aiogram>=3.30", chat_id)
    return False


async def _plain_chunks(bot: Bot, chat_id: int, text: str, reply_to: Optional[int]):
    # Prefer HTML if looks like tags; else Markdown-ish as plain
    mode = ParseMode.HTML if "<" in text[:200] and ">" in text[:200] else None
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
    """Very light markdown → HTML for rich fallback."""
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
    """
    Bot API 10.2 — message in a group visible only to user_id + bot.
    Falls back to normal DM if ephemeral not supported.
    """
    text = _clip_rich(text, 4000)
    try:
        await _raw_api(
            bot,
            "sendMessage",
            chat_id=chat_id,
            text=text,
            receiver_user_id=user_id,
            parse_mode="HTML",
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
