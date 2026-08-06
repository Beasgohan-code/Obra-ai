from __future__ import annotations
import asyncio, logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, FSInputFile

logger = logging.getLogger("obra.welcome")
_STYLES = ("primary", "success", "danger")
_LETTERS = list("WELCOME")
_anim = {}

def _btn(text, callback_data=None, url=None, style=None):
    kw = {"text": text}
    if callback_data: kw["callback_data"] = callback_data
    if url: kw["url"] = url
    if style in _STYLES: kw["style"] = style
    try:
        return InlineKeyboardButton(**kw)
    except TypeError:
        kw.pop("style", None)
        return InlineKeyboardButton(**kw)

def build_welcome_keyboard(shift: int = 0, channel_url: str = ""):
    styles = [_STYLES[(i+shift)%3] for i in range(7)]
    row1 = [_btn(_LETTERS[i], callback_data=f"welcome:letter:{_LETTERS[i]}", style=styles[i]) for i in range(7)]
    rows = [
        row1,
        [_btn("Help", "welcome:help", style="primary"), _btn("Skills", "welcome:skills", style="primary")],
        [_btn("Memory", "welcome:memory", style="success"), _btn("Language", "welcome:lang", style="success")],
    ]
    if channel_url:
        rows.append([_btn("Channel", url=channel_url, style="primary")])
    rows.append([_btn("Close", "welcome:close", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def welcome_caption(user_name: str) -> str:
    return (
        f"✨ <b>Welcome to Obra AI</b>\n\n"
        f"Hey <b>{user_name or 'friend'}</b> — I'm <b>obra</b>, your personal AI agent.\n\n"
        f"Just chat. Code, research, files, schedules, memory — all in Telegram.\n\n"
        f"Use the buttons below!"
    )

async def _animate(bot, chat_id, message_id, channel_url, cycles=60):
    key = (chat_id, message_id)
    try:
        for i in range(cycles):
            await asyncio.sleep(3)
            try:
                await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=build_welcome_keyboard(i+1, channel_url))
            except Exception:
                break
    finally:
        _anim.pop(key, None)

def start_welcome_animation(bot, chat_id, message_id, channel_url=""):
    key = (chat_id, message_id)
    old = _anim.pop(key, None)
    if old and not old.done():
        old.cancel()
    _anim[key] = asyncio.create_task(_animate(bot, chat_id, message_id, channel_url))

async def send_welcome(message: Message, bot: Bot, channel_url: str = "", photo_url: str = ""):
    name = message.from_user.full_name if message.from_user else "friend"
    caption = welcome_caption(name)
    kb = build_welcome_keyboard(0, channel_url)
    sent = None
    if photo_url:
        try:
            if photo_url.startswith("http"):
                sent = await message.answer_photo(photo=photo_url, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                sent = await message.answer_photo(photo=FSInputFile(photo_url), caption=caption, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("photo: %s", e)
    if sent is None:
        sent = await message.answer(caption, parse_mode="HTML", reply_markup=kb)
    start_welcome_animation(bot, sent.chat.id, sent.message_id, channel_url)
    return sent
