import random, asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType, ChatAction
from config.settings import settings
from services.db import db
from services.llm import chat_completion, detect_agent, AGENTS
from services.tools import TOOLS, run_tool
from services import vector_memory
from services.i18n import t, language_system_hint
from services.telegram_send import send_rich, send_thinking_draft, send_ephemeral, react as tg_react
from services.rich_format import estimate_complexity, ensure_rich_structure, RICH_SYSTEM_APPENDIX, detect_poll_intent

router = Router()

async def keep_typing(bot: Bot, chat_id: int, stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            continue

def is_group(m: Message) -> bool:
    return m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

async def should_reply(m: Message, bot: Bot) -> bool:
    if not is_group(m):
        return True
    if not getattr(settings, "GROUP_MENTION_ONLY", True):
        return True
    me = await bot.me()
    uname = (me.username or "obra").lower()
    text = (m.text or m.caption or "").lower()
    if f"@{uname}" in text or "obra" in text.split():
        return True
    if m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id == me.id:
        return True
    return False

async def build_system(user_id, query, agent, is_grp, chat_id=0) -> str:
    base = AGENTS.get(agent, AGENTS["default"])
    mem = await db.get_user_memory(user_id)
    if mem:
        base += f"\n\nKey memory:\n{mem}"
    try:
        sem = await vector_memory.search_memory(user_id, query, n=5)
        if sem:
            base += "\n\nVector memory:\n- " + "\n- ".join(sem)
    except Exception:
        pass
    if is_grp and chat_id:
        try:
            gm = await vector_memory.search_group_memory(chat_id, query, n=4)
            if gm:
                base += "\n\nGroup brain:\n- " + "\n- ".join(gm)
        except Exception:
            pass
    us = await db.get_user_settings(user_id)
    base += language_system_hint(us.get("language") or "en")
    base += f"\n\n[Active agent: {agent}]" + RICH_SYSTEM_APPENDIX
    return base

async def send_rich_or_plain(bot, chat_id, text, reply_to=None):
    await send_rich(bot, chat_id, text, reply_to=reply_to)

async def send_thinking(bot, chat_id, draft_id, stage="Thinking…"):
    await send_thinking_draft(bot, chat_id, draft_id, stage)

@router.message(F.text | F.caption)
async def chat_handler(message: Message, bot: Bot):
    if not message.text and not message.caption:
        return
    text = (message.text or message.caption or "").strip()
    if text.startswith("/"):
        return
    user = message.from_user
    if not user:
        return
    chat_id = message.chat.id
    if await db.is_blocked(user.id):
        return
    if not await should_reply(message, bot):
        return

    ok, _ = await db.check_rate_limit(user.id)
    if not ok:
        msg = t((await db.get_user_settings(user.id)).get("language") or "en", "rate_limit")
        if is_group(message):
            await send_ephemeral(bot, chat_id, user.id, msg)
        else:
            await message.answer(msg)
        return
    okq, _ = await db.check_daily_quota(user.id)
    if not okq:
        msg = t((await db.get_user_settings(user.id)).get("language") or "en", "quota")
        if is_group(message):
            await send_ephemeral(bot, chat_id, user.id, msg)
        else:
            await message.answer(msg)
        return

    poll = detect_poll_intent(text)
    if poll:
        q, opts = poll
        try:
            await bot.send_poll(chat_id=chat_id, question=q[:300], options=opts, is_anonymous=True, reply_to_message_id=message.message_id)
            await db.add_message(chat_id, "user", text)
            await db.add_message(chat_id, "assistant", f"[poll] {q}")
            return
        except Exception:
            pass

    agent = detect_agent(text)
    is_grp = is_group(message)
    await db.add_message(chat_id, "user", text)
    history = await db.get_history(chat_id, limit=settings.MAX_HISTORY_TURNS * 2)
    history = history + [{"role": "user", "content": text}]
    system = await build_system(user.id, text, agent, is_grp, chat_id=chat_id)
    model = settings.model_for(agent)
    us = await db.get_user_settings(user.id)
    user_provider = None
    if us.get("api_key"):
        user_provider = {"api_key": us["api_key"], "api_base": us.get("api_base"), "api_model": us.get("api_model")}

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(bot, chat_id, stop_typing))
    draft_id = random.randint(1, 2_000_000_000)
    await send_thinking(bot, chat_id, draft_id, f"Thinking… ({agent})")

    try:
        complexity = estimate_complexity(text)
        max_tok = {"small": settings.MAX_TOKENS_SMALL, "medium": settings.MAX_TOKENS_MEDIUM, "big": settings.MAX_TOKENS_BIG}.get(complexity, settings.MAX_TOKENS_MEDIUM)
        if agent in ("coder", "solver") or any(w in text.lower() for w in ("make", "build", "create", "bot", "downloader", "full code", "script")):
            max_tok = max(max_tok, getattr(settings, "MAX_TOKENS_BIG", 16384) or 16384)
            system = system + (
                "\n\nCRITICAL: COMPLETE deliverable required. "
                "Write full working code (NOT a 50-line stub). "
                "MUST call create_file or create_zip for downloadable delivery. "
                "Include main entry, requirements, and run steps."
            )
        result = await chat_completion(
            messages=history, system=system, tools=TOOLS, model=model,
            temperature=0.35 if agent == "coder" else 0.7,
            max_tokens=max_tok, user_provider=user_provider,
        )

        for rnd in range(10):
            if not result.get("tool_calls"):
                break
            await send_thinking(bot, chat_id, draft_id, f"Tools… ({rnd+1})")
            raw = result["raw_message"]
            history.append({
                "role": "assistant", "content": raw.content,
                "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in (raw.tool_calls or [])],
            })
            for tc in result["tool_calls"]:
                result_t = await run_tool(tc["name"], tc["arguments"], user_id=user.id)
                if len(result_t) == 2:
                    tool_text, img = result_t
                    file_att = None
                else:
                    tool_text, img, file_att = result_t
                if tool_text and tool_text.startswith("POLL_REQUIRED::"):
                    import json
                    try:
                        payload = json.loads(tool_text.split("::", 1)[1])
                        await bot.send_poll(chat_id=chat_id, question=str(payload.get("question","Poll"))[:300], options=[str(o)[:100] for o in (payload.get("options") or [])][:10], is_anonymous=True, reply_to_message_id=message.message_id)
                        tool_text = "Poll created."
                    except Exception as e:
                        tool_text = f"Poll failed: {e}"
                if file_att:
                    fn, data = file_att
                    await bot.send_document(chat_id, document=BufferedInputFile(data, filename=fn), caption=fn[:200], reply_to_message_id=message.message_id)
                if img:
                    await bot.send_photo(chat_id, photo=BufferedInputFile(img, filename="obra.png"), reply_to_message_id=message.message_id)
                history.append({"role": "tool", "tool_call_id": tc["id"], "content": tool_text or ""})
            result = await chat_completion(messages=history, system=system, tools=TOOLS, model=model, temperature=0.6, max_tokens=max_tok, user_provider=user_provider)

        reply = ensure_rich_structure(result.get("content") or "...", user_text=text, auto_quote=True)
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass
        await send_rich_or_plain(bot, chat_id, reply, reply_to=message.message_id)
        # If coder mode produced big code in text but no file tool was used, auto-attach a .py
        if agent == "coder" and "```" in reply and len(reply) > 800:
            import re as _re
            blocks = _re.findall(r"```(?:python|py|javascript|js|html|css|bash|sh)?\n([\s\S]*?)```", reply)
            if blocks:
                biggest = max(blocks, key=len)
                if len(biggest) > 400:
                    from aiogram.types import BufferedInputFile as _BIF
                    fname = "obra_project.py"
                    if "telegram" in text.lower() or "bot" in text.lower():
                        fname = "bot_main.py"
                    if "html" in text.lower() and "```html" in reply.lower():
                        fname = "index.html"
                    try:
                        await bot.send_document(
                            chat_id,
                            document=_BIF(biggest.encode("utf-8"), filename=fname),
                            caption=f"📎 Auto-exported `{fname}` ({len(biggest)} chars)",
                            reply_to_message_id=message.message_id,
                        )
                    except Exception:
                        pass

        if getattr(settings, "AUTO_REACT", True):
            await tg_react(bot, chat_id, message.message_id, "👍")
        await db.add_message(chat_id, "assistant", reply)
        await db.log_event(user.id, chat_id, "reply", {"agent": agent})
        try:
            await vector_memory.add_memory(user.id, f"User: {text[:200]} | obra: {reply[:200]}")
        except Exception:
            pass
    except Exception as e:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass
        await message.answer(f"⚠️ <code>{str(e)[:280]}</code>", parse_mode="HTML")

async def process_user_text(message: Message, bot: Bot, text: str):
    message.text = text
    await chat_handler(message, bot)
