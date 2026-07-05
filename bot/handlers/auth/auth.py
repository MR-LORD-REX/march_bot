from aiogram import Router
from aiogram.types import Message , CallbackQuery 
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.config.config import CHANNEL_LINK
from bot.services.auth import login , check_user , switch , logout , token_login , token_logout
from bot.services.UG_cache import load_users , load_groups
from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.handlers.auth.kb import make_switch_kb

rt=Router()
logger=logging.getLogger(__name__)

@rt.message(Command("login"))
async def handle_login(msg:Message,db_session:AsyncSession):
    args = msg.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        await msg.reply("Please provide a valid UID. Usage: /login UID_NUMBER")
        return
    uid = int(args[1])
    tele_id=msg.from_user.id
    res=await login(db_session,tele_id,msg,uid)
    kb=InlineKeyboardBuilder()
    kb.button(text="Join our channel",url=CHANNEL_LINK)
    await msg.reply(f"{res.msg}", reply_markup=kb.as_markup(), parse_mode=None)
    if res.success:
        await db_session.commit()
    from bot.config.config import users_record
    await load_users(db_session,users_record)
        
@rt.message(Command("myuid"))
async def handle_myuid(msg:Message,db_session:AsyncSession):
    tele_id=msg.from_user.id
    user=await check_user(db_session,tele_id)
    all_uids=await GameIDs_repo(db_session).get_UIDs(tele_id)
    if not user or not all_uids:
        await msg.reply("Please login using /login UID_NUMBER")
        return
        
    text=""
    for uid in all_uids:
        text+=f"uid: `{uid.game_id}` \| active:{uid.active}\n"
        
    await msg.reply(text, parse_mode="MarkdownV2")
    await db_session.rollback()
    
    
@rt.message(Command("logout"))
async def handle_logout(msg:Message,db_session:AsyncSession):
    tele_id=msg.from_user.id
    user=await check_user(db_session,tele_id)
    all_uids=await GameIDs_repo(db_session).get_UIDs(tele_id)
    if not user or not all_uids:
        await msg.reply("Please login using /login UID_NUMBER")
        return
        
    res=await logout(db_session,tele_id)
    await msg.reply(res.msg)
    await db_session.commit()
    
    if res.success:
        await db_session.commit()
    from bot.config.config import users_record
    await load_users(db_session,users_record)
        
@rt.message(Command("token_login"))
async def handle_token_login(msg:Message,db_session:AsyncSession):
    if msg.chat.type != "private":
        await msg.reply("Please use this command in private chat.")
        return
    args = msg.text.split(maxsplit=1)
    if len(args) < 2 :
        await msg.reply("Please provide a valid token. Usage: /token_login t1//t2 use /token_help")
        return
    token=args[-1]
    token=token.strip()
    token=token.split("//")
    token={"ltoken_v2":token[0],"ltuid_v2":token[1]}
    res=await token_login(db_session,msg.from_user.id,token)
    await msg.reply(text=res.msg)
    if res.success:
        await db_session.commit()
        await msg.delete()
    else:
        await db_session.rollback()
    from bot.config.config import users_record
    await load_users(db_session,users_record)
        
@rt.message(Command("token_logout"))
async def handle_logout(msg:Message,db_session:AsyncSession):
    tele_id=msg.from_user.id
    user=await check_user(db_session,tele_id)
    all_uids=await GameIDs_repo(db_session).get_UIDs(tele_id)
    if not user or not all_uids:
        await msg.reply("Please login using /login UID_NUMBER")
        return
    res=await token_logout(db_session,tele_id)
    await msg.reply(res.msg)
    if res.success:
        await db_session.commit()
        
@rt.message(Command("switch"))
async def handle_switch(msg:Message,db_session:AsyncSession):
    tele_id=msg.from_user.id
    user=await check_user(db_session,tele_id)
    all_uids=await GameIDs_repo(db_session).get_UIDs(tele_id)
    if not user or not all_uids:
        await msg.reply("Please login using /login UID_NUMBER")
        return
    uids=[]
    for uid in all_uids:
        uids.append(uid.game_id)
    kb=make_switch_kb(tele_id,uids)
    await msg.reply("select the uid to switch",reply_markup=kb)
    await db_session.rollback()
    
@rt.callback_query(lambda c: c.data.startswith("switch:"))
async def switch_uid(cb:CallbackQuery,db_session:AsyncSession):
    data=cb.data.split(":")
    to=int(data[1])
    uid=int(data[2])
    if not cb.from_user.id == to:
        cb.answer("not for you",show_alert=True)
    res=await switch(db_session,to,uid)
    await cb.answer(f"{res.msg}",show_alert=True)
    await cb.message.delete()
    if res.success:
        await db_session.commit()
    else:
        await db_session.rollback()