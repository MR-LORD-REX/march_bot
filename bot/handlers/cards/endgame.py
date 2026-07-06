# pyrefly: ignore [missing-import]
from aiogram import Router
from aiogram.types import ReactionTypeEmoji
from aiogram.types import Message , CallbackQuery , InputMediaPhoto
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from typing import Literal
from PIL import Image

from bot.services.auth import check_user
from bot.services.cards import get_endgame_card , EndRes
from bot.utils.images import image_to_tgFile
from bot.handlers.cards.kb import make_report_keboard , make_endgame_keyboard

from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.DB.repo.cache_repo import CacheRepo

logger=logging.getLogger(__name__)

rt=Router()

async def _send_endgame_card(
    msg: Message,
    db_session: AsyncSession,
    tele_id: int,
    res: EndRes,
    kb,
    c_type: Literal['MOC','PF','ANO','AS']
):
    try:
        if not res.cached or type(res.card) == Image.Image:
            photo = await image_to_tgFile(res.card)
        else:
            photo = res.card
        return await msg.reply_photo(photo=photo, reply_markup=kb)
    except TelegramBadRequest as e:
        if "wrong file identifier" not in str(e).lower():
            raise
        logger.warning(f"Invalid cached endgame file_id for {tele_id}, regenerating card")
        sched = res.data or '1'
        await CacheRepo(db_session).delete_all_cache(tele_id)
        fresh = await get_endgame_card(db_session, tele_id, c_type, sched)
        if not fresh:
            raise
        fresh_photo = await image_to_tgFile(fresh.card)
        return await msg.reply_photo(photo=fresh_photo, reply_markup=kb), fresh


async def _edit_endgame_card(
    cb: CallbackQuery,
    db_session: AsyncSession,
    tele_id: int,
    res: EndRes,
    kb,
    c_type: Literal['MOC','PF','ANO','AS'],
    sched: Literal['1','2']
):
    try:
        if not res.cached or type(res.card) == Image.Image:
            media = InputMediaPhoto(media=await image_to_tgFile(res.card))
        else:
            media = InputMediaPhoto(media=res.card)
        return await cb.message.edit_media(media=media, reply_markup=kb)
    except TelegramBadRequest as e:
        error_lower = str(e).lower()
        if "wrong file identifier" not in error_lower and "media_empty" not in error_lower:
            raise
        logger.warning(f"Invalid cached endgame file_id for {tele_id}, regenerating card")
        await CacheRepo(db_session).delete_all_cache(tele_id)
        fresh = await get_endgame_card(db_session, tele_id, c_type, sched)
        if not fresh:
            await cb.answer("failed to regenerate card", show_alert=True)
            return None, None
        fresh_photo = await image_to_tgFile(fresh.card)
        file = await cb.message.edit_media(
            media=InputMediaPhoto(media=fresh_photo),
            reply_markup=kb
        )
        return file, fresh

async def _handle_endgame_command(
    msg: Message,
    db_session: AsyncSession,
    c_type: Literal['MOC','PF','ANO','AS'],
    sched: Literal['1','2'] = '1'
):
    tele_id = msg.from_user.id
    user = await check_user(db_session, tele_id)
    uid  = await GameIDs_repo(db_session).get_active_UID(tele_id)
    if not user or not uid:
        await msg.reply("please login using /login or /switch ")
        return
    try:
        await msg.react([ReactionTypeEmoji(emoji="👍")])
    except Exception as e:
        logger.error(f"error while reacting to message: {e}")

    res = await get_endgame_card(db_session, tele_id, c_type, sched)
    if not res or not getattr(res, "card", None):
        kb = make_report_keboard(tele_id, uid.game_id, r_type=c_type)
        await msg.reply(
            "failed to generate card , press report to report the issue to the bot admins ",
            reply_markup=kb
        )
        return

    # ANO has no schedule selector
    kb = make_endgame_keyboard(tele_id, c_type, active=sched) if c_type != 'ANO' else None

    sent = await _send_endgame_card(msg, db_session, tele_id, res, kb, c_type)
    if isinstance(sent, tuple):
        file, res = sent
    else:
        file = sent

    file_id = file.photo[0].file_id
    cache_slot = int(sched) if c_type != 'ANO' else None
    await CacheRepo(db_session).set_cache(
        tele_id, file_id, cache_type=c_type, data=str(sched), slot=cache_slot
    )
    await db_session.commit()


@rt.message(Command("moc"))
async def handle_moc(msg: Message, db_session: AsyncSession):
    await _handle_endgame_command(msg, db_session, c_type='MOC', sched='1')


@rt.message(Command("purefiction"))
async def handle_purefiction(msg: Message, db_session: AsyncSession):
    await _handle_endgame_command(msg, db_session, c_type='PF', sched='1')


@rt.message(Command("apoc"))
async def handle_apoc(msg: Message, db_session: AsyncSession):
    await _handle_endgame_command(msg, db_session, c_type='AS', sched='1')


@rt.message(Command("anomaly"))
async def handle_anomaly(msg: Message, db_session: AsyncSession):
    await _handle_endgame_command(msg, db_session, c_type='ANO', sched='1')



@rt.callback_query(lambda c: c.data.startswith("EG:"))
async def handle_endgame_switch(cb: CallbackQuery, db_session: AsyncSession):
    tele_id = cb.from_user.id
    parts   = cb.data.split(":")         
    c_type  = parts[1]                    
    owner   = int(parts[2])
    sched   = parts[3]                    

    if tele_id != owner:
        await cb.answer("not for you", show_alert=True)
        return

    await cb.answer()  # dismiss loading spinner

    res = await get_endgame_card(db_session, tele_id, c_type, sched)
    if not res:
        await cb.answer("failed to fetch card", show_alert=True)
        return

    kb = make_endgame_keyboard(tele_id, c_type, active=sched)

    result = await _edit_endgame_card(cb, db_session, tele_id, res, kb, c_type, sched)
    if result is None:
        return
    if isinstance(result, tuple):
        file, res = result
    else:
        file = result

    if file is None:
        return

    file_id    = file.photo[0].file_id
    cache_slot = int(sched)
    await CacheRepo(db_session).set_cache(
        tele_id, file_id, cache_type=c_type, data=str(sched), slot=cache_slot
    )
    await db_session.commit()