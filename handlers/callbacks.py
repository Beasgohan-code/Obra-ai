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
    data = cq.data or ""
    action = data.split(":", 1)[1] if ":" in data else ""
    if action.startswith("letter:"):
        await cq.answer("✨ Welcome!", show_alert=False)
        return
    if action == "close":
        try:
            await cq.message.delete()
        except Exception:
            try:
                await cq.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        await cq.answer()
        return
    if action == "help":
        await cq.message.answer(
            "<b>obra help</b>\n\n"
            "Just send a message — no special commands needed.\n\n"
            "/clear — clear memory\n"
            "/skill — schedules\n"
            "/lang — language\n"
            "/memory — saved notes",
            parse_mode="HTML",
        )
        await cq.answer()
        return
    if action == "skills":
        from services.db import db
        skills = await db.list_skills(cq.from_user.id)
        if not skills:
            await cq.message.answer(
                "No schedules yet.\n<code>/skill every 1 minutes: send me hi</code>",
                parse_mode="HTML",
            )
        else:
            lines = [f"#{s['id']} <code>{s['instruction']}</code>" for s in skills]
            await cq.message.answer("<b>Skills</b>\n" + "\n".join(lines), parse_mode="HTML")
        await cq.answer()
        return
    if action == "memory":
        from services.db import db
        mem = await db.get_user_memory(cq.from_user.id)
        if not mem:
            await cq.message.answer("Nothing stored yet.")
        else:
            await cq.message.answer(
                f"<b>Memory</b>\nName: {mem.get('name') or '—'}\nNotes: {mem.get('notes') or '—'}",
                parse_mode="HTML",
            )
        await cq.answer()
        return
    if action == "lang":
        await cq.message.answer(
            "Set language: <code>/lang en</code> or <code>/lang hi</code>",
            parse_mode="HTML",
        )
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
