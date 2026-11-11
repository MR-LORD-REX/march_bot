from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from fastapi import FastAPI

from bot.api.webhook import create_app
from bot.DB.engine import engine

logger = logging.getLogger(__name__)


def setup_polling(bot: Bot, dp: Dispatcher) -> FastAPI:
    app = create_app(bot, dp=None, mode="polling")

    @asynccontextmanager
    async def polling_lifespan(_app: FastAPI):
        task = asyncio.create_task(dp.start_polling(bot))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await bot.session.close()
            await engine.dispose()
            logger.info("Bot polling stopped")

    app.router.lifespan_context = polling_lifespan
    return app