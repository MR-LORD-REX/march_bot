from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.DB.asyncsessions import session_factory

class DBMiddleware(BaseMiddleware):
    async def __call__(
        self,
        hander: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any]
    )->Any:
        async with session_factory() as session:
            data['db_session']=session
            return await hander(event,data)
        