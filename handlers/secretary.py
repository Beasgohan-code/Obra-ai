"""
Telegram Secretary Mode (Business Connection) — full handler.
BotFather → Mode Settings → Secretary Mode ON
User → Settings → Chat Automation → this bot
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.types import Message, BusinessConnection

from config.settings import settings
from services.db import db
from services.llm import chat_completion, detect_agent, AGENTS
from services.telegram_send import _api

logger = logging.getLogger("obra.secretary")
router = Router(name="secretary")

SECRETARY_SYSTEM = """You are obra acting as a personal secretary for the account owner.
Reply in the owner's voice: short, natural, helpful — not robotic.
Do not reveal you are a bot unless asked.
If the topic is sensitive (money, passwords, legal, private secrets), say the owner will reply soon.
Keep answers concise unless detail is needed.
"""


async def _biz_send(
    bot: Bot,
    *,
    business_connection_id: str,
    chat_id: int,
    text: str,
    reply_to: Optional[int] = None,
) -> bool:
    text = (text or "")[:4000]
    payload = {
        "business_connection_id": business_connection_id,
        "chat_id": chat_id,
        "text": text,
    }
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    try:
        await _api(bot, "sendMessage", payload)
        return True
    except Exception as e:
        logger.warning("biz send: %s", e)
        try:
            payload.pop("reply_parameters", None)
            await _api(bot, "sendMessage", payload)
            return True
        except Exception as e2:
            logger.warning("biz send retry: %s", e2)
            return False


async def _biz_typing(bot: Bot, business_connection_id: str, chat_id: int):
    try:
        await _api(
            bot,
            "sendChatAction",
            {
                "business_connection_id": business_connection_id,
                "chat_id": chat_id,
                "action": "typing",
            },
        )
    except Exception:
        pass


async def _biz_react(bot: Bot, business_connection_id: str, chat_id: int, message_id: int, emoji: str = "👀"):
    try:
        await _api(
            bot,
            "setMessageReaction",
            {
                "business_connection_id": business_connection_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": emoji}],
            },
        )
    except Exception:
        pass


@router.business_connection()
async def on_business_connection(event: BusinessConnection, bot: Bot):
    uid = event.user.id if event.user else 0
    cid = event.id
    is_enabled = bool(getattr(event, "is_enabled", True))
    can_reply = True
    rights = getattr(event, "rights", None)
    if rights is not None:
        can_reply = bool(getattr(rights, "can_reply", True))

    await db.save_business_connection(
        connection_id=cid,
        user_id=uid,
        is_enabled=is_enabled,
        can_reply=can_reply,
        raw={"user_chat_id": getattr(event, "user_chat_id", None)},
    )
    logger.info("Secretary %s user=%s conn=%s reply=%s", "ON" if is_enabled else "OFF", uid, cid, can_reply)

    try:
        if is_enabled:
            await bot.send_message(
                uid,
                "✅ <b>Secretary Mode connected</b>\n\n"
                "I'll help reply in chats you allowed.\n\n"
                "• Auto-reply is <b>ON</b>\n"
                "• Pause anytime: <code>/secretary off</code>\n"
                "• Resume: <code>/secretary on</code>\n"
                "• Status: <code>/secretary</code>\n\n"
                "Manage chats in Settings → Chat Automation.",
                parse_mode="HTML",
            )
        else:
            await bot.send_message(uid, "Secretary Mode disconnected.")
    except Exception:
        pass


async def _handle_biz_text(message: Message, bot: Bot, *, is_edit: bool = False):
    if not message or not message.from_user or message.from_user.is_bot:
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        return

    bc_id = getattr(message, "business_connection_id", None)
    if not bc_id:
        return

    conn = await db.get_business_connection(bc_id)
    if conn and not conn.get("is_enabled"):
        return
    if conn and conn.get("can_reply") is False:
        return

    owner_id = (conn or {}).get("user_id") or 0

    # Owner can pause auto-reply via user_settings
    if owner_id:
        us = await db.get_user_settings(owner_id)
        if us.get("secretary_paused"):
            logger.info("secretary paused for owner %s", owner_id)
            return
        ok, _ = await db.check_rate_limit(owner_id)
        if not ok:
            return

    chat_id = message.chat.id
    await _biz_typing(bot, bc_id, chat_id)
    if getattr(settings, "AUTO_REACT", True):
        await _biz_react(bot, bc_id, chat_id, message.message_id, "👀")

    agent = detect_agent(text)
    system = SECRETARY_SYSTEM
    if owner_id:
        mem = await db.get_user_memory(owner_id)
        if mem:
            system += f"\n\nOwner notes: {mem.get('notes') or ''}\nPrefs: {mem.get('preferences') or {}}"

    history = [{"role": "user", "content": text}]
    try:
        prev = await db.get_history(chat_id, limit=8)
        if prev:
            history = prev[-8:] + ([{"role": "user", "content": f"[edited] {text}"}] if is_edit else history)
    except Exception:
        pass

    try:
        result = await chat_completion(
            messages=history,
            system=system,
            tools=None,
            temperature=0.55,
            max_tokens=min(1500, getattr(settings, "MAX_TOKENS_MEDIUM", 4096) or 4096),
        )
        reply = (result.get("content") or "").strip() or "Got it — the owner will follow up soon."
    except Exception as e:
        logger.warning("secretary LLM: %s", e)
        reply = "Thanks — the owner will reply soon."

    ok = await _biz_send(
        bot,
        business_connection_id=bc_id,
        chat_id=chat_id,
        text=reply,
        reply_to=None if is_edit else message.message_id,
    )
    if ok:
        try:
            await db.add_message(chat_id, "user", text)
            await db.add_message(chat_id, "assistant", reply)
            if owner_id:
                await db.log_event(owner_id, chat_id, "secretary_reply", {"edit": is_edit})
        except Exception:
            pass
    elif owner_id:
        try:
            await bot.send_message(
                owner_id,
                f"⚠️ Secretary couldn't send a reply (chat maybe inactive >24h).\n"
                f"From chat <code>{chat_id}</code>:\n{text[:300]}",
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.business_message()
async def on_business_message(message: Message, bot: Bot):
    await _handle_biz_text(message, bot, is_edit=False)


@router.edited_business_message()
async def on_edited_business_message(message: Message, bot: Bot):
    await _handle_biz_text(message, bot, is_edit=True)


@router.message(F.text.regexp(r"(?i)^/start\s+bizChat"))
async def on_start_biz(message: Message, bot: Bot):
    parts = (message.text or "").split(maxsplit=1)
    args = parts[1].strip() if len(parts) > 1 else ""
    chat_ref = args[7:] if args.lower().startswith("bizchat") else args
    await message.answer(
        f"🔐 <b>Secretary</b> — chat <code>{chat_ref}</code>\n\n"
        f"<code>/secretary</code> status · "
        f"<code>/secretary off</code> pause · "
        f"<code>/secretary on</code> resume",
        parse_mode="HTML",
    )
