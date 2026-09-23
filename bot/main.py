"""Bot entrypoint — runs aiogram polling and the aiohttp webapp concurrently.

The Mini App (webapp) must serve the circular-video-note editor while the bot
polls updates, so both live in the same asyncio loop.
"""
import asyncio
import logging

from dotenv import load_dotenv
load_dotenv()

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import cfg
from bot.database.db import Database, db, set_db
from bot.handlers import actions, media, start
from bot.services.bot_registry import set_bot
from bot.utils.helpers import ensure_dir
from bot.webapp import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    cfg.validate()
    ensure_dir(cfg.work_dir)

    database = Database(cfg.db_path)
    set_db(database)
    await database.init()

    bot = Bot(token=cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    set_bot(bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    dp.include_router(media.router)
    dp.include_router(actions.router)

    runner = None
    sweeper = None
    if cfg.webapp_url:
        app = create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        host = getattr(cfg, "webapp_host", None) or "0.0.0.0"
        site = web.TCPSite(runner, host, cfg.port)
        await site.start()
        logger.info("Webapp up on http://%s:%s", host, cfg.port)
    else:
        logger.warning("WEBAPP_URL not set — Mini App (video note editor) disabled.")

    sweeper = asyncio.create_task(_sweeper())

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if sweeper:
            sweeper.cancel()
        if runner:
            await runner.cleanup()
        handle = db()
        if handle is not None and getattr(handle, "_conn", None) is not None:
            try:
                await handle._conn.close()
            except Exception:
                pass
        await bot.session.close()


async def _sweeper():
    """Periodically drop expired pending items and stored media sessions."""
    from bot.services import nav
    from bot.services.pending import sweep_pending
    from bot.services.sessions import sweep_expired_sessions

    while True:
        try:
            sweep_pending()
            await sweep_expired_sessions(cfg.session_ttl)
            nav.sweep()
        except Exception:
            logger.exception("periodic sweep failed")
        await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass