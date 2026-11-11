from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bot.admin.panel.routes import router as admin_panel_router
from bot.api.routes.mini_app import router as mini_app_router
from bot.config.config import CORS_ORIGINS, WEBHOOK_PATH, WEBHOOK_SECRET, WEBHOOK_URL
from bot.DB.engine import engine

logger = logging.getLogger(__name__)


def _add_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Telegram-Bot-API-Secret-Token"],
        allow_credentials=False,
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


def setup_webhook(bot: Bot, dp: Dispatcher) -> FastAPI:
    app = create_app(bot, dp, mode="webhook")

    @asynccontextmanager
    async def webhook_lifespan(_app: FastAPI):
        current = await bot.get_webhook_info()
        if current.url:
            await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(
            url=WEBHOOK_URL + WEBHOOK_PATH,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logger.info("Webhook set to %s%s", WEBHOOK_URL, WEBHOOK_PATH)
        await dp.emit_startup(bot=bot)
        try:
            yield
        finally:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.emit_shutdown(bot=bot)
            await bot.session.close()
            await engine.dispose()

    app.router.lifespan_context = webhook_lifespan
    return app