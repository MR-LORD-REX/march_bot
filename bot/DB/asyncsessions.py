from sqlalchemy.ext.asyncio import AsyncSession , async_sessionmaker

from bot.DB.engine import engine

session_factory=async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)