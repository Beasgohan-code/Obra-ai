"""Minimal clean command set for Obra."""

from aiogram import Router, Bot, F
from aiogram.types import Message
from aiogram.filters import Command

from services.db import db
from config.settings import settings
from services.i18n import t, LANGS

router = Router()


def is_admin(uid: int) -> bool:
    return uid in settings.admin_list


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    from services.welcome import send_welcome
    channel = getattr(settings, "CHANNEL_URL", "") or ""
    photo = getattr(settings, "WELCOME_PHOTO_URL", "") or ""
    await send_welcome(message, bot, channel_url=channel, photo_url=photo)


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "<b>obra</b>\n\n"
        "Talk normally. No special commands needed for most things.\n\n"
        "<b>Useful</b>\n"
        "/clear — reset this chat history\n"
        "/skill — scheduled messages\n"
        "/lang en|hi|es|… — reply language\n"
        "/memory — what I remember about you\n\n"
        "<b>Examples</b>\n"
        "• write code / explain something\n"
        "• create a .py or .html file\n"
        "• poll: Best option? A / B / C\n"
        "• /skill every 1 minutes: send me hi\n"
    )
    if is_admin(message.from_user.id):
        text += "\n<b>Admin</b>\n/stats /block /unblock\n"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    await db.clear_history(message.chat.id)
    await message.answer("Cleared.")


@router.message(Command("memory"))
async def cmd_memory(message: Message):
    mem = await db.get_user_memory(message.from_user.id)
    if not mem:
        await message.answer("Nothing stored yet.")
        return
    await message.answer(
        f"<b>Memory</b>\n"
        f"Name: {mem.get('name') or '—'}\n"
        f"Notes: {mem.get('notes') or '—'}\n"
        f"Prefs: <code>{mem.get('preferences')}</code>",
        parse_mode="HTML",
    )


@router.message(Command("lang"))
async def cmd_lang(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: <code>/lang en</code>\n"
            f"Codes: <code>{', '.join(LANGS)}</code>",
            parse_mode="HTML",
        )
        return
    code = parts[1].strip().lower()[:5]
    if code not in LANGS:
        await message.answer("Unknown language code.")
        return
    await db.set_user_settings(message.from_user.id, language=code)
    await message.answer(t(code, "lang_set", lang=LANGS[code]), parse_mode="HTML")


@router.message(Command("skill"))
async def cmd_skill(message: Message):
    """
    /skill every 1 minutes: send me hi
    /skill list
    /skill del <id>
    /skill run <id>
    """
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    low = arg.lower()

    if not arg or low in ("list", "ls"):
        skills = await db.list_skills(message.from_user.id)
        if not skills:
            await message.answer(
                "No schedules yet.\n"
                "<code>/skill every 1 minutes: send me hi</code>",
                parse_mode="HTML",
            )
            return
        lines = [
            f"#{s['id']} <code>{s['instruction']}</code>" for s in skills
        ]
        await message.answer("<b>Schedules</b>\n" + "\n".join(lines), parse_mode="HTML")
        return

    if low.startswith("del ") or low.startswith("delete "):
        sid = low.split(maxsplit=1)[1].strip()
        if sid.isdigit():
            await db.delete_skill(message.from_user.id, int(sid))
            try:
                from services.scheduler import reload_skills_now
                await reload_skills_now()
            except Exception:
                pass
            await message.answer("Deleted.")
        return

    if low.startswith("run "):
        sid = low.split(maxsplit=1)[1].strip()
        skills = await db.list_skills(message.from_user.id)
        skill = next((s for s in skills if str(s["id"]) == sid), None)
        if not skill:
            await message.answer("Not found.")
            return
        from services.scheduler import _run_skill
        await message.answer("Running…")
        await _run_skill(skill)
        return

    instruction = arg
    name = instruction[:40]
    await db.add_skill(message.from_user.id, name, instruction)
    try:
        from services.scheduler import reload_skills_now
        await reload_skills_now()
    except Exception as e:
        await message.answer(f"Saved, but schedule failed: {e}")
        return
    await message.answer(
        "✅ Scheduled.\nKeep the bot running for it to fire.\n"
        "<code>/skill list</code>",
        parse_mode="HTML",
    )


@router.message(Command("skills"))
async def cmd_skills(message: Message):
    # alias
    message.text = "/skill list"
    await cmd_skill(message)


# ---------- admin only ----------

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    s = await db.get_stats(24)
    lines = [
        f"<b>24h</b>",
        f"Users: {s['active_users']}",
        f"Chats: {s['chats']}",
        f"Blocked: {s['blocked']}",
    ]
    for k, v in (s.get("events") or {}).items():
        lines.append(f"{k}: {v}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("block"))
async def cmd_block(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /block user_id")
        return
    await db.block_user(int(parts[1]), "admin")
    await message.answer("Blocked.")


@router.message(Command("unblock"))
async def cmd_unblock(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /unblock user_id")
        return
    await db.unblock_user(int(parts[1]))
    await message.answer("Unblocked.")


# Keep confirm for Gmail safety (not shown in help)
@router.message(Command("confirm"))
async def cmd_confirm(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        return
    from services.google_tools import gmail_send
    pending = await db.pop_pending(parts[1])
    if not pending:
        return
    if pending["action"] == "gmail_send":
        pl = pending["payload"]
        r = await gmail_send(pl.get("to", ""), pl.get("subject", ""), pl.get("body", ""))
        await message.answer(r)
