from bot.DB.engine import engine
from bot.DB.base import base as Base
from bot.DB.repo.cmd_meta_repo import CommandMetaRepo
from bot.DB.asyncsessions import session_factory
from bot.handlers.routers import setup_routers
from bot.services.live_cards import send_daily_reminder
from bot.utils.scheduler import scheduled_tasks_on_startup
from bot.config.config import ENV , scheduler
from bot.redis_store import redis_connector



import logging
import sys

base=Base()
logger=logging.getLogger(__name__)

async def init_db():
    try:
        async with engine.begin() as con:
            await con.run_sync(base.metadata.create_all)
            logger.info("databases created succesfully")

    except Exception as e:
        logger.error(f"error in startup : {e}")
        sys.exit(1)
        
async def add_commands():
    from bot.core.main import dp
    from bot.config.config import cmdavailability , users_record, groups_record
    from bot.services.UG_cache import load_users, load_groups
    cmds=setup_routers(dp)
    if cmds:
        try:
            async with session_factory() as session:
                await CommandMetaRepo(session).add_commands(cmds)
            async with session_factory() as session:
                status=await CommandMetaRepo(session).get_all_commands()
                cmdavailability.load(status)
                await load_users(session, users_record)
                await load_groups(session, groups_record)
                logger.info("commands added and cache loaded successfully")
        except Exception as e:
            logger.error(f"error adding commands in startup: {e}")
            
async def init_lorebot():
    """Load the lore chatbot's settings and key pool, seeding a key from
    GEMINI_API_KEY if the DB has none so an existing .env keeps working."""
    from bot.config.config import GEMINI_API_KEY
    from bot.services.lorebot.config import LORE_MODELS
    from bot.services.lorebot.runtime import reload_settings, reload_pool
    from bot.DB.repo.ai_api_repo import AiApiRepo

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
    """Cheap periodic check that survives restarts.

    Two jobs: lift a quota-imposed /ask disable once the Pacific day rolls
    over, and catch daily exhaustion that happened while nobody was asking.
    A fire-once-daily job would miss both if the bot restarted at the wrong
    moment, which on a free dyno is most moments.
    """
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


async def on_startup():
    await init_db()
    await redis_connector.connect()
    await add_commands()
    await init_lorebot()
    scheduler.add_interval(
        task_id="lore_quota_watchdog",
        task_name="lore chatbot quota watchdog",
        coro=lore_quota_watchdog,
        interval=120,
        delay=60,
        max_errors=10,
    )
    scheduler.add_daily(
        task_id="daily_reminder",
        task_name="daily reminder for users",
        coro=send_daily_reminder,
        daily_at=(19, 0, 0),  # UTC time for IST 00:30 AM
        max_errors=2
    )
    # scheduler.add_weekly(
    #     task_id="weekly_reminder",
    #     task_name="weekly reminder for users",
    #     coro=send_weekly_reminder,
    #     weekly_schedule={"sunday":(6,30)} # UTC time for IST Sunday 12:00 PM
    # )
    # scheduler.add_daily(
    #     task_id="perform_daily_tasks",
    #     task_name="perform daily tasks for users",
    #     coro=perform_daily_tasks,
    #     daily_at=(4, 30, 0),  # UTC time for IST 10:00 AM 
    #     max_errors=1
    # )
    await scheduled_tasks_on_startup()