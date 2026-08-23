"""Telegram Secretary Mode — reply on behalf of the user in allowed chats."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Router, Bot, F
from aiogram.types import Message, BusinessConnection

from config.settings import settings
from services.db import db
from services.llm import chat_completion, detect_agent, AGENTS
from services.persona import polish_system

logger = logging.getLogger("obra.secretary")
router = Router(name="secretary")


async def _api(bot: Bot, method: str, payload: dict):
    token = bot.token
    url = f"https://api.telegram.org/bot{token}/{method}"
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description") or data)
            return data.get("result") or data


async def _biz_send(bot, business_connection_id: str, chat_id: int, text: str, reply_to: Optional[int] = None) -> bool:
    payload = {
        "business_connection_id": business_connection_id,
        "chat_id": chat_id,
        "text": (text or "")[:4000],
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


async def _biz_typing(bot, business_connection_id: str, chat_id: int):
    try:
        await _api(bot, "sendChatAction", {
            "business_connection_id": business_connection_id,
            "chat_id": chat_id,
            "action": "typing",
        })
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
    try:
        await db.save_business_connection(cid, uid, is_enabled, can_reply, {})
    except Exception as e:
        logger.warning("save biz conn: %s", e)
    try:
        if is_enabled:
            await bot.send_message(
                uid,
                "✅ <b>Secretary Mode connected</b>\n\n"
                "Auto-reply is ON.\n"
                "<code>/secretary off</code> to pause · <code>/secretary on</code> to resume",
                parse_mode="HTML",
            )
        else:
            await bot.send_message(uid, "Secretary Mode disconnected.")
    except Exception:
        pass


async def _handle(message: Message, bot: Bot, is_edit: bool = False):
    if not message or not message.from_user or message.from_user.is_bot:
        return
    text = (message.text or message.caption or "").strip()
    if not text:
        return
    bc_id = getattr(message, "business_connection_id", None)
    if not bc_id:
        return
    conn = None
    try:
        conn = await db.get_business_connection(bc_id)
    except Exception:
        pass
    if conn and not conn.get("is_enabled"):
        return
    if conn and conn.get("can_reply") is False:
        return
    owner_id = (conn or {}).get("user_id") or 0
    if owner_id:
        try:
            if await db.is_secretary_paused(owner_id):
                return
        except Exception:
            pass
    chat_id = message.chat.id
    await _biz_typing(bot, bc_id, chat_id)
    system = polish_system(AGENTS.get("default", ""), mode="secretary")
    if owner_id:
        try:
            mem = await db.get_user_memory(owner_id)
            if mem:
                system += f"\nOwner notes: {mem.get('notes') or ''}"
        except Exception:
            pass
    history = [{"role": "user", "content": text}]
    try:
        prev = await db.get_history(chat_id, limit=6)
        if prev:
            history = prev[-6:] + history
    except Exception:
        pass
    try:
        result = await chat_completion(
            messages=history, system=system, tools=None,
            temperature=0.55, max_tokens=1200,
        )
        reply = (result.get("content") or "").strip() or "Got it — the owner will follow up soon."
    except Exception as e:
        logger.warning("secretary LLM: %s", e)
        reply = "Thanks — the owner will reply soon."
    ok = await _biz_send(bot, bc_id, chat_id, reply, None if is_edit else message.message_id)
    if ok:
        try:
            await db.add_message(chat_id, "user", text)
            await db.add_message(chat_id, "assistant", reply)
        except Exception:
            pass
    elif owner_id:
        try:
            await bot.send_message(
                owner_id,
                f"⚠️ Secretary couldn't reply (maybe chat inactive >24h).\n{text[:250]}",
            )
        except Exception:
            pass


@router.business_message()
async def on_business_message(message: Message, bot: Bot):
    await _handle(message, bot, False)


@router.edited_business_message()
async def on_edited_business_message(message: Message, bot: Bot):
    await _handle(message, bot, True)


@router.message(F.text.regexp(r"(?i)^/start\s+bizChat"))
async def on_start_biz(message: Message, bot: Bot):
    parts = (message.text or "").split(maxsplit=1)
    args = parts[1].strip() if len(parts) > 1 else ""
    chat_ref = args[7:] if args.lower().startswith("bizchat") else args
    await message.answer(
        f"🔐 <b>Secretary</b> — chat <code>{chat_ref}</code>\n"
        f"<code>/secretary</code> · on · off",
        parse_mode="HTML",
    )
