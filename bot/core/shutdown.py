from bot.DB.engine import engine
from bot.redis_store import redis_connector

async def on_shutdown():
    await engine.dispose()
    await redis_connector.disconnect()