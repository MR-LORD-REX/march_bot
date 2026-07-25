import logging
import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import unquote

from contextlib import asynccontextmanager
from aiogram.types import Update, InputMediaPhoto, BufferedInputFile, Message
from aiogram import Bot, Dispatcher

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import List, Optional

from bot.config.config import WEBHOOK_PATH, WEBHOOK_SECRET, WEBHOOK_URL, BOT_TOKEN
from bot.DB.engine import engine
from bot.DB.asyncsessions import session_factory

logger = logging.getLogger(__name__)

class TeammatePayload(BaseModel):
    characterId: str
    lightCone: str
    characterEidolon: int = 0
    lightConeSuperimposition: int = 1

class SubmitTeamRequest(BaseModel):
    slot: int
    teammates: List[TeammatePayload]
    chat_id: int          # GC (or DM) to post the result into
    message_id: int       # The original card message to edit
    tele_id: int          # Who submitted (for auth + DB lookup)
    init_data: str        # Raw Telegram initData string for verification

    @field_validator('teammates')
    @classmethod
    def must_be_three(cls, v):
        if len(v) != 3:
            raise ValueError('exactly 3 teammates required')
        return v



def _verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 300) -> bool:
    """Validates Telegram WebApp initData HMAC-SHA256 signature.
    Rejects data older than max_age_seconds (default 5 minutes).
    """
    try:
        parsed_raw = dict(pair.split('=', 1) for pair in init_data.split('&'))
        parsed = {k: unquote(v) for k, v in parsed_raw.items()}
        received_hash = parsed.pop('hash', None)
        if not received_hash:
            return False

        # Optional: reject stale initData
        auth_date = int(parsed.get('auth_date', 0))
        if time.time() - auth_date > max_age_seconds:
            logger.warning(f"initData is stale: age={int(time.time() - auth_date)}s")
            return False

        # Build the data-check string (sorted key=value pairs)
        data_check_string = '\n'.join(
            f'{k}={v}' for k, v in sorted(parsed.items())
        )

        secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, received_hash)
    except Exception as e:
        logger.error(f"initData verification failed: {e}")
        return False


def _add_submit_route(app: FastAPI, bot: Bot) -> None:
    """Mounts POST /submit_team on the given FastAPI app."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # narrow this to your GH Pages domain in prod
        allow_methods=["POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.post("/submit_team")
    async def submit_team(request: Request):
        try:
            body = await request.json()
            payload = SubmitTeamRequest(**body)
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))

        if not _verify_init_data(payload.init_data, BOT_TOKEN):
            raise HTTPException(status_code=401, detail="Invalid initData")

        from honkai_cards import Teammate
        from bot.services.cards import get_custom_card
        from bot.utils.images import image_to_tgFile
        from bot.handlers.cards.kb import make_back_kb
        from bot.DB.repo.game_ids_repo import GameIDs_repo
        from bot.DB.repo.cache_repo import CacheRepo

        teammates = [
            Teammate(
                characterId=tm.characterId,
                lightCone=tm.lightCone,
                characterEidolon=tm.characterEidolon,
                lightConeSuperimposition=tm.lightConeSuperimposition,
            )
            for tm in payload.teammates
        ]

        async with session_factory() as db_session:
            res = await get_custom_card(db_session, payload.tele_id, payload.slot, teammates)
            uid = await GameIDs_repo(db_session).get_active_UID(payload.tele_id)

        if not res or not getattr(res, 'card', None):
            raise HTTPException(status_code=500, detail="Card generation failed")

        bot_me = await bot.me()
        uid_val = uid.game_id if uid else 0
        kb = make_back_kb(payload.tele_id, payload.slot, uid_val, bot_me.username, payload.chat_id, payload.message_id)

        try:
            file = await image_to_tgFile(res.card)
            photo = InputMediaPhoto(media=file, caption="✦ Custom Team Card")
            m = await bot.edit_message_media(
                chat_id=payload.chat_id,
                message_id=payload.message_id,
                media=photo,
                reply_markup=kb
            )
            if isinstance(m, Message) and m.photo:
                file_id = m.photo[0].file_id
                async with session_factory() as cache_session:
                    await CacheRepo(cache_session).set_cache(payload.tele_id, file_id, cache_type='CHAR', data=str(payload.slot), slot=payload.slot)
                    await cache_session.commit()
            return JSONResponse({"ok": True})
        except Exception as e:
            logger.error(f"submit_team: failed to edit message: {e}")
            try:
                file = await image_to_tgFile(res.card)
                m = await bot.send_photo(
                    chat_id=payload.chat_id,
                    photo=file,
                    caption="✦ Custom Team Card",
                    reply_markup=kb
                )
                if isinstance(m, Message) and m.photo:
                    file_id = m.photo[0].file_id
                    async with session_factory() as cache_session:
                        await CacheRepo(cache_session).set_cache(payload.tele_id, file_id, cache_type='CHAR', data=str(payload.slot), slot=payload.slot)
                        await cache_session.commit()
                return JSONResponse({"ok": True, "note": "sent as new message"})
            except Exception as e2:
                logger.error(f"submit_team: fallback also failed: {e2}")
                raise HTTPException(status_code=500, detail=str(e2))


def setup_webhook(bot: Bot, dp: Dispatcher):

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            current = await bot.get_webhook_info()
            if current.url:
                await bot.delete_webhook(drop_pending_updates=True)

            await bot.set_webhook(
                url=WEBHOOK_URL + WEBHOOK_PATH,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True
            )
            logger.info(f"Webhook set to {WEBHOOK_URL + WEBHOOK_PATH}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}", exc_info=True)
            raise
        yield
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.session.close()
        await engine.dispose()
        logger.info("Bot session and DB closed")

    app = FastAPI(title="Bot Webhook", lifespan=lifespan)
    _add_submit_route(app, bot)

    @app.post(WEBHOOK_PATH)
    async def handle_update(request: Request):
        try:
            token = request.headers.get("X-Telegram-Bot-API-Secret-Token")
            if token != WEBHOOK_SECRET:
                logger.warning("Invalid webhook secret token")
                raise HTTPException(status_code=401, detail="Unauthorized")

            update = await request.json()
            update = Update(**update)
            await dp.feed_update(bot=bot, update=update)
            return JSONResponse({"ok": True})

        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    @app.head("/")
    async def head():
        return JSONResponse({"status": "ok"})

    @app.get("/")
    async def _get():
        return JSONResponse({"status": "ok"})

    return app


def setup_polling(bot: Bot, dp: Dispatcher):

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        polling_task = None
        try:
            polling_task = asyncio.create_task(dp.start_polling(bot))
            yield
        finally:
            if polling_task:
                polling_task.cancel()
                try:
                    await polling_task
                except asyncio.CancelledError:
                    pass
            await bot.session.close()
            await engine.dispose()
            logger.info("Bot polling stopped and session closed")

    app = FastAPI(title="Bot Polling", lifespan=lifespan)
    _add_submit_route(app, bot)

    @app.head("/")
    async def head():
        return JSONResponse({"status": "ok"})

    @app.get("/")
    async def _get():
        return JSONResponse({"status": "ok"})

    return app