from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from bot.auth.handoff import HandoffError, claim_handoff, create_handoff, legacy_handoff
from bot.auth.mini_app import encode_handoff
from bot.auth.telegram_webapp import InitDataError, verify_init_data
from bot.config.config import BOT_TOKEN
from bot.DB.asyncsessions import session_factory
from bot.DB.repo.cache_repo import CacheRepo
from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.DB.repo.user_repo import UserRepo
from bot.handlers.cards.kb import make_back_kb

router = APIRouter(tags=["mini-app"])


class TeammatePayload(BaseModel):
    characterId: str
    lightCone: str
    characterEidolon: int = 0
    lightConeSuperimposition: int = 1


class SubmitTeamRequest(BaseModel):
    slot: int = Field(gt=0)
    teammates: list[TeammatePayload]
    init_data: str
    handoff: str | None = None
    # Transitional fields from the deployed Mini App. They are accepted only
    # when the signed Telegram user is valid; never used as identity.
    tele_id: int | None = None
    chat_id: int | None = None
    message_id: int | None = None


@router.post("/submit_team")
async def submit_team(body: SubmitTeamRequest, request: Request):
    try:
        user = verify_init_data(body.init_data, BOT_TOKEN)
    except InitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if len(body.teammates) != 3:
        raise HTTPException(status_code=422, detail="exactly 3 teammates required")

    try:
        if body.handoff:
            handoff = await claim_handoff(body.handoff, user.telegram_id)
        else:
            if body.chat_id is None or body.message_id is None:
                raise HandoffError("missing handoff")
            active_uid = await _active_uid(user.telegram_id)
            if active_uid is None:
                raise HandoffError("user has no active UID")
            handoff = await legacy_handoff(
                telegram_id=user.telegram_id,
                uid=active_uid,
                slot=body.slot,
                chat_id=body.chat_id,
                message_id=body.message_id,
            )
    except HandoffError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if handoff.slot != body.slot:
        raise HTTPException(status_code=409, detail="handoff slot mismatch")

    from honkai_cards import Teammate
    from bot.services.cards import get_custom_card

    teammates = [
        Teammate(
            characterId=item.characterId,
            lightCone=item.lightCone,
            characterEidolon=item.characterEidolon,
            lightConeSuperimposition=item.lightConeSuperimposition,
        )
        for item in body.teammates
    ]

    async with session_factory() as session:
        active = await GameIDs_repo(session).get_active_UID(user.telegram_id)
        if not active:
            raise HTTPException(status_code=409, detail="no active UID")
        if active.game_id != handoff.uid:
            raise HTTPException(status_code=409, detail="handoff UID is no longer active")
        if not await UserRepo(session).get_by_tele_id(user.telegram_id):
            raise HTTPException(status_code=409, detail="user is not registered")

        result = await get_custom_card(session, user.telegram_id, handoff.slot, teammates)
        if not result or not getattr(result, "card", None):
            raise HTTPException(status_code=500, detail="Card generation failed")

    bot = request.app.state.bot
    bot_me = await bot.me()
    caption = "✦ Custom Team Card"
    file = await _card_file(result.card)

    async def _keyboard(chat_id: int, message_id: int):
        next_handoff = await create_handoff(
            telegram_id=user.telegram_id,
            chat_id=chat_id,
            message_id=message_id,
            uid=handoff.uid,
            slot=handoff.slot,
        )
        return make_back_kb(
            user.telegram_id,
            handoff.slot,
            handoff.uid,
            bot_me.username,
            chat_id,
            message_id,
            handoff_reference=encode_handoff(next_handoff),
        )

    from aiogram.types import InputMediaPhoto, Message

    try:
        message = await bot.edit_message_media(
            chat_id=handoff.chat_id,
            message_id=handoff.message_id,
            media=InputMediaPhoto(
                media=file,
                caption=caption,
            ),
            reply_markup=await _keyboard(handoff.chat_id, handoff.message_id),
        )
        if isinstance(message, Message) and message.photo:
            async with session_factory() as cache_session:
                await CacheRepo(cache_session).set_cache(
                    user.telegram_id,
                    message.photo[0].file_id,
                    cache_type="CHAR",
                    data=str(handoff.slot),
                    slot=handoff.slot,
                )
                await cache_session.commit()
        return {"ok": True}
    except Exception:
        import logging

        logging.getLogger(__name__).exception("submit_team edit failed; falling back")
        try:
            message = await bot.send_photo(
                chat_id=handoff.chat_id,
                photo=await _card_file(result.card),
                caption=caption,
            )
            if isinstance(message, Message) and message.photo:
                await message.edit_reply_markup(
                    reply_markup=await _keyboard(handoff.chat_id, message.message_id)
                )
            return {"ok": True, "note": "sent as new message"}
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Could not deliver custom card") from exc

async def _active_uid(telegram_id: int) -> int | None:
    async with session_factory() as session:
        row = await GameIDs_repo(session).get_active_UID(telegram_id)
        return row.game_id if row else None


async def _card_file(card):
    from bot.utils.images import image_to_tgFile

    return await image_to_tgFile(card)