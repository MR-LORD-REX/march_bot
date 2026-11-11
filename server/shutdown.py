from DB.engine import engine
from shared.redis import redis_connector
from server.admin.panel.broadcast import stop_worker


async def on_shutdown():
    await stop_worker()
    try:
        from bot.services.lorebot.utils import close_tool_retriever

        await close_tool_retriever()
    except Exception:
        pass
    await engine.dispose()
    await redis_connector.disconnect()