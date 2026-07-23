from aiogram import Router
from aiogram.types import Message , CallbackQuery , InputMediaPhoto, InputMediaAnimation
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.services.auth import check_user
from bot.services.cards import get_profile_card , get_character_card
from bot.utils.images import image_to_tgFile
from bot.utils.gifs import get_gif
from bot.handlers.cards.kb import make_report_keboard , make_profile_keyboard , make_back_kb

from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.DB.repo.cache_repo import CacheRepo

logger=logging.getLogger(__name__)

rt=Router()

_CARD_ERROR = "failed to generate profile card , press report to report the issue to the bot admins "
_CHAR_ERROR = "failed to generate character card , press report to report the issue to the bot admins "


async def _delete_message(msg: Message) -> None:
    try:
        await msg.delete()
    except Exception:
        pass


async def _reply_card_error(msg: Message, text: str, kb) -> None:
    await msg.reply_animation(get_gif("error_3"), caption=text, reply_markup=kb)


async def _edit_card_error(msg: Message, text: str, kb) -> None:
    await msg.edit_media(
        media=InputMediaAnimation(media=get_gif("error_3"), caption=text),
        reply_markup=kb,
    )

async def _send_profile_with_cache_fallback(msg: Message, db_session: AsyncSession, tele_id: int, res, kb):
    """Try cached Telegram file_id first; regenerate if it becomes invalid."""
    try:
        if not res.cached or not res.card:
            photo = await image_to_tgFile(res.card)
        else:
            photo = res.card
        return await msg.reply_photo(photo=photo, reply_markup=kb)
    except TelegramBadRequest as e:
        if "wrong file identifier" not in str(e).lower():
            raise
        logger.warning(f"Invalid cached profile file_id for {tele_id}, regenerating card")
        await CacheRepo(db_session).delete_all_cache(tele_id)
        fresh = await get_profile_card(db_session, tele_id)
        if not fresh:
            raise
        fresh_photo = await image_to_tgFile(fresh.card)
        return await msg.reply_photo(photo=fresh_photo, reply_markup=kb), fresh

@rt.message(Command("myc"))
async def handle_profile(msg:Message,db_session:AsyncSession):
    tele_id=msg.from_user.id
    user=await check_user(db_session,tele_id)
    uid=await GameIDs_repo(db_session).get_active_UID(tele_id)
    if not user or not uid:
        await msg.reply("please login using /login or /switch ")
        return
    loading_msg = await msg.reply_animation(get_gif("loading"))
    res=await get_profile_card(db_session,tele_id)
    await _delete_message(loading_msg)
    if not res or not getattr(res, "card", None):
        kb=make_report_keboard(tele_id,uid.game_id,r_type='PFP')
        await _reply_card_error(msg, _CARD_ERROR, kb)
        return
    kb=make_profile_keyboard(tele_id,chars=res.data)
    sent = await _send_profile_with_cache_fallback(msg, db_session, tele_id, res, kb)
    if not sent:
        await _reply_card_error(msg, _CARD_ERROR, make_report_keboard(tele_id,uid.game_id,r_type='PFP'))
        return
    if isinstance(sent, tuple):
        file, res = sent
    else:
        file = sent
    file_id = file.photo[0].file_id
    
    await CacheRepo(db_session).set_cache(tele_id,file_id,cache_type='PFP',data=f"{res.data}",slot=None)
    await db_session.commit()
    
@rt.callback_query(lambda c: c.data.startswith("C_card:"))
async def handle_ccard(cb:CallbackQuery,db_session:AsyncSession):
    tele_id=cb.from_user.id
    data=cb.data.split(":")
    to=int(data[1])
    if not tele_id==to:
        await cb.answer("not for you",show_alert=True)
        return
    
    slot=int(data[-1])

    await cb.message.edit_media(
        media=InputMediaAnimation(media=get_gif("loading"),
        caption="Running benchmark simulations , this may take a while..."
        ))
    res=await get_character_card(db_session,tele_id,slot)
    if not res or not getattr(res, "card", None):
        uid=await GameIDs_repo(db_session).get_active_UID(tele_id)
        kb=make_report_keboard(tele_id,uid.game_id,r_type='CHAR')
        await _edit_card_error(cb.message, _CHAR_ERROR, kb)
        return
    kb=make_back_kb(tele_id)
    try:
        if res.cached and res.card:
            photo=InputMediaPhoto(media=res.card)
        else:
            file=await image_to_tgFile(res.card)
            photo=InputMediaPhoto(media=file)
        file=await cb.message.edit_media(media=photo,reply_markup=kb)
    except TelegramBadRequest as e:
        error_lower = str(e).lower()
        if "wrong file identifier" not in error_lower and "media_empty" not in error_lower:
            raise
        logger.warning(f"Invalid cached character file_id for {tele_id}, regenerating card")
        await CacheRepo(db_session).delete_all_cache(tele_id)
        res = await get_character_card(db_session, tele_id, slot)
        if not res:
            uid = await GameIDs_repo(db_session).get_active_UID(tele_id)
            kb = make_report_keboard(tele_id, uid.game_id, r_type='CHAR')
            await _edit_card_error(cb.message, _CHAR_ERROR, kb)
            return
        fresh_file = await image_to_tgFile(res.card)
        file = await cb.message.edit_media(
            media=InputMediaPhoto(media=fresh_file),
            reply_markup=kb
        )
    file_id = file.photo[0].file_id
    
    await CacheRepo(db_session).set_cache(tele_id,file_id,cache_type='CHAR',data=str(slot),slot=slot)
    await db_session.commit()
    
    
@rt.callback_query(lambda c: c.data.startswith("back_P:"))
async def handle_back(cb:CallbackQuery,db_session:AsyncSession):
    tele_id=cb.from_user.id
    data=cb.data.split(":")
    to=int(data[1])
    if not tele_id==to:
        await cb.answer("not for you",show_alert=True)
        return
    uid=await GameIDs_repo(db_session).get_active_UID(tele_id)
    await cb.message.edit_media(media=InputMediaAnimation(media=get_gif("loading")))
    res=await get_profile_card(db_session,tele_id)
    if not res or not getattr(res, "card", None):
        kb=make_report_keboard(tele_id,uid.game_id,r_type='PFP')
        await _edit_card_error(cb.message, _CARD_ERROR, kb)
        return
    kb=make_profile_keyboard(tele_id,chars=res.data)
    try:
        if not res.cached or not res.card:
            file=await image_to_tgFile(res.card)
            photo=InputMediaPhoto(media=file)
        else:
            photo=InputMediaPhoto(media=res.card)
        file=await cb.message.edit_media(media=photo,reply_markup=kb)
    except TelegramBadRequest as e:
        error_lower = str(e).lower()
        if "wrong file identifier" not in error_lower and "media_empty" not in error_lower:
            raise
        logger.warning(f"Invalid cached profile file_id on back for {tele_id}, regenerating card")
        await CacheRepo(db_session).delete_all_cache(tele_id)
        res = await get_profile_card(db_session, tele_id)
        if not res:
            kb = make_report_keboard(tele_id, uid.game_id, r_type='PFP')
            await _edit_card_error(cb.message, _CARD_ERROR, kb)
            return
        regenerated = await image_to_tgFile(res.card)
        file = await cb.message.edit_media(
            media=InputMediaPhoto(media=regenerated),
            reply_markup=make_profile_keyboard(tele_id, chars=res.data)
        )
    file_id = file.photo[0].file_id
    
    await CacheRepo(db_session).set_cache(tele_id,file_id,cache_type='PFP',data=f"{res.data}",slot=None)
    await db_session.commit()