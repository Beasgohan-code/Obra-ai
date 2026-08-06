"""Obra /start welcome — Bot API button styles (primary / success / danger)."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, List

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, FSInputFile

logger = logging.getLogger("obra.welcome")

# Official styles: primary=blue, success=green, danger=red
_STYLES = ("primary", "success", "danger")
_LETTERS = list("WELCOME")

_anim_tasks: dict = {}


def _btn(text: str, callback_data: str = None, url: str = None, style: str = None) -> InlineKeyboardButton:
    """Build button with style= when supported by aiogram; always attach via model_extra if needed."""
    kwargs = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    if style in _STYLES:
        kwargs["style"] = style
    try:
        return InlineKeyboardButton(**kwargs)
    except TypeError:
        # Older aiogram without style field — inject after construct
        kwargs.pop("style", None)
        b = InlineKeyboardButton(**kwargs)
        try:
            # pydantic v2
            b = b.model_copy(update={"style": style}) if style else b
        except Exception:
            if style:
                object.__setattr__(b, "style", style)
        return b


def welcome_letter_styles(shift: int = 0) -> List[str]:
    """Rotate primary/success/danger across W-E-L-C-O-M-E."""
    return [_STYLES[(i + shift) % 3] for i in range(7)]


def build_welcome_keyboard(shift: int = 0, channel_url: str = "") -> InlineKeyboardMarkup:
    styles = welcome_letter_styles(shift)
    welcome_row = [
        _btn(_LETTERS[i], callback_data=f"welcome:letter:{_LETTERS[i]}", style=styles[i])
        for i in range(7)
    ]
    row2 = [
        _btn("Help", callback_data="welcome:help", style="primary"),
        _btn("Skills", callback_data="welcome:skills", style="primary"),
    ]
    row3 = [
        _btn("Memory", callback_data="welcome:memory", style="success"),
        _btn("Language", callback_data="welcome:lang", style="success"),
    ]
    rows = [welcome_row, row2, row3]
    if channel_url:
        rows.append([_btn("Channel", url=channel_url, style="primary")])
    rows.append([_btn("Close", callback_data="welcome:close", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def welcome_caption(user_name: str) -> str:
    name = user_name or "friend"
    return (
        f"✨ <b>Welcome to Obra AI</b>\n\n"
        f"Hey <b>{name}</b> — I'm <b>obra</b>, your personal AI agent on Telegram.\n\n"
        f"Just chat. I can code, research, write files, schedule reminders, "
        f"remember context, and more.\n\n"
        f"Use the buttons below to get started!"
    )


async def _animate_welcome(bot: Bot, chat_id: int, message_id: int, channel_url: str, cycles: int = 60):
    """Every 3s rotate style= on WELCOME letters (blue/green/red cycle)."""
    key = (chat_id, message_id)
    try:
        for i in range(cycles):
            await asyncio.sleep(3)
            try:
                await bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=build_welcome_keyboard(i + 1, channel_url),
                )
            except Exception as e:
                logger.debug("welcome anim stop: %s", e)
                break
    finally:
        _anim_tasks.pop(key, None)


def start_welcome_animation(bot: Bot, chat_id: int, message_id: int, channel_url: str = ""):
    key = (chat_id, message_id)
    old = _anim_tasks.pop(key, None)
    if old and not old.done():
        old.cancel()
    _anim_tasks[key] = asyncio.create_task(
        _animate_welcome(bot, chat_id, message_id, channel_url)
    )


async def send_welcome(message: Message, bot: Bot, channel_url: str = "", photo_url: str = ""):
    name = message.from_user.full_name if message.from_user else "friend"
    caption = welcome_caption(name)
    kb = build_welcome_keyboard(0, channel_url)
    sent: Optional[Message] = None
    if photo_url:
        try:
            if photo_url.startswith("http"):
                sent = await message.answer_photo(
                    photo=photo_url, caption=caption, parse_mode="HTML", reply_markup=kb
                )
            else:
                sent = await message.answer_photo(
                    photo=FSInputFile(photo_url), caption=caption, parse_mode="HTML", reply_markup=kb
                )
        except Exception as e:
            logger.warning("welcome photo failed: %s", e)
    if sent is None:
        sent = await message.answer(caption, parse_mode="HTML", reply_markup=kb)
    start_welcome_animation(bot, sent.chat.id, sent.message_id, channel_url)
    return sent
