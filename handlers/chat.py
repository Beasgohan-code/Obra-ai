import random
from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType, ChatAction

from config.settings import settings
from services.db import db
from services.llm import chat_completion, detect_agent, AGENTS
from services.tools import TOOLS, run_tool
from services import vector_memory
from services.media_ai import extract_facts_for_memory, text_to_speech
from services.i18n import t, language_system_hint
from services.persona import quick_reply, polish_system
from services.smart_context import force_file_delivery, suggest_title

router = Router()


async def keep_typing(bot: Bot, chat_id: int, stop_event: "asyncio.Event"):
    """Re-send typing action every ~4s until stop_event is set."""
    import asyncio
    try:
        while not stop_event.is_set():
            try:
                await bot.send_chat_action(chat_id, ChatAction.TYPING)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                continue
    except Exception:
        pass



def is_group(m: Message) -> bool:
    return m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def should_reply(m: Message, bot: Bot) -> bool:
    if not is_group(m):
        return True
    if not settings.GROUP_MENTION_ONLY:
        return True
    me = await bot.me()
    uname = (me.username or "obra").lower()
    text = (m.text or m.caption or "").lower()
    if f"@{uname}" in text or "obra" in text.split():
        return True
    if m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id == me.id:
        return True
    return False


async def build_system(user_id: int, query: str, agent: str, is_grp: bool, chat_id: int = 0) -> str:
    base = AGENTS.get(agent, AGENTS["default"])
    mem = await db.get_user_memory(user_id)
    if mem:
        base += f"\n\nKey-value memory:\n{mem}"
    try:
        sem = await vector_memory.search_memory(user_id, query, n=5)
        if sem:
            base += "\n\nVector memory:\n- " + "\n- ".join(sem)
    except Exception:
        pass
    try:
        skills = await db.list_skills(user_id)
        if skills:
            lines = [f"- {s['name']}: {s['instruction']}" for s in skills[:8]]
            base += "\n\nSaved skills (user routines):\n" + "\n".join(lines)
    except Exception:
        pass
    if is_grp:
        base += "\n\nGroup chat — be concise. Shared group brain is available via group_remember tool."
        try:
            if chat_id:
                gm = await vector_memory.search_group_memory(chat_id, query, n=4)
                if gm:
                    base += "\n\nGroup brain:\n- " + "\n- ".join(gm)
        except Exception:
            pass
    us = await db.get_user_settings(user_id)
    base += language_system_hint(us.get("language") or "en")
    base += f"\n\n[Active agent: {agent}]"
    base += RICH_SYSTEM_APPENDIX
    return base


from services.telegram_send import send_rich, send_thinking_draft, send_ephemeral, react as tg_react
from services.rich_format import estimate_complexity, tokens_for_complexity, ensure_rich_structure, RICH_SYSTEM_APPENDIX, detect_poll_intent


async def send_rich_or_plain(bot: Bot, chat_id: int, text: str, reply_to: int = None):
    await send_rich(bot, chat_id, text, reply_to=reply_to)


