from aiogram import Router, Bot
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
    await send_welcome(message, bot, channel_url=getattr(settings,"CHANNEL_URL","") or "", photo_url=getattr(settings,"WELCOME_PHOTO_URL","") or "")

@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "<b>obra</b>\n\nJust chat.\n\n"
        "/clear — clear memory\n/skill — schedules\n/lang — language\n/memory — notes\n"
    )
    if is_admin(message.from_user.id):
        text += "\nAdmin: /stats /block /unblock\n"
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
    await message.answer(f"<b>Memory</b>\nName: {mem.get('name') or '—'}\nNotes: {mem.get('notes') or '—'}\nPrefs: <code>{mem.get('preferences')}</code>", parse_mode="HTML")

@router.message(Command("lang"))
async def cmd_lang(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(f"Usage: <code>/lang en</code>\n{', '.join(LANGS)}", parse_mode="HTML")
        return
    code = parts[1].strip().lower()[:5]
    if code not in LANGS:
        await message.answer("Unknown code.")
        return
    await db.set_user_settings(message.from_user.id, language=code)
    await message.answer(t(code, "lang_set", lang=LANGS[code]))

@router.message(Command("skill"))
async def cmd_skill(message: Message):
    raw = (message.text or "").strip()
    parts = raw.split(maxsplit=1)
    arg = parts[1].strip() if len(parts)>1 else ""
    low = arg.lower()
    if not arg or low in ("list","ls"):
        skills = await db.list_skills(message.from_user.id)
        if not skills:
            await message.answer("No schedules.\n<code>/skill every 1 minutes: send me hi</code>", parse_mode="HTML")
            return
        await message.answer("<b>Schedules</b>\n" + "\n".join(f"#{s['id']} <code>{s['instruction']}</code>" for s in skills), parse_mode="HTML")
        return
    if low.startswith("del "):
        sid = low.split(maxsplit=1)[1].strip()
        if sid.isdigit():
            await db.delete_skill(message.from_user.id, int(sid))
            try:
                from services.scheduler import reload_skills_now
                await reload_skills_now()
            except Exception: pass
            await message.answer("Deleted.")
        return
    if low.startswith("run "):
        sid = low.split(maxsplit=1)[1].strip()
        skills = await db.list_skills(message.from_user.id)
        skill = next((s for s in skills if str(s["id"])==sid), None)
        if not skill:
            await message.answer("Not found")
            return
        from services.scheduler import _run_skill
        await message.answer("Running…")
        await _run_skill(skill)
        return
    await db.add_skill(message.from_user.id, arg[:40], arg)
    try:
        from services.scheduler import reload_skills_now
        await reload_skills_now()
    except Exception as e:
        await message.answer(f"Saved but schedule failed: {e}")
        return
    await message.answer("✅ Scheduled. Keep bot process running.\n<code>/skill list</code>", parse_mode="HTML")

@router.message(Command("skills"))
async def cmd_skills(message: Message):
    message.text = "/skill list"
    await cmd_skill(message)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id): return
    s = await db.get_stats(24)
    await message.answer(f"Users: {s['active_users']}\nChats: {s['chats']}\nBlocked: {s['blocked']}", parse_mode="HTML")

@router.message(Command("block"))
async def cmd_block(message: Message):
    if not is_admin(message.from_user.id): return
    parts = (message.text or "").split()
    if len(parts)<2 or not parts[1].isdigit():
        await message.answer("Usage: /block user_id"); return
    await db.block_user(int(parts[1])); await message.answer("Blocked.")

@router.message(Command("unblock"))
async def cmd_unblock(message: Message):
    if not is_admin(message.from_user.id): return
    parts = (message.text or "").split()
    if len(parts)<2 or not parts[1].isdigit():
        await message.answer("Usage: /unblock user_id"); return
    await db.unblock_user(int(parts[1])); await message.answer("Unblocked.")


@router.message(Command("secretary"))
async def cmd_secretary(message: Message):
    """Pause/resume secretary auto-replies for this owner."""
    parts = (message.text or "").split(maxsplit=1)
    arg = (parts[1].strip().lower() if len(parts) > 1 else "")
    uid = message.from_user.id
    us = await db.get_user_settings(uid)
    if arg in ("off", "pause", "stop"):
        await db.set_user_settings(uid, secretary_paused=True)
        await message.answer("⏸️ Secretary auto-reply <b>paused</b>.\n<code>/secretary on</code> to resume.", parse_mode="HTML")
        return
    if arg in ("on", "resume", "start"):
        await db.set_user_settings(uid, secretary_paused=False)
        await message.answer("▶️ Secretary auto-reply <b>on</b>.", parse_mode="HTML")
        return
    paused = bool(us.get("secretary_paused"))
    await message.answer(
        f"🔐 <b>Secretary</b>\n"
        f"Auto-reply: <b>{'PAUSED' if paused else 'ON'}</b>\n\n"
        f"1) @BotFather → Secretary Mode ON\n"
        f"2) Settings → Chat Automation → this bot\n"
        f"3) <code>/secretary on|off</code>",
        parse_mode="HTML",
    )
