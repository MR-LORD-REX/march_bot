from sqlalchemy.ext.asyncio import create_async_engine , AsyncEngine

from bot.config.config import DB_URL , ENV

engine:AsyncEngine = create_async_engine(
    DB_URL,
    echo=ENV=='dev',
    pool_size=15,
    max_overflow=5
)