async def send_thinking(bot: Bot, chat_id: int, draft_id: int, stage: str = "Thinking…"):
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

    # Block check
    if await db.is_blocked(user.id):
        return

    # Rate limit + daily/monthly quotas (premium aware)
    if user.id not in settings.admin_list:
        ok, remaining = await db.check_rate_limit(user.id)
        if not ok:
            await message.answer("⏳ Slow down a bit — rate limit.")
            return
        ok_q, reason = await db.check_quotas(user.id)
        if not ok_q:
            await message.answer(f"🚫 {reason}")
            return

    if not await should_reply(message, bot):
        return

    me = await bot.me()
    if me.username:
        text = text.replace(f"@{me.username}", "").replace(f"@{me.username.lower()}", "").strip()
    if not text:
        return

    # Instant replies for tiny greetings (no LLM cost)
    qr = quick_reply(text)
    if qr:
        await message.answer(qr, parse_mode="Markdown")
        await db.add_message(message.chat.id, "user", text)
        await db.add_message(message.chat.id, "assistant", qr)
        return  # BUGFIX: previously fell through and ALSO sent a full LLM reply

    # Premium / usage intents (natural language — no commands)
    low_intent = text.lower().strip()
    if low_intent in ("upgrade", "premium", "buy premium", "stars", "buy stars") or "buy premium" in low_intent:
        from handlers.payments import send_premium_invoice
        try:
            await send_premium_invoice(bot, message.chat.id)
        except Exception as e:
            await message.answer(f"Premium invoice: {e}")
        return
    if low_intent in ("usage", "my usage", "limits", "quota"):
        d_u, d_l = await db.usage_today(user.id)
        m_u, m_l = await db.usage_month(user.id)
        prem = await db.is_premium(user.id)
        await message.answer(
            f"{'⭐ Premium' if prem else 'Free'} · today {d_u}/{d_l} · month {m_u}/{m_l}"
        )
        return

    # make skill from reply to text/document
    if message.reply_to_message and any(k in text.lower() for k in ("make skill", "makeskill", "save skill", "add skill", "create skill")):
        src = message.reply_to_message
        body = (src.text or src.caption or "").strip()
        if not body and src.document:
            try:
                f = await bot.get_file(src.document.file_id)
                bio = await bot.download_file(f.file_path)
                body = bio.read().decode("utf-8", errors="replace")[:20000]
            except Exception as e:
                await message.answer(f"Could not read file: {e}")
                return
        if body:
            name = (text[:40] if len(text) > 15 else body.split("\n")[0][:40])
            await db.add_skill(user.id, name, body)
            try:
                from services.scheduler import reload_skills_now
                await reload_skills_now()
            except Exception:
                pass
            await message.answer(f"✅ Skill saved ({len(body)} chars).")
            return

    # Auto poll detection (Bot API sendPoll)
    poll = detect_poll_intent(text)
    if poll:
        question, options = poll
        try:
            await bot.send_poll(
                chat_id=message.chat.id,
                question=question[:300],
                options=options,
                is_anonymous=True,
                reply_to_message_id=message.message_id,
            )
            await db.add_message(message.chat.id, "user", text)
            await db.add_message(message.chat.id, "assistant", f"[poll] {question}")
            return
        except Exception as e:
            # fall through to normal AI if poll fails
            pass

    # Manual agent override: "use coder: ..."
    agent = "default"
    low = text.lower()
    for a in ("coder", "researcher", "writer"):
        if low.startswith(f"use {a}:") or low.startswith(f"/{a} "):
            agent = a
            text = text.split(":", 1)[-1].strip() if ":" in text else text.split(" ", 1)[-1].strip()
            break
    else:
        agent = detect_agent(text)

    chat_id = message.chat.id
    is_grp = is_group(message)
    await db.update_chat_meta(chat_id, title=message.chat.title or str(chat_id), is_group=is_grp)
    await db.add_message(chat_id, "user", text)
    await db.log_event(user.id, chat_id, "message", {"agent": agent})

    history = await db.get_history(chat_id, limit=settings.MAX_HISTORY_TURNS * 2)
    system = await build_system(user.id, text, agent, is_grp, chat_id=chat_id)
    model = settings.model_for(agent)
    us = await db.get_user_settings(user.id)
    user_provider = None
    if us.get("api_key"):
        user_provider = {"api_key": us["api_key"], "api_base": us.get("api_base"), "api_model": us.get("api_model")}

    import asyncio
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(bot, chat_id, stop_typing))
    draft_id = random.randint(1, 2_000_000_000)
    await send_thinking(bot, chat_id, draft_id, f"Thinking… ({agent})")

    try:
        complexity = estimate_complexity(text)
        max_tok = {
            "small": settings.MAX_TOKENS_SMALL,
            "medium": settings.MAX_TOKENS_MEDIUM,
            "big": settings.MAX_TOKENS_BIG,
        }.get(complexity, settings.MAX_TOKENS_MEDIUM)
        system = polish_system(system, mode="chat", agent=agent)
        if agent in ("coder", "solver") or force_file_delivery(text):
            max_tok = max(max_tok, getattr(settings, "MAX_TOKENS_CODE", None) or getattr(settings, "MAX_TOKENS_BIG", 16384) or 16384)
            system += (
                "\n\nCRITICAL: COMPLETE deliverable. Full working code, not a short stub. "
                "MUST call create_file or create_zip for downloadable delivery."
            )
        result = await chat_completion(
            messages=history, system=system, tools=TOOLS, model=model,
            temperature=0.35 if agent == "coder" else 0.7,
            max_tokens=max_tok, user_provider=user_provider
        )

        for rnd in range(16):
            if not result.get("tool_calls"):
                break
            await send_thinking(bot, chat_id, draft_id, f"Tools… ({rnd+1})")
            raw = result["raw_message"]
            from services.llm import _assistant_tool_message
            tcs = result.get("tool_calls") or []
            history.append(_assistant_tool_message(
                getattr(raw, "content", None),
                tcs,
                gemini=bool(result.get("gemini")),
            ))
            for tc in result["tool_calls"]:
                # inject chat_id for group tools
                if tc["name"] == "group_remember" and isinstance(tc.get("arguments"), dict):
                    tc["arguments"].setdefault("chat_id", chat_id)
                if tc["name"] == "clear_chat" and isinstance(tc.get("arguments"), dict):
                    tc["arguments"].setdefault("chat_id", chat_id)
                result_t = None
                last_err = None
                for _try in range(max(1, getattr(settings, "TOOL_MAX_RETRIES", 2) + 1)):
                    try:
                        result_t = await run_tool(tc["name"], tc["arguments"], user_id=user.id)
                        # self-check: retry on obvious failure strings
                        txt0 = result_t[0] if result_t else ""
                        if txt0.startswith("ERR:") or "failed:" in (txt0 or "").lower() or "error:" in (txt0 or "").lower()[:40]:
                            last_err = txt0
                            continue
                        break
                    except Exception as e:
                        last_err = str(e)
                        result_t = (f"Tool error: {e}", None, None)
                if result_t is None:
                    result_t = (last_err or "Tool failed", None, None)
                if len(result_t) == 2:
                    tool_text, img = result_t
                    file_att = None
                else:
                    tool_text, img, file_att = result_t
                if img:
                    await bot.send_photo(
                        chat_id,
                        photo=BufferedInputFile(img, filename="obra.png"),
                        caption=(tool_text[:900] if tool_text else "Image"),
                        reply_to_message_id=message.message_id,
                    )
                    tool_text = tool_text or "Image sent."
                if file_att:
                    fn, data = file_att
                    await bot.send_document(
                        chat_id,
                        document=BufferedInputFile(data, filename=fn),
                        caption=(tool_text[:900] if tool_text else fn),
                        reply_to_message_id=message.message_id,
                    )
                    tool_text = tool_text or f"Sent file {fn}"
                if tool_text.startswith("POLL_REQUIRED::"):
                    import json as _json
                    try:
                        payload = _json.loads(tool_text.split("::", 1)[1])
                        await bot.send_poll(
                            chat_id=chat_id,
                            question=str(payload.get("question", "Poll"))[:300],
                            options=[str(o)[:100] for o in (payload.get("options") or [])][:10],
                            is_anonymous=bool(payload.get("is_anonymous", True)),
                            allows_multiple_answers=bool(payload.get("allows_multiple_answers", False)),
                            reply_to_message_id=message.message_id,
                        )
                        tool_text = "Poll created in chat."
                    except Exception as e:
                        tool_text = f"Poll failed: {e}"
                if tool_text.startswith("CONFIRM_REQUIRED::"):
                    parts = tool_text.split("::", 2)
                    pid = parts[1] if len(parts) > 1 else ""
                    # fix chat_id on pending
                    try:
                        pending = await db.pop_pending(pid)
                        if pending:
                            await db.save_pending(pid, user.id, chat_id, pending["action"], pending["payload"])
                    except Exception:
                        pass
                    def _sb(text, data, style):
                        try:
                            return InlineKeyboardButton(text=text, callback_data=data, style=style)
                        except TypeError:
                            b = InlineKeyboardButton(text=text, callback_data=data)
                            try:
                                b = b.model_copy(update={"style": style})
                            except Exception:
                                pass
                            return b
                    kb = InlineKeyboardMarkup(inline_keyboard=[[
                        _sb("✅ Confirm", f"confirm:{pid}", "success"),
                        _sb("❌ Cancel", f"cancel:{pid}", "danger"),
                    ]])
                    await message.answer(
                        f"⚠️ Confirmation required\n{parts[2] if len(parts)>2 else tool_text}",
                        reply_markup=kb,
                    )
                history.append({"role": "tool", "tool_call_id": tc["id"], "content": tool_text})
                await db.add_message(chat_id, "assistant", f"(tool {tc['name']})")
            result = await chat_completion(
                messages=history, system=system, tools=TOOLS, model=model,
                temperature=0.6, max_tokens=max_tok, user_provider=user_provider
            )

        reply = ensure_rich_structure(result.get("content") or "...", user_text=text, auto_quote=True)
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass
        await send_rich_or_plain(bot, chat_id, reply, reply_to=message.message_id)
        # Auto-export code blocks if model forgot create_file
        if agent == "coder" and "```" in reply and len(reply) > 800:
            import re as _re
            blocks = _re.findall(r"```(?:python|py|javascript|js|html|bash)?\n([\s\S]*?)```", reply)
            if blocks:
                biggest = max(blocks, key=len)
                if len(biggest) > 400:
                    fname = "bot_main.py" if any(w in text.lower() for w in ("bot", "telegram")) else "obra_project.py"
                    try:
                        await bot.send_document(
                            chat_id,
                            document=BufferedInputFile(biggest.encode("utf-8"), filename=fname),
                            caption=f"📎 Auto-exported `{fname}`",
                            reply_to_message_id=message.message_id,
                        )
                    except Exception:
                        pass
        if len(reply) > 600:
            def _sb(text, data, style):
                try:
                    return InlineKeyboardButton(text=text, callback_data=data, style=style)
                except TypeError:
                    return InlineKeyboardButton(text=text, callback_data=data)
            more_kb = InlineKeyboardMarkup(inline_keyboard=[[
                _sb("Continue", f"reply:more:{message.message_id}", "primary"),
                _sb("Retry", f"reply:retry:{message.message_id}", "success"),
            ]])
            try:
                await bot.send_message(chat_id, "⋯", reply_markup=more_kb)
            except Exception:
                pass
        # auto react
        if settings.AUTO_REACT:
            try:
                emoji = {"coder": "💻", "researcher": "🔍", "writer": "✍️", "solver": "🚀", "terminal": "⌨️"}.get(agent, "👍")
                await tg_react(bot, chat_id, message.message_id, emoji)
            except Exception:
                pass
        # auto project title from first long chat
        if settings.AUTO_PROJECT_TITLE and len(text) > 40:
            try:
                projects = await db.list_projects(user.id)
                if not any(pr.get("chat_id") == chat_id for pr in projects):
                    title = suggest_title(text)
                    await db.set_project_title(user.id, chat_id, title)
            except Exception:
                pass
        await db.add_message(chat_id, "assistant", reply)
        # Optional TTS
        try:
            if us.get("tts_enabled"):
                audio = await text_to_speech(reply[:1000])
                if audio:
                    await bot.send_voice(chat_id, voice=BufferedInputFile(audio, filename="obra.mp3"))
        except Exception:
            pass
        await db.log_event(user.id, chat_id, "reply", {"agent": agent, "len": len(reply), "provider": result.get("provider"), "model": result.get("model_used")})

        if len(text) > 25 and len(reply) > 40:
            try:
                await vector_memory.add_memory(
                    user.id, f"User: {text[:200]} | obra({agent}): {reply[:200]}",
                    metadata={"chat_id": str(chat_id), "agent": agent},
                )
            except Exception:
                pass
        if settings.ENABLE_AUTO_FACTS and len(text) > 15:
            try:
                fact = await extract_facts_for_memory(text, reply)
                if fact:
                    await vector_memory.add_memory(user.id, fact, metadata={"type": "auto_fact"})
            except Exception:
                pass

    except Exception as e:
        stop_typing.set()
        try:
            await typing_task
        except Exception:
            pass
        await message.answer(f"⚠️ <code>{str(e)[:280]}</code>", parse_mode="HTML")
        await db.log_event(user.id, chat_id, "error", {"error": str(e)[:200]})


