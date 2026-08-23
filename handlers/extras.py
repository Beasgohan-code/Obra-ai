"""Small delightful extras — mood, ping, about, status."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import Command

from config.settings import settings
from services.db import db

router = Router(name="extras")
_START = time.time()


@router.message(Command("ping"))
async def cmd_ping(message: Message):
    t0 = time.time()
    m = await message.answer("🏓 pong")
    ms = int((time.time() - t0) * 1000)
    try:
        await m.edit_text(f"🏓 pong — `{ms}ms`", parse_mode="Markdown")
    except Exception:
        pass


@router.message(Command("about"))
async def cmd_about(message: Message):
    up = int(time.time() - _START)
    h, rem = divmod(up, 3600)
    m, s = divmod(rem, 60)
    await message.answer(
        "✨ <b>obra</b> — your personal AI agent on Telegram\n\n"
        "• Chat naturally — tools, code, files, schedules\n"
        "• Rich Messages + thinking drafts\n"
        "• Secretary Mode for inbox auto-replies\n"
        "• Multi-language · memory · multi-agent\n\n"
        f"Uptime: <code>{h}h {m}m {s}s</code>\n"
        "Type /help for commands.",
        parse_mode="HTML",
    )


@router.message(Command("status"))
async def cmd_status(message: Message, bot: Bot):
    me = await bot.get_me()
    up = int(time.time() - _START)
    uid = message.from_user.id if message.from_user else 0
    us = await db.get_user_settings(uid) if uid else {}
    await message.answer(
        f"<b>Status</b>\n"
        f"Bot: @{me.username}\n"
        f"Uptime: <code>{up}s</code>\n"
        f"Rich: <code>{getattr(settings,'USE_RICH_MESSAGES', True)}</code>\n"
        f"Scheduler: <code>{getattr(settings,'ENABLE_SCHEDULER', True)}</code>\n"
        f"Secretary paused: <code>{bool(us.get('secretary_paused'))}</code>\n"
        f"UTC: <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}</code>",
        parse_mode="HTML",
    )
