"""
Background scheduler for timed skills.
Fixes: immediate reload on save, 1-minute intervals, clearer parsing.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings
from services.llm import chat_completion, AGENTS

logger = logging.getLogger("obra.scheduler")
_scheduler: Optional[AsyncIOScheduler] = None
_bot = None


def set_bot(bot):
    global _bot
    _bot = bot


def _parse_schedule(instruction: str):
    t = (instruction or "").lower()

    # every minute / every 1 minute(s)
    if re.search(r"every\s+minute\b", t) or re.search(r"every\s+1\s*m(in|ins|inute|inutes)?\b", t):
        return IntervalTrigger(minutes=1)

    m = re.search(r"every\s+(\d+)\s*(minute|minutes|min|mins)\b", t)
    if m:
        mins = max(1, int(m.group(1)))
        return IntervalTrigger(minutes=mins)

    m = re.search(r"every\s+(\d+)\s*(hour|hours|hr|hrs)\b", t)
    if m:
        return IntervalTrigger(hours=max(1, int(m.group(1))))

    if "hourly" in t:
        return IntervalTrigger(hours=1)

    # every N seconds (clamp >= 30 to avoid spam abuse on free hosts)
    m = re.search(r"every\s+(\d+)\s*(second|seconds|sec|secs)\b", t)
    if m:
        secs = max(30, int(m.group(1)))
        return IntervalTrigger(seconds=secs)

    if "daily" in t or "every day" in t:
        hm = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?", t)
        hour = int(hm.group(1)) if hm else 9
        minute = int(hm.group(2)) if hm and hm.group(2) else 0
        return CronTrigger(hour=hour % 24, minute=minute)

    days = {
        "monday": "mon", "tuesday": "tue", "wednesday": "wed",
        "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
    }
    for name, code in days.items():
        if name in t:
            hm = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?", t)
            hour = int(hm.group(1)) if hm else 9
            minute = int(hm.group(2)) if hm and hm.group(2) else 0
            return CronTrigger(day_of_week=code, hour=hour % 24, minute=minute)

    return None


async def _run_skill(skill: dict):
    if not _bot:
        logger.warning("Skill skipped — bot not ready")
        return
    user_id = skill["user_id"]
    name = skill.get("name") or "skill"
    instruction = skill.get("instruction") or ""
    logger.info("Running skill id=%s name=%s user=%s", skill.get("id"), name, user_id)
    try:
        # If instruction is basically "send me a message...", keep it simple
        low = instruction.lower()
        if any(x in low for x in ("send me", "message me", "ping me", "remind me", "say ")):
            # Direct message without heavy LLM when possible
            body = instruction
            # strip schedule prefix
            body = re.sub(
                r"^(every\s+\d+\s*(minute|minutes|min|mins|hour|hours|second|seconds)|every\s+minute|hourly|daily)\s*[:,\-]?\s*",
                "",
                body,
                flags=re.I,
            ).strip() or f"Scheduled ping from skill **{name}**"
            await _bot.send_message(user_id, f"⏰ <b>{name}</b>\n\n{body}", parse_mode="HTML")
        else:
            result = await chat_completion(
                messages=[{
                    "role": "user",
                    "content": (
                        f"Execute this scheduled skill now.\n"
                        f"Name: {name}\nInstruction: {instruction}\n"
                        f"Produce a short useful update for the user."
                    ),
                }],
                system=AGENTS.get("default", "") + "\nYou are running a scheduled skill. Be concise.",
                temperature=0.5,
                max_tokens=800,
            )
            text = result.get("content") or f"Skill `{name}` ran."
            await _bot.send_message(user_id, f"⏰ <b>{name}</b>\n\n{text[:3500]}", parse_mode="HTML")
        try:
            from services.db import db
            await db.log_event(user_id, user_id, "skill_run", {"skill": name})
        except Exception:
            pass
    except Exception as e:
        logger.exception("Skill failed: %s", e)
        try:
            await _bot.send_message(user_id, f"⏰ Skill `{name}` failed: {e}")
        except Exception:
            pass


async def refresh_skill_jobs():
    global _scheduler
    if not _scheduler:
        return
    for job in list(_scheduler.get_jobs()):
        if job.id and str(job.id).startswith("skill_"):
            try:
                job.remove()
            except Exception:
                pass

    from services.db import db
    import aiosqlite

    rows = []
    try:
        async with aiosqlite.connect(settings.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT id, user_id, name, instruction FROM user_skills"
            )
            rows = [dict(r) for r in await cur.fetchall()]
    except Exception as e:
        logger.warning("Could not load skills: %s", e)
        return

    for s in rows:
        trigger = _parse_schedule(s["instruction"])
        if trigger is None:
            # default: every 15 min if no schedule words
            trigger = IntervalTrigger(minutes=max(1, int(getattr(settings, "SKILL_CHECK_MINUTES", 15) or 15)))
        jid = f"skill_{s['id']}"
        try:
            _scheduler.add_job(
                _run_skill,
                trigger=trigger,
                args=[s],
                id=jid,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("Scheduled %s -> %s | %s", jid, trigger, s.get("instruction", "")[:60])
        except Exception as e:
            logger.warning("Failed to schedule %s: %s", jid, e)


async def reload_skills_now():
    """Call after save_skill so new jobs start immediately."""
    await refresh_skill_jobs()


def start_scheduler(bot):
    global _scheduler
    if not getattr(settings, "ENABLE_SCHEDULER", True):
        logger.info("Scheduler disabled")
        return None
    set_bot(bot)
    _scheduler = AsyncIOScheduler(timezone="UTC")
    # refresh job list every minute so new skills appear fast
    _scheduler.add_job(
        refresh_skill_jobs,
        IntervalTrigger(minutes=1),
        id="refresh_skills",
        replace_existing=True,
    )
    _scheduler.start()
    asyncio.create_task(refresh_skill_jobs())
    logger.info("Scheduler started (1-min reload)")
    return _scheduler
