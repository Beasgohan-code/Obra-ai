"""Only /start and /help — everything else is natural language + agents."""
from aiogram import Router, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.filters import Command

from services.db import db
from config.settings import settings

router = Router()


def _btn(text: str, data: str, style: str = "primary"):
    try:
        return InlineKeyboardButton(text=text, callback_data=data, style=style)
    except TypeError:
        return InlineKeyboardButton(text=text, callback_data=data)


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    from services.welcome import send_welcome
    channel = getattr(settings, "CHANNEL_URL", "") or ""
    photo = getattr(settings, "WELCOME_PHOTO_URL", "") or ""
    await send_welcome(message, bot, channel_url=channel, photo_url=photo)
    # Soft status line
    try:
        uid = message.from_user.id
        prem = await db.is_premium(uid)
        used_d, lim_d = await db.usage_today(uid)
        plan = "⭐ Premium" if prem else "Free"
        await message.answer(
            f"<b>{plan}</b> · today {used_d}/{lim_d}\n"
            f"Just chat — no commands needed.\n"
            f"Say <i>upgrade</i> for Stars premium.",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "<b>obra</b> — AI agent\n\n"
        "Just talk. Agents handle the rest.\n\n"
        "<b>Examples</b>\n"
        "• make a full telegram bot and send zip\n"
        "• remember my name is Alex\n"
        "• every day at 9am remind me water\n"
        "• run: print(2+2)\n"
        "• reply to a .md file: make this a skill\n"
        "• upgrade / buy premium\n\n"
        "Only commands: /start · /help"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        _btn("⭐ Premium", "premium:show", "primary"),
        _btn("Usage", "premium:usage", "success"),
    ]])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)
