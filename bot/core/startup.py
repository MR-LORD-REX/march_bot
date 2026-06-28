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
            
async def on_startup():
    await init_db()
    await redis_connector.connect()
    await add_commands()
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