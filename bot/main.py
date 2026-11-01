import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import uvicorn

from config.settings import settings
from services.db import db
from handlers.commands import router as commands_router
from handlers.chat import router as chat_router
from handlers.media import router as media_router
from handlers.inline import router as inline_router
from handlers.callbacks import router as callbacks_router
from handlers.payments import router as payments_router
from web.dashboard import app as fastapi_app
from services.scheduler import start_scheduler, reload_skills_now

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("obra")

os.makedirs("data", exist_ok=True)
os.makedirs(settings.CHROMA_PATH, exist_ok=True)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    # Order matters: aiogram stops at the first matching handler, so specific
    # routers (secretary deep-link, extras, commands incl. the unknown-command
    # catch-all) must come before the generic chat/media routers.
    try:
        from handlers.secretary import router as secretary_router
        dp.include_router(secretary_router)
    except Exception as e:
        logger.warning("secretary router skipped: %s", e)
    try:
        from handlers.extras import router as extras_router
        dp.include_router(extras_router)
    except Exception as e:
        logger.warning("extras router skipped: %s", e)
    dp.include_router(commands_router)
    dp.include_router(chat_router)
    dp.include_router(media_router)
    dp.include_router(inline_router)
    dp.include_router(callbacks_router)
    dp.include_router(payments_router)
    try:
        from handlers.webapp import router as webapp_router
        dp.include_router(webapp_router)
    except Exception as e:
        logger.warning("webapp router skipped: %s", e)
    return dp


ALLOWED_UPDATES = [
    "message", "callback_query", "inline_query",
    "business_connection", "business_message",
    "edited_business_message", "deleted_business_messages",
    "pre_checkout_query", "edited_message",
]


async def run_polling(bot: Bot, dp: Dispatcher):
    me = await bot.get_me()
    logger.info(f"obra polling as @{me.username}")
    # Resilience: a single network/API error must not kill the bot + dashboard.
    while True:
        try:
            await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("polling crashed (%s) — restarting in 5s", e)
            await asyncio.sleep(5)


async def run_webhook(bot: Bot, dp: Dispatcher):
    await bot.set_webhook(
        url=settings.WEBHOOK_URL.rstrip("/") + settings.WEBHOOK_PATH,
        secret_token=settings.WEBHOOK_SECRET or None,
        drop_pending_updates=True,
    )
    me = await bot.get_me()
    logger.info(f"obra webhook as @{me.username} → {settings.WEBHOOK_URL}")

    aio = web.Application()
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.WEBHOOK_SECRET or None,
    ).register(aio, path=settings.WEBHOOK_PATH)
    setup_application(aio, dp, bot=bot)

    runner = web.AppRunner(aio)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8081)
    await site.start()
    logger.info("Webhook server on :8081 (put reverse-proxy in front)")
    await asyncio.Event().wait()


async def run_dashboard():
    port = int(os.environ.get("PORT") or settings.DASHBOARD_PORT or 8080)
    host = settings.DASHBOARD_HOST or "0.0.0.0"
    logger.info("Dashboard/uptime on %s:%s", host, port)
    config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def self_ping_loop():
    """Keep Render free tier awake by pinging /health every 4 minutes."""
    url = (os.environ.get("RENDER_EXTERNAL_URL") or getattr(settings, "PUBLIC_URL", "") or "").rstrip("/")
    if not url:
        logger.info("self_ping off (set PUBLIC_URL or RENDER_EXTERNAL_URL)")
        return
    import aiohttp
    endpoint = url + "/health"
    logger.info("self_ping → %s", endpoint)
    await asyncio.sleep(20)
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(endpoint, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    logger.debug("self_ping %s", r.status)
        except Exception as e:
            logger.debug("self_ping: %s", e)
        await asyncio.sleep(240)


async def _run_forever(coro_factory, name: str):
    """Run a task forever, restarting it if it crashes."""
    while True:
        try:
            await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("%s crashed (%s) — restarting in 5s", name, e)
            await asyncio.sleep(5)


async def main():
    token = (settings.BOT_TOKEN or "").strip()
    if not token or ":" not in token or len(token) < 20:
        raise SystemExit(
            "❌ BOT_TOKEN is missing/invalid. Get one from @BotFather and put it "
            "in .env (BOT_TOKEN=123456:ABC...) — see .env.example"
        )
    await db.init()
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()
    start_scheduler(bot)
    try:
        await reload_skills_now()
    except Exception as e:
        logger.warning("initial skill load: %s", e)
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Start obra"),
            BotCommand(command="help", description="Help & examples"),
            BotCommand(command="clear", description="Clear chat history"),
            BotCommand(command="lang", description="Set reply language"),
            BotCommand(command="memory", description="Show saved memory"),
            BotCommand(command="forget", description="Forget memory"),
            BotCommand(command="skill", description="List scheduled skills"),
            BotCommand(command="setkey", description="Set your own LLM key (BYOK)"),
            BotCommand(command="project", description="Name this chat project"),
            BotCommand(command="tts", description="Voice replies on/off"),
            BotCommand(command="usage", description="Usage & limits"),
            BotCommand(command="cancel", description="Cancel pending actions"),
            BotCommand(command="ping", description="Ping"),
            BotCommand(command="status", description="Bot status"),
        ])
    except Exception:
        pass
    mode = (settings.MODE or "polling").lower()
    logger.info(f"Starting obra mode={mode}")
    try:
        from services.tools import TOOLS
        chain = settings.provider_chain()
        logger.info("self_check tools=%s rich=%s providers=%s",
                    len(TOOLS), getattr(settings, "USE_RICH_MESSAGES", True),
                    [p["name"] for p in chain] or ["NONE — add GROQ_API_KEY!"])
    except Exception as e:
        logger.warning("self_check: %s", e)

    if mode == "webhook" and settings.WEBHOOK_URL:
        await asyncio.gather(
            _run_forever(lambda: run_webhook(bot, dp), "webhook"),
            _run_forever(run_dashboard, "dashboard"),
            _run_forever(self_ping_loop, "self_ping"),
        )
    else:
        await asyncio.gather(
            _run_forever(lambda: run_polling(bot, dp), "polling"),
            _run_forever(run_dashboard, "dashboard"),
            _run_forever(self_ping_loop, "self_ping"),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
