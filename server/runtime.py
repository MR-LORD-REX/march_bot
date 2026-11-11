from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.middleware.commands import CommandChecker
from bot.middleware.dbm import DBMiddleware
from bot.middleware.ratelimit import RateLimitMiddleware
from server.app import setup_polling, setup_webhook
from server.shutdown import on_shutdown
from server.startup import on_startup
from shared.config.settings import BOT_TOKEN, ENV, MODE, PORT, cmdavailability
from shared.runtime import bot_runtime

logger = logging.getLogger(__name__)

dp = Dispatcher()
dp.message.middleware(RateLimitMiddleware())
dp.message.middleware(DBMiddleware())
dp.message.middleware(CommandChecker(cmdavailability))
dp.callback_query.middleware(DBMiddleware())

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

# Shared services read the running bot through this accessor instead of
# importing this server module, keeping bot -> shared and server -> bot.
bot_runtime.bind(bot, dp)


async def start() -> None:
    if MODE == "polling":
        app = setup_polling(bot, dp)
    elif MODE == "webhook":
        app = setup_webhook(bot, dp)
    else:
        raise RuntimeError(f"invalid MODE={MODE!r}; expected 'polling' or 'webhook'")

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0" if ENV == "prod" else "localhost",
        port=int(PORT),
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()