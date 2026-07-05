from aiogram import Router
from aiogram.types import ReactionTypeEmoji
from aiogram.types import Message , InlineKeyboardMarkup , CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from datetime import datetime, timezone , timedelta

from bot.config.config import users_record, scheduler
from bot.DB.repo.scheduler_repo import SchedulerRepo
from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.utils.auth import decrypt_token

from bot.services.live_cards import (
    get_live_stats_card,
    get_banners_card,
    get_events_card,
    send_daily_reminder,
    send_recovery_notification,
    get_endgame_card,
    # send_weekly_reminder
)

from bot.utils.images import image_to_tgFile

rt=Router()
logger=logging.getLogger(__name__)

def get_sanity_reminder_keyboard(tele_id:int,seconds:int)->InlineKeyboardMarkup:
    kb=InlineKeyboardBuilder()
    tsk=scheduler.get_task(f"sanity_reminder_{tele_id}")
    if tsk and tsk.running:
        kb.button(text="cancel recovery reminder",callback_data=f"cancel_sanity:{tele_id}")
    else:
        kb.button(text="set recovery reminder",callback_data=f"sanity:{tele_id}:{seconds}")
    return kb.as_markup()
        

@rt.message(Command("notes"))
async def handle_notes(msg:Message,db_session:AsyncSession):
    tele_id=msg.from_user.id
    if not users_record.is_registered(tele_id):
        await msg.reply("please login using /login")
        return
    try:
        await msg.react([ReactionTypeEmoji(emoji="👍")])
    except Exception as e:
        logger.error(f"error while reacting to message: {e}")
    res=await get_live_stats_card(db_session,tele_id)
    if not res:
        await msg.reply("failed to generate live stats card")
        return
    if res.success:
        file=await image_to_tgFile(res.card)
        kb=get_sanity_reminder_keyboard(tele_id,res.seconds if res.seconds else 0)
        await msg.reply_photo(photo=file,caption=res.msg,reply_markup=kb)
    else:
        await msg.reply(res.msg)
        
    
@rt.callback_query(lambda c: c.data and c.data.startswith("sanity:"))
async def handle_recovery_reminder(callback_query:CallbackQuery,db_session:AsyncSession):
    data=callback_query.data.split(":")
    target_tele_id=int(data[1])
    seconds=int(data[2])
    if callback_query.from_user.id != target_tele_id:
        await callback_query.answer("this button is not for you", show_alert=True)
        return
    scheduler.add_oneshot(
        task_id=f"sanity_reminder_{target_tele_id}",
        task_name=f"Sanity reminder",
        coro=send_recovery_notification,
        delay=seconds,
        max_errors=1,
        tele_id=target_tele_id,
        retries=3
    )
    await callback_query.answer("recovery reminder set! Make sure to allow notifications from this bot in DM ", show_alert=True)
    now=datetime.now(timezone.utc)
    await SchedulerRepo(db_session).add_task_meta(
        user_id=target_tele_id,
        task_id=f"sanity_reminder_{target_tele_id}",
        task_name=f"Sanity reminder",
        task_type="Oneshot",
        args=None,
        execution_time=now + timedelta(seconds=seconds)
    )
    kb=get_sanity_reminder_keyboard(target_tele_id,seconds)
    await callback_query.message.edit_reply_markup(reply_markup=kb)
    
@rt.callback_query(lambda c: c.data and c.data.startswith("cancel_sanity:"))
async def handle_cancel_recovery_reminder(callback_query:CallbackQuery,db_session:AsyncSession):
    data=callback_query.data.split(":")
    target_tele_id=int(data[1])
    if callback_query.from_user.id != target_tele_id:
        await callback_query.answer("this button is not for you", show_alert=True)
        return
    tsk=scheduler.get_task(f"sanity_reminder_{target_tele_id}")
    if tsk and tsk.running:
        tsk.cancel()
    await SchedulerRepo(db_session).delete_task_meta(f"sanity_reminder_{target_tele_id}")
    await callback_query.answer("recovery reminder cancelled!", show_alert=True)
    await callback_query.message.delete()

@rt.message(Command("banners"))
async def handle_banners(msg: Message, db_session: AsyncSession):
    """Show current Honkai: Star Rail banners — no auth needed."""
    tele_id = msg.from_user.id
    if not users_record.is_registered(tele_id):
        await msg.reply("Please register a UID first using /login.")
        return
    try:
        await msg.react([ReactionTypeEmoji(emoji="💵")])
    except Exception as e:
        logger.error(f"error while reacting to message: {e}")

    res = await get_banners_card(db_session, tele_id)
    if res.success and res.card:
        file = await image_to_tgFile(res.card)
        await msg.reply_photo(photo=file, caption=res.msg)
    else:
        await msg.reply(res.msg)


@rt.message(Command("events"))
async def handle_events(msg: Message, db_session: AsyncSession):
    """Show current Honkai: Star Rail events — no auth needed."""
    tele_id = msg.from_user.id
    if not users_record.is_registered(tele_id):
        await msg.reply("Please register a UID first using /login.")
        return
    try:
        await msg.react([ReactionTypeEmoji(emoji="🎉")])
    except Exception as e:
        logger.error(f"error while reacting to message: {e}")

    res = await get_events_card(db_session, tele_id)
    if res.success and res.card:
        file = await image_to_tgFile(res.card)
        await msg.reply_photo(photo=file, caption=res.msg)
    else:
        await msg.reply(res.msg)

@rt.message(Command("endgames"))
async def handle_endgames(msg: Message, db_session: AsyncSession):
    """Show current Honkai: Star Rail endgame content — no auth needed."""
    tele_id = msg.from_user.id
    if not users_record.is_registered(tele_id):
        await msg.reply("Please register a UID first using /login.")
        return
    try:
        await msg.react([ReactionTypeEmoji(emoji="🏆")])
    except Exception as e:
        logger.error(f"error while reacting to message: {e}")
        
    res = await get_endgame_card(db_session, tele_id)
    if res.success and res.card:
        file = await image_to_tgFile(res.card)
        await msg.reply_photo(photo=file, caption=res.msg)
    else:
        await msg.reply(res.msg)