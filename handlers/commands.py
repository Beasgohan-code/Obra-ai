"""User-facing commands.

/start and /help are the entry points; everything else is *also* available in
natural language, but these commands give explicit control:
/clear /new · /lang · /memory /forget · /skill · /setkey · /project · /tts ·
/usage · /cancel
"""
from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandObject

from services.db import db
from services.i18n import t, LANGS
from services import vector_memory
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


HELP_TEXT = (
    "<b>obra</b> — AI agent\n\n"
    "Just talk. Agents handle the rest.\n\n"
    "<b>Examples</b>\n"
    "• make a full telegram bot and send zip\n"
    "• remember my name is Alex\n"
    "• every day at 9am remind me water\n"
    "• run: print(2+2)\n"
    "• reply to a .md file: make this a skill\n"
    "• upgrade / buy premium\n\n"
    "<b>Commands</b>\n"
    "/start · /help · /clear · /lang &lt;code&gt; · /memory · /forget\n"
    "/skill · /setkey · /project &lt;title&gt; · /tts on|off · /usage · /cancel\n"
    "/ping · /about · /status"
)


@router.message(Command("help"))
async def cmd_help(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        _btn("⭐ Premium", "premium:show", "primary"),
        _btn("Usage", "premium:usage", "success"),
    ]])
    await message.answer(HELP_TEXT, parse_mode="HTML", reply_markup=kb)


# ---------------------------------------------------------------- history
@router.message(Command("clear", "new"))
async def cmd_clear(message: Message):
    await db.clear_history(message.chat.id)
    await message.answer("🧹 Chat history cleared. Fresh start!")


# ---------------------------------------------------------------- language
@router.message(Command("lang"))
async def cmd_lang(message: Message, command: CommandObject):
    uid = message.from_user.id
    us = await db.get_user_settings(uid)
    lang = us.get("language") or "en"
    arg = (command.args or "").strip().lower()
    if not arg:
        langs = " · ".join(f"<code>{k}</code>" for k in LANGS)
        await message.answer(
            f"Current language: <b>{lang}</b>\nSet with <code>/lang en</code> etc.\n{langs}",
            parse_mode="HTML",
        )
        return
    arg = arg[:5]
    if arg not in LANGS:
        await message.answer(f"Unknown language code <code>{arg}</code>. Try /lang without args to list.", parse_mode="HTML")
        return
    await db.set_user_settings(uid, language=arg)
    await message.answer(t(arg, "lang_set", lang=LANGS.get(arg, arg)), parse_mode="HTML")


# ---------------------------------------------------------------- memory
@router.message(Command("memory"))
async def cmd_memory(message: Message):
    uid = message.from_user.id
    mem = await db.get_user_memory(uid) or {}
    prefs = mem.get("preferences") or {}
    lines = [
        "<b>🧠 Memory</b>",
        f"Name: <code>{mem.get('name') or '—'}</code>",
        f"Notes: <code>{(mem.get('notes') or '—')[:300]}</code>",
    ]
    if prefs:
        plines = "\n".join(f"• <code>{k}</code> = <code>{str(v)[:120]}</code>" for k, v in list(prefs.items())[:12])
        lines.append(f"Preferences:\n{plines}")
    lines.append("\nSay <i>remember …</i> to add · <code>/forget</code> to wipe")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("forget"))
async def cmd_forget(message: Message, command: CommandObject):
    uid = message.from_user.id
    what = (command.args or "all").strip().lower()
    if what in ("all", "notes"):
        await db.set_user_memory(uid, notes="")
    if what in ("all", "name"):
        await db.set_user_memory(uid, name="")
    if what in ("all", "preferences", "prefs"):
        await db.set_user_memory(uid, preferences={})
    if what in ("all", "vectors", "semantic"):
        await vector_memory.clear_user_vectors(uid)
    await message.answer(f"🗑️ Forgot: {what}")


# ---------------------------------------------------------------- skills
@router.message(Command("skill", "skills"))
async def cmd_skill(message: Message, command: CommandObject):
    uid = message.from_user.id
    args = (command.args or "").strip()
    if args.lower().startswith("delete ") or args.lower().startswith("remove "):
        try:
            sid = int(args.split()[1])
            await db.delete_skill(uid, sid)
            from services.scheduler import reload_skills_now
            try:
                await reload_skills_now()
            except Exception:
                pass
            await message.answer(f"🗑️ Deleted skill #{sid}")
        except Exception as e:
            await message.answer(f"Usage: /skill delete &lt;id&gt; ({e})", parse_mode="HTML")
        return
    skills = await db.list_skills(uid)
    if not skills:
        await message.answer(
            "⏰ <b>No skills yet.</b>\n\n"
            "Say e.g. <code>every day at 9am summarize my github</code>\n"
            "or reply to a file: <code>make this a skill</code>\n"
            "Manage with <code>/skill delete &lt;id&gt;</code>",
            parse_mode="HTML",
        )
        return
    lines = [f"#{s['id']} <code>{s['instruction'][:120]}</code>" for s in skills[:15]]
    await message.answer("⏰ <b>Skills</b>\n" + "\n".join(lines) + "\n\n<code>/skill delete &lt;id&gt;</code>", parse_mode="HTML")


