from bot.DB.engine import engine
from bot.redis_store import redis_connector

async def on_shutdown():
    try:
        from bot.services.lorebot.utils import close_tool_retriever
        await close_tool_retriever()
    except Exception:
        pass
    await engine.dispose()
    await redis_connector.disconnect()