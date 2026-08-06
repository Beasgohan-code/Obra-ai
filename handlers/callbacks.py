from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from services.db import db
from config.settings import settings

router = Router()

def _b(text, data, style=None):
    kw = {"text": text, "callback_data": data}
    if style: kw["style"] = style
    try:
        return InlineKeyboardButton(**kw)
    except TypeError:
        kw.pop("style", None)
        return InlineKeyboardButton(**kw)

@router.callback_query(F.data.startswith("welcome:"))
async def on_welcome(cq: CallbackQuery):
    data = cq.data or ""
    action = data.split(":",1)[1] if ":" in data else ""
    msg = cq.message
    has_photo = bool(msg.photo) if msg else False
    channel = getattr(settings, "CHANNEL_URL", "") or ""

    async def _edit(html, kb=None):
        try:
            if has_photo:
                await msg.edit_caption(caption=html, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.edit_text(html, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await msg.answer(html, parse_mode="HTML", reply_markup=kb)

    if action.startswith("letter:"):
        await cq.answer("Welcome!"); return
    if action == "close":
        try: await msg.delete()
        except Exception:
            try: await msg.edit_reply_markup(reply_markup=None)
            except Exception: pass
        await cq.answer(); return

    back = InlineKeyboardMarkup(inline_keyboard=[[_b("Back", "welcome:home", "primary")]])
    if action == "help":
        await _edit("<b>obra help</b>\n\nJust send a message.\n/clear /skill /lang /memory\n\nTap Back.", back)
        await cq.answer(); return
    if action == "skills":
        skills = await db.list_skills(cq.from_user.id)
        body = "No schedules.\n<code>/skill every 1 minutes: send me hi</code>" if not skills else "<b>Skills</b>\n"+"\n".join(f"#{s['id']} <code>{s['instruction']}</code>" for s in skills)
        await _edit(body+"\n\nTap Back.", back); await cq.answer(); return
    if action == "memory":
        mem = await db.get_user_memory(cq.from_user.id)
        body = "Nothing stored." if not mem else f"<b>Memory</b>\n{mem.get('name') or '—'}\n{mem.get('notes') or '—'}"
        await _edit(body+"\n\nTap Back.", back); await cq.answer(); return
    if action == "lang":
        await _edit("Use <code>/lang en</code> or <code>/lang hi</code>\n\nTap Back.", back); await cq.answer(); return
    if action == "home":
        from services.welcome import welcome_caption, build_welcome_keyboard
        name = cq.from_user.full_name if cq.from_user else "friend"
        await _edit(welcome_caption(name), build_welcome_keyboard(0, channel)); await cq.answer(); return
    await cq.answer()

@router.callback_query(F.data.startswith("confirm:"))
async def on_confirm(cq: CallbackQuery):
    await cq.answer("OK")

@router.callback_query(F.data.startswith("cancel:"))
async def on_cancel(cq: CallbackQuery):
    await cq.answer("Cancelled")