async def process_user_text(message: Message, bot: Bot, text: str):
    """Entry used by voice handler after transcription."""
    user = message.from_user
    chat_id = message.chat.id
    agent = detect_agent(text)
    history = await db.get_history(chat_id, limit=settings.MAX_HISTORY_TURNS * 2)
    history = history + [{"role": "user", "content": text}]
    system = await build_system(user.id, text, agent, is_group(message), chat_id=chat_id)
    await db.add_message(chat_id, "user", text)
    result = await chat_completion(
        messages=history, system=system, tools=TOOLS, model=settings.model_for(agent)
    )
    for _ in range(4):
        if not result.get("tool_calls"):
            break
        raw = result["raw_message"]
        history.append({
            "role": "assistant",
            "content": raw.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in (raw.tool_calls or [])
            ],
        })
        for tc in result["tool_calls"]:
            if tc["name"] == "group_remember" and isinstance(tc.get("arguments"), dict):
                tc["arguments"].setdefault("chat_id", chat_id)
            result_t = await run_tool(tc["name"], tc["arguments"], user_id=user.id)
            if len(result_t) == 2:
                tool_text, img = result_t
                file_att = None
            else:
                tool_text, img, file_att = result_t
            if file_att:
                fn, data = file_att
                await bot.send_document(
                    chat_id,
                    document=BufferedInputFile(data, filename=fn),
                    caption=fn,
                )
            history.append({"role": "tool", "tool_call_id": tc["id"], "content": tool_text or ""})
        result = await chat_completion(
            messages=history, system=system, tools=TOOLS, model=settings.model_for(agent)
        )
    reply = ensure_rich_structure(result.get("content") or "...", user_text=text)
    await send_rich_or_plain(bot, chat_id, reply, reply_to=message.message_id)
    await db.add_message(chat_id, "assistant", reply)
