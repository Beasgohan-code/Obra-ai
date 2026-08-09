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
from handlers.secretary import router as secretary_router
from web.dashboard import app as fastapi_app
from services.scheduler import start_scheduler, reload_skills_now

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("obra")

os.makedirs("data", exist_ok=True)
os.makedirs(settings.CHROMA_PATH, exist_ok=True)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(commands_router)
    dp.include_router(chat_router)
    dp.include_router(media_router)
    dp.include_router(inline_router)
    dp.include_router(callbacks_router)
    dp.include_router(secretary_router)
    return dp


async def run_polling(bot: Bot, dp: Dispatcher):
    me = await bot.get_me()
    logger.info(f"obra polling as @{me.username}")
    await dp.start_polling(
        bot,
        allowed_updates=[
            "message", "callback_query", "inline_query",
            "business_connection", "business_message",
            "edited_business_message", "deleted_business_messages",
        ],
    )


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
    # Render injects PORT — must bind to it for Web Service health checks
    port = int(os.environ.get("PORT") or settings.DASHBOARD_PORT or 8080)
    host = settings.DASHBOARD_HOST or "0.0.0.0"
    logger.info("Dashboard/uptime listening on %s:%s", host, port)
    config = uvicorn.Config(
        fastapi_app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def self_ping_loop():
    """Optional: ping our own /health so Render free tier stays awake."""
    url = (os.environ.get("RENDER_EXTERNAL_URL") or getattr(settings, "PUBLIC_URL", "") or "").rstrip("/")
    if not url:
        logger.info("self_ping disabled (set RENDER_EXTERNAL_URL or PUBLIC_URL)")
        return
    import aiohttp
    endpoint = url + "/health"
    logger.info("self_ping enabled → %s every 4 min", endpoint)
    await asyncio.sleep(30)
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    logger.debug("self_ping %s", resp.status)
        except Exception as e:
            logger.debug("self_ping fail: %s", e)
        await asyncio.sleep(240)  # 4 minutes


async def main():
    await db.init()
    bot = Bot(
        token=settings.BOT_TOKEN,
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
            BotCommand(command="start", description="Start"),
            BotCommand(command="help", description="Help"),
            BotCommand(command="clear", description="Clear chat memory"),
            BotCommand(command="skill", description="Schedules / reminders"),
            BotCommand(command="lang", description="Language"),
            BotCommand(command="memory", description="Your memory"),
        ])
    except Exception:
        pass
    mode = (settings.MODE or "polling").lower()
    logger.info(f"Starting obra mode={mode}")
    # startup self-check
    try:
        from services.tools import TOOLS
        from services.scheduler import start_scheduler as _ss
        logger.info("self_check tools=%s rich=%s scheduler=%s secretary=on",
                    len(TOOLS),
                    getattr(settings, "USE_RICH_MESSAGES", True),
                    getattr(settings, "ENABLE_SCHEDULER", True))
    except Exception as e:
        logger.warning("self_check: %s", e)

    if mode == "webhook" and settings.WEBHOOK_URL:
        await asyncio.gather(run_webhook(bot, dp), run_dashboard(), self_ping_loop())
    else:
        await asyncio.gather(run_polling(bot, dp), run_dashboard(), self_ping_loop())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
