from aiogram import Router
from aiogram.types import (
    Message , CallbackQuery , InputMediaPhoto, InputMediaAnimation , InlineQuery ,
    InlineQueryResult , InlineQueryResultArticle , InlineKeyboardMarkup , InlineKeyboardButton
    )

from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import json

from bot.services.auth import check_user
from bot.services.cards import get_profile_card , get_character_card , get_custom_card 
from honkai_cards import Teammate
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

async def _update_cust_msg(chat_id: int, msg_id: int, card, kb) -> None:
    """Edit the original message with the generated custom team card."""
    from bot.core.main import bot
    try:
        if hasattr(card, 'read'):
            from aiogram.types import BufferedInputFile
            file = BufferedInputFile(card.read(), filename='custom_team.png')
            photo = InputMediaPhoto(media=file)
        else:
            photo = InputMediaPhoto(media=card)
        await bot.edit_message_media(
            chat_id=chat_id,
            message_id=msg_id,
            media=photo,
            reply_markup=kb,
        )
    except Exception as e:
        logger.error(f"_update_cust_msg failed: {e}")

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
    uid=await GameIDs_repo(db_session).get_active_UID(tele_id)
    bot_me = await cb.bot.me()
    chat_id    = cb.message.chat.id
    message_id = cb.message.message_id
    kb=make_back_kb(tele_id, slot, uid.game_id, bot_me.username, chat_id, message_id)
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
    charname= await CacheRepo(db_session).get_cache(tele_id,cache_type='PFP')
    import ast
    if charname:
        charname= ast.literal_eval(charname.data)
        charname={ item["slot"] : item["name"] for item in charname}
        charname=charname.get(slot,"Unknown")
    else:
        charname="Unknown"
    await CacheRepo(db_session).set_cache(tele_id,file_id,cache_type='CHAR',data=charname,slot=slot)
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

@rt.callback_query(lambda c: c.data.startswith("cust_C:"))
async def cust_team(cb: CallbackQuery, db_session: AsyncSession):
    """Handles custom team webapp data returned via sendData.

    Expected cb.data format:  cust_C:{tele_id}:{slot}
    The webapp sends its payload via Telegram.WebApp.sendData(), which arrives
    as a separate web_app_data update — handled in handle_webapp_data below.
    This callback simply opens the webapp URL for the user.
    """
    tele_id = cb.from_user.id
    data    = cb.data.split(":")
    to      = int(data[1])
    slot    = int(data[2])
    if tele_id != to:
        await cb.answer("not for you", show_alert=True)
        return
    await cb


@rt.message(lambda m: m.web_app_data is not None)
async def handle_webapp_data(msg: Message, db_session: AsyncSession):
    """Receives the JSON payload sent by the webapp via Telegram.WebApp.sendData().

    Payload schema:
    {
      "slot": int,
      "teammates": [
        {
          "characterId": str,
          "lightCone": str,
          "characterEidolon": int,
          "lightConeSuperimposition": int
        },
        ...  (exactly 3 entries)
      ]
    }
    """
    tele_id = msg.from_user.id
    raw     = msg.web_app_data.data

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        await msg.reply("Invalid data from webapp.")
        return
    logger.info(f"Received webapp data: {payload}")
    slot          = int(payload.get("slot", 1))
    teammates_raw = payload.get("teammates", [])
    
    if len(teammates_raw) != 3:
        await msg.reply("Please select exactly 3 teammates.")
        return

    try:
        teammates = [
            Teammate(
                characterId              = tm["characterId"],
                lightCone               = tm["lightCone"],
                characterEidolon        = int(tm.get("characterEidolon", 0)),
                lightConeSuperimposition= int(tm.get("lightConeSuperimposition", 1)),
            )
            for tm in teammates_raw
        ]
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Teammate parse error: {e}")
        await msg.reply("Could not parse teammate data. Please try again.")
        return

    loading_msg = await msg.reply_animation(
        get_gif("loading"),
        caption="Building your custom team card…"
    )

    res = await get_custom_card(db_session, tele_id, slot, teammates)

    await _delete_message(loading_msg)

    if not res or not getattr(res, "card", None):
        uid = await GameIDs_repo(db_session).get_active_UID(tele_id)
        kb  = make_report_keboard(tele_id, uid.game_id if uid else 0, r_type='CHAR')
        await _reply_card_error(msg, _CHAR_ERROR, kb)
        return

    try:
        file  = await image_to_tgFile(res.card)
        await msg.reply_photo(photo=file, caption="✦ Custom Team Card")
    except Exception as e:
        logger.error(f"Failed to send custom card: {e}")
        await msg.reply("Failed to send card. Please try again.")

async def handle_webapp_deeplink(msg: Message, payload: str, db_session: AsyncSession):
    """Handles deep link payload from Web App.
    Format: c_{slot}_{cId1}-{lc1}-{e1}{s1}_{cId2}...
    """
    tele_id = msg.from_user.id
    parts = payload.split('_')
    if len(parts) != 5 or parts[0] != 'c':
        await msg.reply("Invalid custom team data.")
        return
        
    try:
        slot = int(parts[1])
        teammates = []
        for i in range(2, 5):
            tm_parts = parts[i].split('-')
            if len(tm_parts) != 3:
                raise ValueError("Invalid teammate format")
            char_id, lc_id, e_s = tm_parts
            e = int(e_s[0])
            s = int(e_s[1])
            teammates.append(Teammate(
                characterId=char_id,
                lightCone=lc_id,
                characterEidolon=e,
                lightConeSuperimposition=s
            ))
    except Exception as e:
        logger.error(f"Deep link parse error: {e}")
        await msg.reply("Could not parse teammate data. Please try again.")
        return

    loading_msg = await msg.reply_animation(
        get_gif("loading"),
        caption="Building your custom team card…"
    )

    res = await get_custom_card(db_session, tele_id, slot, teammates)
    await _delete_message(loading_msg)

    if not res or not getattr(res, "card", None):
        uid = await GameIDs_repo(db_session).get_active_UID(tele_id)
        kb  = make_report_keboard(tele_id, uid.game_id if uid else 0, r_type='CHAR')
        await _reply_card_error(msg, _CHAR_ERROR, kb)
        return

    try:
        file = await image_to_tgFile(res.card)
        await msg.reply_photo(photo=file, caption="✦ Custom Team Card")
    except Exception as e:
        logger.error(f"Failed to send custom card: {e}")
        await msg.reply("Failed to send card. Please try again.")
