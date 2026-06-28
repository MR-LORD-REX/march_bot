from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import uvicorn

from bot.middleware.dbm import DBMiddleware
from bot.middleware.ratelimit import RateLimitMiddleware
from bot.middleware.commands import CommandChecker
from bot.config.config import BOT_TOKEN , MODE , ENV , PORT , cmdavailability
from bot.core.startup import on_startup
from bot.core.shutdown import on_shutdown
from bot.core.webhook import setup_webhook , setup_polling


dp=Dispatcher()
dp.message.middleware(RateLimitMiddleware())
dp.message.middleware(CommandChecker(cmdavailability))
dp.message.middleware(DBMiddleware())
dp.callback_query.middleware(DBMiddleware())
dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)


bot=Bot(token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

async def start():
    if MODE=="polling":
        app = setup_polling(bot,dp)
        
        config=uvicorn.Config(
            app=app,
            host="0.0.0.0" if ENV == "prod" else "localhost",
            port=int(PORT),
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
    elif MODE=="webhook":
        app = setup_webhook(bot,dp)
        
        config=uvicorn.Config(
            app=app,
            host="0.0.0.0" if ENV == "prod" else "localhost",
            port=int(PORT),
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
    else:
        print("invalid mode")