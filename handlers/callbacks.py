from aiogram import Router, F
from aiogram.types import CallbackQuery
from services.db import db
from services.google_tools import gmail_send
from services.i18n import t

router = Router()


@router.callback_query(F.data.startswith("confirm:"))
async def on_confirm(cq: CallbackQuery):
    pid = cq.data.split(":", 1)[1]
    pending = await db.pop_pending(pid)
    if not pending:
        await cq.answer("Expired or already handled", show_alert=True)
        return
    if cq.from_user and pending["user_id"] and cq.from_user.id != pending["user_id"]:
        await cq.answer("Not your action", show_alert=True)
        return
    us = await db.get_user_settings(cq.from_user.id)
    lang = us.get("language") or "en"
    action = pending["action"]
    payload = pending["payload"]
    if action == "gmail_send":
        result = await gmail_send(payload.get("to",""), payload.get("subject",""), payload.get("body",""))
        await cq.message.answer(result)
        await cq.answer(t(lang, "done"))
    else:
        await cq.answer("Unknown action")


@router.callback_query(F.data.startswith("cancel:"))
async def on_cancel(cq: CallbackQuery):
    pid = cq.data.split(":", 1)[1]
    await db.pop_pending(pid)
    us = await db.get_user_settings(cq.from_user.id)
    lang = us.get("language") or "en"
    await cq.message.answer(t(lang, "cancelled"))
    await cq.answer()


@router.callback_query(F.data.startswith("welcome:"))
async def on_welcome(cq: CallbackQuery):
    """Edit the same /start message instead of flooding new messages."""
    data = cq.data or ""
    action = data.split(":", 1)[1] if ":" in data else ""
    msg = cq.message
    has_photo = bool(msg.photo) if msg else False

    async def _edit(html: str, kb=None):
        try:
            if has_photo:
                await msg.edit_caption(caption=html, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.edit_text(html, parse_mode="HTML", reply_markup=kb)
        except Exception:
            # fallback only if edit impossible
            await msg.answer(html, parse_mode="HTML", reply_markup=kb)

    if action.startswith("letter:"):
        await cq.answer("Welcome!", show_alert=False)
        return

    if action == "close":
        try:
            await msg.delete()
        except Exception:
            try:
                await msg.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        await cq.answer()
        return

    from services.welcome import build_welcome_keyboard
    from config.settings import settings
    channel = getattr(settings, "CHANNEL_URL", "") or ""
    back_kb = build_welcome_keyboard(0, channel)

    if action == "help":
        html = (
            "<b>obra help</b>\n\n"
            "Just send a message — no special commands needed.\n\n"
            "/clear — clear memory\n"
            "/skill — schedules\n"
            "/lang — language\n"
            "/memory — saved notes\n\n"
            "Tap <b>Back</b> to return."
        )
        # add Back button
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        def _b(text, data, style=None):
            kw = {"text": text, "callback_data": data}
            if style:
                kw["style"] = style
            try:
                return InlineKeyboardButton(**kw)
            except TypeError:
                kw.pop("style", None)
                return InlineKeyboardButton(**kw)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [_b("Back", "welcome:home", "primary")],
        ])
        await _edit(html, kb)
        await cq.answer()
        return

    if action == "skills":
        from services.db import db
        skills = await db.list_skills(cq.from_user.id)
        if not skills:
            body = "No schedules yet.\n<code>/skill every 1 minutes: send me hi</code>"
        else:
            lines = [f"#{s['id']} <code>{s['instruction']}</code>" for s in skills]
            body = "<b>Skills</b>\n" + "\n".join(lines)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        def _b(text, data, style=None):
            kw = {"text": text, "callback_data": data}
            if style:
                kw["style"] = style
            try:
                return InlineKeyboardButton(**kw)
            except TypeError:
                kw.pop("style", None)
                return InlineKeyboardButton(**kw)
        kb = InlineKeyboardMarkup(inline_keyboard=[[_b("Back", "welcome:home", "primary")]])
        await _edit(body + "\n\nTap <b>Back</b> to return.", kb)
        await cq.answer()
        return

    if action == "memory":
        from services.db import db
        mem = await db.get_user_memory(cq.from_user.id)
        if not mem:
            body = "Nothing stored yet."
        else:
            body = (
                f"<b>Memory</b>\nName: {mem.get('name') or '—'}\n"
                f"Notes: {mem.get('notes') or '—'}"
            )
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        def _b(text, data, style=None):
            kw = {"text": text, "callback_data": data}
            if style:
                kw["style"] = style
            try:
                return InlineKeyboardButton(**kw)
            except TypeError:
                kw.pop("style", None)
                return InlineKeyboardButton(**kw)
        kb = InlineKeyboardMarkup(inline_keyboard=[[_b("Back", "welcome:home", "primary")]])
        await _edit(body + "\n\nTap <b>Back</b>.", kb)
        await cq.answer()
        return

    if action == "lang":
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        def _b(text, data, style=None):
            kw = {"text": text, "callback_data": data}
            if style:
                kw["style"] = style
            try:
                return InlineKeyboardButton(**kw)
            except TypeError:
                kw.pop("style", None)
                return InlineKeyboardButton(**kw)
        kb = InlineKeyboardMarkup(inline_keyboard=[[_b("Back", "welcome:home", "primary")]])
        await _edit(
            "Set language with:\n<code>/lang en</code> or <code>/lang hi</code>\n\nTap <b>Back</b>.",
            kb,
        )
        await cq.answer()
        return

    if action == "home":
        from services.welcome import welcome_caption, build_welcome_keyboard
        name = cq.from_user.full_name if cq.from_user else "friend"
        await _edit(welcome_caption(name), build_welcome_keyboard(0, channel))
        await cq.answer()
        return

    await cq.answer()


@router.callback_query(F.data.startswith("reply:"))
async def on_reply_actions(cq: CallbackQuery):
    parts = (cq.data or "").split(":")
    # reply:more:msgid or reply:retry:msgid
    if len(parts) < 2:
        await cq.answer()
        return
    action = parts[1]
    await cq.answer("Working…" if action in ("more", "retry") else "")
    if action not in ("more", "retry"):
        return
    # Use last user message from history
    from services.db import db
    from handlers.chat import process_user_text
    hist = await db.get_history(cq.message.chat.id, limit=6)
    user_msgs = [h for h in hist if h.get("role") == "user"]
    if not user_msgs:
        await cq.message.answer("Nothing to continue.")
        return
    prompt = user_msgs[-1]["content"]
    if action == "more":
        prompt = f"Continue / expand on your previous answer about:\n{prompt}\n\nAdd more detail, steps, or examples."
    else:
        prompt = f"Try again with a better answer for:\n{prompt}"
    # Minimal synthetic message
    class _Msg:
        pass
    m = cq.message
    await process_user_text(m, cq.bot, prompt)