# ---------------------------------------------------------------- BYOK
@router.message(Command("setkey"))
async def cmd_setkey(message: Message, command: CommandObject):
    uid = message.from_user.id
    args = (command.args or "").strip()
    if not args or args.lower() in ("clear", "off", "remove"):
        await db.set_user_settings(uid, api_key="", api_base="", api_model="")
        await message.answer("🔑 Personal LLM key cleared — using server providers.")
        return
    parts = args.split()
    api_key = parts[0]
    api_base = parts[1] if len(parts) > 1 else ""
    api_model = parts[2] if len(parts) > 2 else ""
    await db.set_user_settings(uid, api_key=api_key, api_base=api_base or None, api_model=api_model or None)
    masked = api_key[:6] + "…" + api_key[-4:] if len(api_key) > 12 else "***"
    await message.answer(
        f"🔑 Personal key saved (<code>{masked}</code>) — your chats now use your own provider first.\n"
        f"Base: <code>{api_base or 'default'}</code> · Model: <code>{api_model or 'default'}</code>\n"
        f"Clear anytime with <code>/setkey clear</code>",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------- projects
@router.message(Command("project"))
async def cmd_project(message: Message, command: CommandObject):
    uid = message.from_user.id
    title = (command.args or "").strip()
    if not title:
        projects = await db.list_projects(uid)
        if not projects:
            await message.answer("📁 No projects yet. Name this chat: <code>/project my bot</code>", parse_mode="HTML")
            return
        lines = [f"• <code>{p['title']}</code> (chat <code>{p['chat_id']}</code>)" for p in projects[:15]]
        await message.answer("📁 <b>Projects</b>\n" + "\n".join(lines), parse_mode="HTML")
        return
    await db.set_project_title(uid, message.chat.id, title)
    await message.answer(f"📁 This chat is now project <b>{title[:80]}</b>", parse_mode="HTML")


# ---------------------------------------------------------------- tts
@router.message(Command("tts"))
async def cmd_tts(message: Message, command: CommandObject):
    uid = message.from_user.id
    arg = (command.args or "").strip().lower()
    us = await db.get_user_settings(uid)
    lang = us.get("language") or "en"
    if arg in ("on", "1", "yes", "enable"):
        await db.set_user_settings(uid, tts_enabled=1)
        await message.answer(t(lang, "tts_on"))
    elif arg in ("off", "0", "no", "disable"):
        await db.set_user_settings(uid, tts_enabled=0)
        await message.answer(t(lang, "tts_off"))
    else:
        state = "on" if us.get("tts_enabled") else "off"
        await message.answer(f"🔊 TTS is <b>{state}</b> — use <code>/tts on</code> or <code>/tts off</code>", parse_mode="HTML")


# ---------------------------------------------------------------- usage / cancel
@router.message(Command("usage", "limits", "quota"))
async def cmd_usage(message: Message):
    uid = message.from_user.id
    d_u, d_l = await db.usage_today(uid)
    m_u, m_l = await db.usage_month(uid)
    prem = await db.is_premium(uid)
    await message.answer(
        f"<b>{'⭐ Premium' if prem else 'Free'}</b> · today <code>{d_u}/{d_l}</code> · month <code>{m_u}/{m_l}</code>\n"
        f"Say <i>upgrade</i> for Stars premium.",
        parse_mode="HTML",
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    uid = message.from_user.id
    us = await db.get_user_settings(uid)
    lang = us.get("language") or "en"
    n = await db.clear_pending_for_user(uid)
    await message.answer(t(lang, "cancelled") + (f" ({n})" if n else ""))


# ---------------------------------------------------------------- search
@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject):
    """Search this chat's history + long-term memory for a keyword."""
    q = (command.args or "").strip()
    if not q:
        await message.answer("🔎 Usage: <code>/search what you are looking for</code>", parse_mode="HTML")
        return
    uid = message.from_user.id
    hist = await db.search_history(message.chat.id, q, limit=8)
    try:
        mem = await vector_memory.search_memory(uid, q, n=5)
    except Exception:
        mem = []
    parts = []
    if hist:
        parts.append("<b>In this chat:</b>")
        for h in hist:
            snippet = (h["content"] or "")[:160].replace("\n", " ")
            parts.append(f"• <i>{h['role']}</i>: {snippet}")
    if mem:
        parts.append("<b>From memory:</b>")
        for m in mem:
            parts.append(f"• {m[:160]}")
    if not parts:
        parts.append(f"Nothing found for <code>{q}</code>.")
    await message.answer("\n".join(parts)[:4000], parse_mode="HTML")


# ---------------------------------------------------------------- catch-all
@router.message(F.text.startswith("/"))
async def cmd_unknown(message: Message):
    """Any unrecognised /command gets a helpful nudge instead of silence."""
    await message.answer(
        "🤔 Unknown command. Try <code>/help</code> — or just talk to me in plain words.",
        parse_mode="HTML",
    )
