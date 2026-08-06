"""Reliable skill scheduler for Obra (APScheduler + safety net loop)."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings

logger = logging.getLogger("obra.scheduler")
_scheduler: Optional[AsyncIOScheduler] = None
_bot = None
_last_run: Dict[int, float] = {}  # skill_id -> unix ts


def set_bot(bot):
    global _bot
    _bot = bot


def _parse_interval_seconds(instruction: str) -> Optional[int]:
    """Return interval in seconds, or None for cron-only patterns."""
    t = (instruction or "").lower()

    if re.search(r"every\s+minute\b", t) or re.search(r"every\s+1\s*m(in|ins|inute|inutes)?\b", t):
        return 60

    m = re.search(r"every\s+(\d+)\s*(second|seconds|sec|secs)\b", t)
    if m:
        return max(30, int(m.group(1)))

    m = re.search(r"every\s+(\d+)\s*(minute|minutes|min|mins)\b", t)
    if m:
        return max(60, int(m.group(1)) * 60)

    m = re.search(r"every\s+(\d+)\s*(hour|hours|hr|hrs)\b", t)
    if m:
        return max(3600, int(m.group(1)) * 3600)

    if "hourly" in t:
        return 3600

    return None


def _parse_cron(instruction: str):
    t = (instruction or "").lower()
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


def _parse_schedule(instruction: str):
    secs = _parse_interval_seconds(instruction)
    if secs is not None:
        return IntervalTrigger(seconds=secs)
    cron = _parse_cron(instruction)
    if cron is not None:
        return cron
    # default 15 min
    default_m = max(1, int(getattr(settings, "SKILL_CHECK_MINUTES", 15) or 15))
    return IntervalTrigger(seconds=default_m * 60)


async def _run_skill(skill: dict):
    global _bot, _last_run
    if not _bot:
        logger.warning("Skill skipped — bot not set")
        return
    user_id = skill["user_id"]
    skill_id = skill.get("id")
    name = skill.get("name") or "skill"
    instruction = skill.get("instruction") or ""
    logger.info("Running skill id=%s user=%s: %s", skill_id, user_id, name)

    if skill_id is not None:
        _last_run[int(skill_id)] = datetime.now(timezone.utc).timestamp()

    try:
        low = instruction.lower()
        # Strip schedule prefix for message body
        body = re.sub(
            r"^(every\s+\d+\s*(minute|minutes|min|mins|hour|hours|second|seconds|sec|secs)|every\s+minute|hourly|daily)\s*[:,\-]?\s*",
            "",
            instruction,
            flags=re.I,
        ).strip()

        if any(x in low for x in ("send me", "message me", "ping me", "remind me", "say ")):
            text = body or f"Scheduled ping from **{name}**"
            await _bot.send_message(
                user_id,
                f"⏰ <b>{name}</b>\n\n{text}",
                parse_mode="HTML",
            )
        else:
            from services.llm import chat_completion, AGENTS
            result = await chat_completion(
                messages=[{
                    "role": "user",
                    "content": (
                        f"Execute this scheduled skill now.\n"
                        f"Name: {name}\nInstruction: {instruction}\n"
                        f"Produce a short useful update."
                    ),
                }],
                system=AGENTS.get("default", "") + "\nScheduled skill — be concise.",
                temperature=0.5,
                max_tokens=600,
            )
            text = result.get("content") or f"Skill `{name}` ran."
            await _bot.send_message(
                user_id,
                f"⏰ <b>{name}</b>\n\n{text[:3500]}",
                parse_mode="HTML",
            )
        try:
            from services.db import db
            await db.log_event(user_id, user_id, "skill_run", {"skill": name, "id": skill_id})
        except Exception:
            pass
        logger.info("Skill id=%s delivered to %s", skill_id, user_id)
    except Exception as e:
        logger.exception("Skill failed id=%s: %s", skill_id, e)
        try:
            await _bot.send_message(user_id, f"⏰ Skill failed: {e}")
        except Exception:
            pass


async def _load_skills():
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
        logger.warning("Load skills failed: %s", e)
    return rows


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

    rows = await _load_skills()
    now = datetime.now(timezone.utc)
    for s in rows:
        trigger = _parse_schedule(s["instruction"])
        jid = f"skill_{s['id']}"
        # First fire soon (30s) so user sees it works, then follow interval
        next_run = now + timedelta(seconds=30)
        try:
            _scheduler.add_job(
                _run_skill,
                trigger=trigger,
                args=[s],
                id=jid,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                next_run_time=next_run,
            )
            logger.info("Scheduled %s next=%s | %s", jid, next_run.isoformat(), s.get("instruction", "")[:80])
        except Exception as e:
            logger.warning("Schedule fail %s: %s", jid, e)

    logger.info("Active skill jobs: %s", len([j for j in _scheduler.get_jobs() if str(j.id).startswith("skill_")]))


async def reload_skills_now():
    await refresh_skill_jobs()


async def _safety_loop():
    """
    Backup: if APScheduler misses, run interval skills when due.
    Checks every 20 seconds.
    """
    await asyncio.sleep(15)
    while True:
        try:
            rows = await _load_skills()
            now = datetime.now(timezone.utc).timestamp()
            for s in rows:
                secs = _parse_interval_seconds(s.get("instruction") or "")
                if not secs:
                    continue
                sid = int(s["id"])
                last = _last_run.get(sid, 0)
                if last == 0:
                    # let APScheduler handle first fire; mark lightly
                    continue
                if now - last >= secs - 5:
                    # due
                    if sid not in _last_run or now - _last_run.get(sid, 0) >= secs - 5:
                        await _run_skill(s)
        except Exception as e:
            logger.debug("safety loop: %s", e)
        await asyncio.sleep(20)


def start_scheduler(bot):
    global _scheduler
    if not getattr(settings, "ENABLE_SCHEDULER", True):
        logger.info("Scheduler disabled via ENABLE_SCHEDULER=false")
        return None
    set_bot(bot)
    try:
        _scheduler = AsyncIOScheduler(timezone="UTC")
        _scheduler.add_job(
            refresh_skill_jobs,
            IntervalTrigger(seconds=60),
            id="refresh_skills",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=5),
        )
        _scheduler.start()
        logger.info("APScheduler started")
    except Exception as e:
        logger.exception("APScheduler failed to start: %s", e)
        _scheduler = None

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(refresh_skill_jobs())
        loop.create_task(_safety_loop())
        logger.info("Skill reload + safety loop tasks scheduled")
    except RuntimeError:
        logger.warning("No running loop yet for scheduler tasks")
    return _scheduler
