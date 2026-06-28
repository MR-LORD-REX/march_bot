from aiogram import Router
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, MEMBER, LEFT
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from bot.DB.repo.user_repo import UserRepo
from bot.DB.repo.tele_group_repo import TeleGroupRepo
from bot.DB.repo.users_in_group_repo import UsersInGroupRepo
from bot.DB.asyncsessions import session_factory

from bot.config.config import groups_record, users_record

from bot.services.UG_cache import load_users, load_groups

logger = logging.getLogger(__name__)

rt = Router()

@rt.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def bot_added_to_group(update: ChatMemberUpdated):
    group_id = update.chat.id
    group_name = update.chat.title or update.chat.full_name or "Unknown"
    
    try:
        async with session_factory() as session:
            group_repo = TeleGroupRepo(session)
            existing_group = await group_repo.get_group(group_id)
            if not existing_group:
                await group_repo.add_group(group_id, group_name)
                logger.info(f"Bot added to group: {group_name} (ID: {group_id})")
                await session.commit()
            else:
                logger.info(f"Bot already in group: {group_name} (ID: {group_id})")
    except Exception as e:
        logger.error(f"error adding group: {e}")

@rt.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEFT))
async def bot_removed_from_group(update: ChatMemberUpdated):
    group_id = update.chat.id
    group_name = update.chat.title or update.chat.full_name or "Unknown"
    
    try:
        async with session_factory() as session:
            group_repo = TeleGroupRepo(session)
            group = await group_repo.get_group(group_id)
            if group:
                await group_repo.delete(group)
                logger.info(f"Bot removed from group: {group_name} (ID: {group_id})")
                await session.commit()
            else:
                logger.warning(f"Group not found in database: {group_id}")
    except Exception as e:
        logger.error(f"error removing group: {e}")



@rt.message()
async def handle_all_messages(message: Message,db_session: AsyncSession):
    """Handle all messages to keep user-group cache updated"""
    try:
        logger.debug(f"Received message from user {message.from_user.id} in chat {message.chat.id}")
        user_id = message.from_user.id
        user_name = message.from_user.username
        display_name = message.from_user.full_name
        group_id = message.chat.id
        try:
            if message.chat.type in ["group", "supergroup"]:
                if not users_record.is_registered(user_id):
                    logger.debug(f"user {user_id} not registered, skipping group update")
                    return
                if not groups_record.is_registered(group_id):
                    await TeleGroupRepo(db_session).add_group(
                        group_id, 
                        message.chat.title or message.chat.full_name or "Unknown"
                        )
                    await load_groups(db_session, groups_record)
                    logger.info(f" NEW: Group {group_id} added to database")
                
                if not groups_record.is_user_in_group(user_id, group_id):
                    added = await UsersInGroupRepo(db_session).add_user_to_group(user_id, group_id)
                    if added:
                        await load_groups(db_session, groups_record)
                        logger.info(f" NEW: User {user_id}({user_name}) added to group {group_id}")
                    else:
                        logger.warning(f"FAILED: Could not add user {user_id} to group {group_id}")
                
                if user_name != users_record.get_username(user_id) or display_name != users_record.get_display_name(user_id):
                    user = await UserRepo(db_session).get_by_tele_id(user_id)
                    if user:
                        old_username = user.username
                        old_display = user.display_name
                        user.username = user_name
                        user.display_name = display_name
                        await UserRepo(db_session).update(user)
                        await load_users(db_session, users_record)
                        logger.info(f" UPDATE: User {user_id} | name: {old_username}→{user_name} | display: {old_display}→{display_name}")
                    else:
                        logger.warning(f" FAILED: User {user_id} not found in database for update")
            else:
                if users_record.is_registered(user_id):
                    if user_name != users_record.get_username(user_id) or display_name != users_record.get_display_name(user_id):
                        user = await UserRepo(db_session).get_by_tele_id(user_id)
                        if user:
                            old_username = user.username
                            old_display = user.display_name
                            user.username = user_name
                            user.display_name = display_name
                            await UserRepo(db_session).update(user)
                            await load_users(db_session, users_record)
                            logger.info(f" UPDATE (DM): User {user_id} | name: {old_username}→{user_name} | display: {old_display}→{display_name}")
                        else:
                            logger.warning(f" FAILED: User {user_id} not found in database for update (DM)")
            await db_session.commit()
        except Exception as e:
            logger.error(f" ERROR: Failed to update user-group cache | User: {user_id} | Group: {group_id} | Error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f" ERROR: Critical error in handle_all_messages: {e}", exc_info=True)