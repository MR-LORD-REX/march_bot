from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from DB.bootstrap import ensure_schema_ready
from DB.engine import engine
from server.admin.panel.routes import router as admin_panel_router
from server.routes.mini_app import router as mini_app_router
from server.shutdown import on_shutdown
from server.startup import on_startup
from shared.config.settings import (
    BACKEND_TYPE,
    BACKEND_URL,
    CORS_ORIGINS,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
    WEBHOOK_URL,
)

logger = logging.getLogger(__name__)


def _add_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Telegram-Bot-API-Secret-Token"],
        allow_credentials=True,
    )


def create_app(bot: Bot, dp: Dispatcher | None = None, mode: str = "webhook") -> FastAPI:
    app = FastAPI(title="HSR Bot API", docs_url=None, redoc_url=None, openapi_url=None)
    _add_cors(app)
    app.include_router(mini_app_router)
    app.include_router(admin_panel_router)
    app.state.bot = bot
    app.state.dispatcher = dp
    app.state.mode = mode

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/api/config")
    async def public_config():
        # Public, non-secret runtime configuration for the Mini App / future
        # React client. Secrets stay server-side.
        return {
            "backend_url": BACKEND_URL,
            "backend_type": BACKEND_TYPE,
            "mode": mode,
        }

    @app.middleware("http")
    async def panel_security_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; style-src 'self'; script-src 'self'; "
                "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
            )
        return response

    if dp is not None:

        @app.post(WEBHOOK_PATH)
        async def handle_update(request: Request):
            supplied = request.headers.get("X-Telegram-Bot-API-Secret-Token")
            if not WEBHOOK_SECRET or supplied != WEBHOOK_SECRET:
                raise HTTPException(status_code=401, detail="Unauthorized")
            try:
                await dp.feed_update(bot=bot, update=Update(**(await request.json())))
            except Exception:
                logger.exception("webhook update failed")
                return JSONResponse({"ok": False}, status_code=500)
            return {"ok": True}

    return app


@asynccontextmanager
async def _runtime_lifespan(_app: FastAPI):
    """Run schema and service startup once, then hold the runtime open."""
    await asyncio.to_thread(ensure_schema_ready)
    await on_startup()
    logger.info("startup complete")
    try:
        yield
    finally:
        await on_shutdown()
        await engine.dispose()


def setup_polling(bot: Bot, dp: Dispatcher) -> FastAPI:
    app = create_app(bot, dp=None, mode="polling")

    @asynccontextmanager
    async def polling_lifespan(_app: FastAPI):
        polling_task: asyncio.Task[Any] | None = None
        try:
            async with _runtime_lifespan(_app):
                polling_task = asyncio.create_task(
                    dp.start_polling(bot), name="telegram-polling"
                )
                await asyncio.sleep(0)
                if polling_task.done():
                    polling_task.result()
                    raise RuntimeError("Telegram polling exited during startup")
                yield
        finally:
            if polling_task is not None:
                polling_task.cancel()
                try:
                    await polling_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("Telegram polling stopped unexpectedly")
            # Close the bot session only after polling has fully stopped, or
            # aiohttp can log "Connector is closed" from the polling task.
            await bot.session.close()
            logger.info("Bot polling stopped")

    app.router.lifespan_context = polling_lifespan
    return app


def setup_webhook(bot: Bot, dp: Dispatcher) -> FastAPI:
    app = create_app(bot, dp, mode="webhook")

    @asynccontextmanager
    async def webhook_lifespan(_app: FastAPI):
        try:
            async with _runtime_lifespan(_app):
                current = await bot.get_webhook_info()
                if current.url:
                    await bot.delete_webhook(drop_pending_updates=True)
                await bot.set_webhook(
                    url=WEBHOOK_URL + WEBHOOK_PATH,
                    secret_token=WEBHOOK_SECRET,
                    drop_pending_updates=True,
                )
                logger.info("Webhook set to %s%s", WEBHOOK_URL, WEBHOOK_PATH)
                yield
        finally:
            await bot.delete_webhook(drop_pending_updates=True)
            await bot.session.close()

    app.router.lifespan_context = webhook_lifespan
    return app