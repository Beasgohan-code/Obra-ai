"""Telegram Mini App bridge — handles web_app_data messages from the Mini App.

The Mini App calls tg.sendData(JSON.stringify({prompt, agent})) → Telegram
delivers a message with web_app_data → we run it through the normal pipeline.
"""
from __future__ import annotations

import json
import logging

from aiogram import Router, Bot, F
from aiogram.types import Message

from config.settings import settings
from services.db import db

logger = logging.getLogger("obra.webapp")
router = Router(name="webapp")


@router.message(F.web_app_data)
async def on_web_app_data(message: Message, bot: Bot):
    user = message.from_user
    if not user or user.is_bot:
        return
    raw = message.web_app_data.data if message.web_app_data else ""
    prompt = raw
    agent = None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            prompt = str(data.get("prompt") or data.get("text") or raw)
            agent = data.get("agent") or None
    except Exception:
        pass
    prompt = (prompt or "").strip()
    if not prompt:
        return
    if len(prompt) > int(getattr(settings, "MAX_MESSAGE_CHARS", 20000) or 20000):
        await message.answer("📄 Too long — send as a file in chat.")
        return
    if await db.is_blocked(user.id):
        return
    if user.id not in settings.admin_list:
        ok, _ = await db.check_rate_limit(user.id)
        if not ok:
            await message.answer("⏳ Slow down a bit — rate limit.")
            return
        ok_q, reason = await db.check_quotas(user.id)
        if not ok_q:
            await message.answer(f"🚫 {reason}")
            return

    if agent in ("coder", "researcher", "writer", "solver", "summarizer", "terminal"):
        prompt = f"use {agent}: {prompt}"

    await db.log_event(user.id, message.chat.id, "miniapp", {"len": len(prompt)})
    from handlers.chat import process_user_text
    try:
        await process_user_text(message, bot, prompt)
    except Exception as e:
        logger.warning("webapp pipeline: %s", e)
        await message.answer(f"⚠️ <code>{str(e)[:200]}</code>", parse_mode="HTML")
