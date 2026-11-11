from __future__ import annotations

import logging

from DB.repo.cmd_meta_repo import CommandMetaRepo
from DB.asyncsessions import session_factory
from bot.handlers.routers import setup_routers
from bot.services.live_cards import send_daily_reminder
from shared.scheduling.scheduler import scheduled_tasks_on_startup
from shared.config.settings import scheduler
from shared.redis import redis_connector
from shared.runtime import bot_runtime


logger = logging.getLogger(__name__)


async def add_commands():
    from shared.config.settings import cmdavailability, users_record, groups_record
    from shared.runtime import load_users, load_groups

    cmds = setup_routers(bot_runtime.dispatcher)
    if cmds:
        try:
            async with session_factory() as session:
                await CommandMetaRepo(session).add_commands(cmds)
            async with session_factory() as session:
                status = await CommandMetaRepo(session).get_all_commands()
                cmdavailability.load(status)
                await load_users(session, users_record)
                await load_groups(session, groups_record)
                logger.info("commands added and cache loaded successfully")
        except Exception as e:
            logger.error(f"error adding commands in startup: {e}")


async def init_lorebot():
    """Load the lore chatbot's settings and key pool, seeding a key from
    GEMINI_API_KEY if the DB has none so an existing .env keeps working."""
    from shared.config.settings import GEMINI_API_KEY
    from bot.services.lorebot.config import LORE_MODELS
    from bot.services.lorebot.runtime import reload_settings, reload_pool
    from DB.repo.ai_api_repo import AiApiRepo

    try:
        await reload_settings()

        async with session_factory() as session:
            repo = AiApiRepo(session)
            existing = await repo.get_all_with_models()

            if not existing and GEMINI_API_KEY:
                await repo.add_key("env", GEMINI_API_KEY, LORE_MODELS)
                await session.commit()
                logger.info("seeded lore api key 'env' from GEMINI_API_KEY")
            elif existing:
                # Backfill buckets for models added to LORE_MODELS since these
                # keys were stored.
                created = await repo.sync_models(LORE_MODELS)
                if created:
                    await session.commit()
                    logger.info(f"backfilled {created} model buckets")

        count = await reload_pool()
        if not count:
            logger.warning(
                "lore chatbot has no API keys; /ask will report as unavailable"
            )
    except Exception as e:
        logger.error(f"error initialising lore chatbot: {e}")


async def lore_quota_watchdog():
    """Cheap periodic check that survives restarts."""
    from bot.services.lorebot.runtime import (
        settings as lore_settings,
        quota_manager,
        daily_quota_reset,
        on_rpd_exhausted,
    )
    from bot.services.lorebot.quota import pacific_day

    try:
        if lore_settings.rpd_disabled:
            if lore_settings.rpd_disabled_on != pacific_day():
                await daily_quota_reset()
            return

        if quota_manager.slots and await quota_manager.is_daily_exhausted():
            await on_rpd_exhausted()
    except Exception as e:
        logger.error(f"lore quota watchdog error: {e}")


async def on_startup(*_args, **_kwargs):
    """Initialise runtime services once, before polling starts."""
    await redis_connector.connect()
    await add_commands()
    await init_lorebot()

    # Hooks may be re-entered by aiogram during start_polling. The scheduler
    # registry is process-wide, so only register its jobs once.
    if not scheduler.get_task("lore_quota_watchdog"):
        scheduler.add_interval(
            task_id="lore_quota_watchdog",
            task_name="lore chatbot quota watchdog",
            coro=lore_quota_watchdog,
            interval=120,
            delay=60,
            max_errors=10,
        )
    if not scheduler.get_task("daily_reminder"):
        scheduler.add_daily(
            task_id="daily_reminder",
            task_name="daily reminder for users",
            coro=send_daily_reminder,
            daily_at=(19, 0, 0),  # UTC time for IST 00:30 AM
            max_errors=2,
        )

    try:
        await scheduled_tasks_on_startup()
    except Exception as e:
        logger.error(f"error restoring scheduled tasks: {e}")