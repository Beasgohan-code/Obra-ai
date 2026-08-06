"""
Reliable Rich Messages via direct Bot API HTTP calls.
Works even when aiogram typed methods are missing/broken.
"""
from __future__ import annotations

import logging
from typing import Optional, Any, Dict

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from config.settings import settings

logger = logging.getLogger("obra.rich")


def _clip(text: str, limit: int = 32000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n\n…(truncated)"


async def _api(bot: Bot, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST https://api.telegram.org/bot<token>/<method>"""
    token = bot.token
    url = f"https://api.telegram.org/bot{token}/{method}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            data = await resp.json()
            if not data.get("ok"):
                desc = data.get("description") or data
                raise RuntimeError(f"Telegram {method} failed: {desc}")
            return data.get("result") or data


async def send_thinking_draft(bot: Bot, chat_id: int, draft_id: int, stage: str = "Thinking…") -> bool:
    if not getattr(settings, "USE_RICH_MESSAGES", True):
        return False
    try:
        await _api(
            bot,
            "sendRichMessageDraft",
            {
                "chat_id": chat_id,
                "draft_id": draft_id,
                "rich_message": {"html": f"<tg-thinking>{stage}</tg-thinking>"},
            },
        )
        logger.info("thinking draft ok chat=%s", chat_id)
        return True
    except Exception as e:
        logger.warning("thinking draft failed: %s", e)
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
    Always try sendRichMessage first (markdown, then html).
    Falls back to chunked sendMessage only if API rejects rich.
    """
    text = _clip(text or "")
    use_rich = getattr(settings, "USE_RICH_MESSAGES", True)

    if use_rich:
        bodies = [
            {"markdown": text},
            {"html": text} if (prefer_html or "<" in text[:300]) else None,
        ]
        # Prefer markdown for ## tables lists
        for rich in [b for b in bodies if b]:
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "rich_message": rich,
            }
            if reply_to:
                payload["reply_parameters"] = {"message_id": reply_to}
            try:
                await _api(bot, "sendRichMessage", payload)
                logger.info("sendRichMessage OK chat=%s keys=%s len=%s", chat_id, list(rich.keys()), len(text))
                return True
            except Exception as e:
                logger.warning("sendRichMessage failed (%s): %s", list(rich.keys()), e)

        # Try typed aiogram as secondary
        try:
            from aiogram.types import InputRichMessage, ReplyParameters
            rm = InputRichMessage(markdown=text)
            kwargs = {"chat_id": chat_id, "rich_message": rm}
            if reply_to:
                try:
                    kwargs["reply_parameters"] = ReplyParameters(message_id=reply_to)
                except Exception:
                    kwargs["reply_to_message_id"] = reply_to
            await bot.send_rich_message(**kwargs)
            logger.info("typed send_rich_message OK chat=%s", chat_id)
            return True
        except Exception as e:
            logger.warning("typed send_rich_message failed: %s", e)

    await _plain_chunks(bot, chat_id, text, reply_to)
    logger.warning("RICH_FALLBACK plain chat=%s len=%s", chat_id, len(text))
    return False


async def _plain_chunks(bot: Bot, chat_id: int, text: str, reply_to: Optional[int]):
    step = 4000
    for i in range(0, max(1, len(text)), step):
        chunk = text[i : i + step]
        try:
            await bot.send_message(
                chat_id,
                chunk,
                reply_to_message_id=reply_to if i == 0 else None,
            )
        except TelegramAPIError:
            await bot.send_message(chat_id, chunk)


async def send_ephemeral(bot: Bot, chat_id: int, user_id: int, text: str) -> bool:
    text = _clip(text, 4000)
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
