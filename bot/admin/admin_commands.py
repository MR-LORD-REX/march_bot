from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import asyncio

from bot.config.config import OWNER_TELE_ID , cmdavailability , ADMIN_GC_ID
from bot.DB.repo.admin_repo import AdminRepo
from bot.DB.repo.tele_group_repo import TeleGroupRepo
from bot.DB.repo.user_repo import UserRepo
from bot.DB.repo.cmd_meta_repo import CommandMetaRepo

rt = Router()
logger = logging.getLogger(__name__)

_album_cache: dict[str, list[Message]] = {}

proxies=None

try:
    with open("proxies.json", "r") as f:
        import json
        proxies = json.load(f)
except Exception as e:
    logger.warning(f"Could not load proxies.json: {e}")


def setup_admin_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="basic", callback_data="set_authority:basic"),
        InlineKeyboardButton(text="moderator", callback_data="set_authority:moderator")
    )
    kb.row(
        InlineKeyboardButton(text="admin", callback_data="set_authority:admin"),
        InlineKeyboardButton(text="owner", callback_data="set_authority:owner")
    )
    return kb.as_markup()


async def get_user_authority(db_session: AsyncSession, tele_id: int):
    if tele_id == OWNER_TELE_ID:
        return "owner"

    user = await AdminRepo(db_session).get_admin(tele_id)
    if not user:
        return None

    return user.authority


def _caption_kwargs(message: Message) -> dict:
    if not message.caption:
        return {}
    kwargs = {"caption": message.caption}
    if message.caption_entities:
        kwargs["caption_entities"] = message.caption_entities
    return kwargs


def _resolve_album(source: Message) -> list[Message]:
    if source.media_group_id:
        album = _album_cache.get(source.media_group_id, [source])
        return sorted(album, key=lambda m: m.message_id)
    return [source]


def _album_caption_source(messages: list[Message]) -> Message:
    for msg in messages:
        if msg.caption:
            return msg
    return messages[0]


def _build_photo_album(messages: list[Message]) -> list[InputMediaPhoto]:
    photos = [msg for msg in messages if msg.photo]
    caption_src = _album_caption_source(photos)
    media = []
    for i, msg in enumerate(photos):
        kwargs = {"media": msg.photo[-1].file_id}
        if i == 0:
            kwargs.update(_caption_kwargs(caption_src))
        media.append(InputMediaPhoto(**kwargs))
    return media


def _build_video_album(messages: list[Message]) -> list[InputMediaVideo]:
    videos = [msg for msg in messages if msg.video]
    caption_src = _album_caption_source(videos)
    media = []
    for i, msg in enumerate(videos):
        kwargs = {"media": msg.video.file_id}
        if i == 0:
            kwargs.update(_caption_kwargs(caption_src))
        media.append(InputMediaVideo(**kwargs))
    return media


async def _broadcast_media(message: Message, db_session: AsyncSession, media_type: str):
    tele_id = message.from_user.id
    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin"]:
        logger.warning(f"Unauthorized broadcast_{media_type} attempt: user {tele_id}")
        return

    source = message.reply_to_message if message.reply_to_message else message
    has_media = source.photo if media_type == "photo" else source.video
    if not has_media:
        label = "photo" if media_type == "photo" else "video"
        await message.reply(f"Please reply to a {label} (or album) to broadcast")
        return

    from bot.core.main import bot

    groups = await TeleGroupRepo(db_session).get_all()
    album = _resolve_album(source)

    for group in groups:
        try:
            if media_type == "photo":
                if len(album) == 1:
                    msg = album[0]
                    await bot.send_photo(
                        group.group_id,
                        photo=msg.photo[-1].file_id,
                        **_caption_kwargs(msg),
                    )
                else:
                    await bot.send_media_group(
                        group.group_id,
                        media=_build_photo_album(album),
                    )
            elif len(album) == 1:
                msg = album[0]
                await bot.send_video(
                    group.group_id,
                    video=msg.video.file_id,
                    **_caption_kwargs(msg),
                )
            else:
                await bot.send_media_group(
                    group.group_id,
                    media=_build_video_album(album),
                )
        except Exception as e:
            logger.error(f"Broadcast {media_type} error in {group.group_id}: {e}")
            await asyncio.sleep(5)

    unit = "photo" if len(album) == 1 else f"{len(album)} photos"
    if media_type == "video":
        unit = "video" if len(album) == 1 else f"{len(album)} videos"
    await message.reply(f"Broadcast sent successfully ({unit})")


@rt.message(F.media_group_id)
async def cache_media_group(message: Message):
    key = message.media_group_id
    if key not in _album_cache:
        _album_cache[key] = []
    _album_cache[key].append(message)


# ================================= OWNER ONLY COMMANDS =================================

@rt.message(Command("update_assets"))
async def update_assets(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    logger.info(f"update_assets command called by user {tele_id}")

    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority != "owner":
        logger.warning(f"Unauthorized update_assets attempt: user {tele_id}")
        return
    try:
        import enka
        async with enka.HSRClient() as hsr:
            await hsr.update_assets()
            await message.reply("Assets update completed successfully.")
    except Exception as e:
        logger.error(f"Error updating assets: {e}")
        await message.reply(f"Error updating assets: {e}")
    
@rt.message(Command("add_admin"))
async def add_admin(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    logger.info(f"add_admin command called by user {tele_id}")

    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority != "owner":
        logger.warning(f"Unauthorized add_admin attempt: user {tele_id}")
        return

    target = message.reply_to_message if message.reply_to_message else None
    if not target:
        await message.reply("Please reply to the user to add as admin")
        return

    user_name = target.from_user.username if target.from_user.username else None
    display_name = target.from_user.full_name if target.from_user.full_name else None
    target_id = target.from_user.id

    await AdminRepo(db_session).add_admin(target_id, "basic")
    await db_session.commit()

    await message.reply(
        f"Admin added successfully with telegram id {target_id}, username {user_name}, display name {display_name}"
    )


@rt.message(Command("remove_admin"))
async def remove_admin(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    logger.info(f"remove_admin command called by user {tele_id}")

    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority != "owner":
        logger.warning(f"Unauthorized remove_admin attempt: user {tele_id}")
        return

    target = message.reply_to_message if message.reply_to_message else None
    if not target:
        await message.reply("Please reply to the user to remove from admin")
        return

    target_id = target.from_user.id
    success = await AdminRepo(db_session).remove_admin(target_id)

    if success:
        await db_session.commit()
        await message.reply(f"Admin removed successfully with telegram id {target_id}")
    else:
        await message.reply(f"No admin found with telegram id {target_id}")


@rt.message(Command("update_admin"))
async def update_admin(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    logger.info(f"update_admin command called by user {tele_id}")

    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority != "owner":
        logger.warning(f"Unauthorized update_admin attempt: user {tele_id}")
        return

    target = message.reply_to_message if message.reply_to_message else None
    if not target:
        await message.reply("Please reply to the user to update admin")
        return

    target_id = target.from_user.id
    target_user = await AdminRepo(db_session).get_admin(target_id)

    if not target_user:
        await message.reply(f"No admin found with telegram id {target_id}")
        return

    kb = setup_admin_kb()
    await message.reply(
        f"Select the authority level for the user with telegram id {target_id}",
        reply_markup=kb
    )
    
@rt.message(Command("edit_commands"))
async def edit_commands(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    logger.info(f"edit_commands called by user {tele_id}")

    user_authority = await get_user_authority(db_session, tele_id)
    if user_authority != "owner":
        logger.warning(f"Unauthorized edit_commands attempt: user {tele_id}")
        return

    commands = await CommandMetaRepo(db_session).get_all_commands()
    if not commands:
        await message.reply("No commands found in the database.")
        return

    kb = InlineKeyboardBuilder()
    for cmd, active in commands.items():
        status = "on" if active else "off"
        toggle = "off" if active else "on"
        kb.button(
            text=f"/{cmd} — {status}",
            callback_data=f"toggle_cmd:{cmd}:{toggle}"
        )
    kb.adjust(3)

    await message.reply("Command status manager — tap to toggle:", reply_markup=kb.as_markup())


@rt.callback_query(F.data.startswith("toggle_cmd:"))
async def toggle_cmd(query: CallbackQuery, db_session: AsyncSession):
    tele_id = query.from_user.id
    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority != "owner":
        await query.answer("Unauthorized.", show_alert=True)
        return

    _, cmd, new_state = query.data.split(":")
    active = new_state == "on"

    success = await CommandMetaRepo(db_session).update_cmd(cmd, active)
    if not success:
        await query.answer(f"Command /{cmd} not found.", show_alert=True)
        return

    await db_session.commit()

    commands = await CommandMetaRepo(db_session).get_all_commands()
    kb = InlineKeyboardBuilder()
    for c, a in commands.items():
        status = "on" if a else "off"
        toggle = "off" if a else "on"
        kb.button(
            text=f"/{c} — {status}",
            callback_data=f"toggle_cmd:{c}:{toggle}"
        )
    kb.adjust(2)

    await query.message.edit_reply_markup(reply_markup=kb.as_markup())
    await query.answer(f"/{cmd} is now {'enabled' if active else 'disabled'}.", show_alert=True)
    await db_session.commit()
    new = await CommandMetaRepo(db_session).get_all_commands()
    cmdavailability.load(new)



# ================================= ADMIN + OWNER =================================

@rt.message(Command("broadcast"))
async def broadcast(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    logger.info(f"broadcast command called by user {tele_id}")

    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin"]:
        logger.warning(f"Unauthorized broadcast attempt: user {tele_id}")
        return

    to_send = message.reply_to_message.text if message.reply_to_message else message.text
    if not to_send:
        await message.reply("Please reply to the text message to broadcast")
        return

    from bot.core.main import bot

    groups = await TeleGroupRepo(db_session).get_all()

    for group in groups:
        try:
            await bot.send_message(group.group_id, to_send)
        except Exception as e:
            logger.error(f"Broadcast error in {group.group_id}: {e}")
            await asyncio.sleep(5)

    await message.reply("Broadcast sent successfully")


@rt.message(Command("broadcast_photo"))
async def broadcast_photo(message: Message, db_session: AsyncSession):
    logger.info(f"broadcast_photo command called by user {message.from_user.id}")
    await _broadcast_media(message, db_session, "photo")


@rt.message(Command("broadcast_vid"))
async def broadcast_vid(message: Message, db_session: AsyncSession):
    logger.info(f"broadcast_vid command called by user {message.from_user.id}")
    await _broadcast_media(message, db_session, "video")


USERS_PER_PAGE = 5


def _build_users_page_text(
    users,
    page: int,
    total_pages: int,
    total_count: int,
    admin_map: dict[int, str],
) -> str:
    start_idx = page * USERS_PER_PAGE
    lines = [
        "👥 <b>Users Database</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📄 Page <b>{page + 1}</b> of <b>{total_pages}</b>  ·  {total_count} total",
        "",
    ]

    for i, user in enumerate(users, start=start_idx + 1):
        status = "🚫 Banned" if user.banned else "✅ Active"
        warn_line = f"⚠️ {user.warns} warn{'s' if user.warns != 1 else ''}" if user.warns else "✅ 0 warns"
        username = f"@{user.username}" if user.username else "—"
        name = user.display_name or "—"
        uid_count = len(user.game_ids)
        admin_badge = f"  ·  🛡 {admin_map[user.telegram_id]}" if user.telegram_id in admin_map else ""

        lines.extend([
            f"━━ <b>#{i}</b> ━━",
            f"{status}{admin_badge}  ·  {warn_line}",
            f"👤 <b>{name}</b>  ·  {username}",
            f"🆔 <code>{user.telegram_id}</code>  ·  🎮 {uid_count} UID{'s' if uid_count != 1 else ''}",
            "",
        ])

    return "\n".join(lines).rstrip()


def _build_users_page_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    nav_buttons = []

    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀ Prev", callback_data=f"users_page:{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="users_page:noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="Next ▶", callback_data=f"users_page:{page + 1}")
        )

    if nav_buttons:
        kb.row(*nav_buttons)
    return kb.as_markup()


async def _render_users_page(page: int, db_session: AsyncSession):
    repo = UserRepo(db_session)
    total_count = await repo.count_users()
    if total_count == 0:
        return None, None

    total_pages = max(1, (total_count + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    users = await repo.get_page(page, USERS_PER_PAGE)
    admins = await AdminRepo(db_session).get_all_admins()
    admin_map = {admin.telegram_id: admin.authority for admin in admins}

    text = _build_users_page_text(users, page, total_pages, total_count, admin_map)
    kb = _build_users_page_kb(page, total_pages)
    return text, kb


@rt.message(Command("users"))
async def list_users(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    logger.info(f"users command called by user {tele_id}")

    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin"]:
        logger.warning(f"Unauthorized users attempt: user {tele_id}")
        return

    text, kb = await _render_users_page(0, db_session)
    if not text:
        await message.reply("No users found in the database.")
        return

    await message.reply(text, parse_mode="HTML", reply_markup=kb)


@rt.callback_query(F.data.startswith("users_page:"))
async def users_page_callback(query: CallbackQuery, db_session: AsyncSession):
    tele_id = query.from_user.id
    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin"]:
        await query.answer("Unauthorized.", show_alert=True)
        return

    page_token = query.data.split(":")[1]
    if page_token == "noop":
        await query.answer()
        return

    page = int(page_token)
    text, kb = await _render_users_page(page, db_session)
    if not text:
        await query.answer("No users found.", show_alert=True)
        return

    await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


# ================================= MODERATOR + ADMIN + OWNER =================================

@rt.message(Command("disable_command"))
async def disable_command(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    logger.info(f"disable_command command called by user {tele_id}")
    user_authority = await get_user_authority(db_session, tele_id)
    if user_authority != "owner":
        logger.warning(f"Unauthorized disable_command attempt: user {tele_id}")
        return
    command = message.text.split(" ")[1].replace("/","")
    reason = message.text.split(" ")[2:]
    reason = " ".join(reason)
    if not command or not reason:
        await message.reply("Please provide a command and a reason")
        return
    await CommandMetaRepo(db_session).disable_command(command, reason)
    await db_session.commit()
    await message.reply("Command disabled successfully")
    from bot.core.main import bot
    await bot.send_message(
        ADMIN_GC_ID,
        f"Command /{command} has been disabled by @{message.from_user.username if message.from_user.username else message.from_user.display_name} with the reason: {reason}"
    )
    new = await CommandMetaRepo(db_session).get_all_commands()
    cmdavailability.load(new)

@rt.message(Command("ban_user"))
async def ban_user(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id

    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin", "moderator"]:
        return

    if not message.reply_to_message:
        await message.reply("Please reply to the user to ban")
        return

    to_ban = message.reply_to_message.from_user.id
    await UserRepo(db_session).ban_user(to_ban)
    await db_session.commit()

    await message.reply("User banned successfully")


@rt.message(Command("unban_user"))
async def unban_user(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id

    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin", "moderator"]:
        return

    if not message.reply_to_message:
        await message.reply("Please reply to the user to unban")
        return

    to_unban = message.reply_to_message.from_user.id
    await UserRepo(db_session).unban_user(to_unban)
    await db_session.commit()

    await message.reply("User unbanned successfully")


# ================================= BASIC + ABOVE =================================

@rt.message(Command("send"))
async def send(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin", "moderator", "basic"]:
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.reply("Please enter the message to send")
        return

    to_send = parts[1]

    from bot.core.main import bot
    await bot.send_message(message.chat.id, to_send)


@rt.message(Command("reply"))
async def reply(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin", "moderator", "basic"]:
        return

    if not message.reply_to_message:
        await message.reply("please provide the user to reply to")
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.reply("please provide the text to reply")
        return

    await message.reply_to_message.reply(parts[1])


@rt.message(Command("delete"))
async def delete(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin", "moderator", "basic"]:
        return

    if not message.reply_to_message:
        await message.reply("Please reply to the message to delete")
        return

    from bot.core.main import bot

    try:
        await bot.delete_message(
            message.reply_to_message.chat.id,
            message.reply_to_message.message_id
        )
    except Exception:
        await message.reply("Error deleting message")


@rt.message(Command("admin_help"))
async def admin_help(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority not in ["owner", "admin", "moderator", "basic"]:
        return

    help_text = """
/add_admin - owner only
/remove_admin - owner only
/update_admin - owner only
/broadcast - admin + owner
/broadcast_photo - admin + owner
/broadcast_vid - admin + owner
/ban_user - moderator + admin + owner
/unban_user - moderator + admin + owner
/send <message>
/reply <message>
/delete
"""

    await message.reply(help_text, parse_mode=None)


@rt.callback_query(F.data.startswith("set_authority:"))
async def set_authority(query: CallbackQuery, db_session: AsyncSession):
    tele_id = query.from_user.id
    user_authority = await get_user_authority(db_session, tele_id)

    if user_authority != "owner":
        return

    if not query.message.reply_to_message:
        await query.message.reply("No target user found")
        return

    target_id = query.message.reply_to_message.from_user.id
    target = await AdminRepo(db_session).get_admin(target_id)

    if not target:
        await query.message.reply("No admin found for the user")
        return

    new_authority = query.data.split(":")[1]

    await AdminRepo(db_session).update_admin(target.telegram_id, new_authority)
    await db_session.commit()

    await query.answer(
        f"Authority updated to {new_authority} for user with telegram id {target.telegram_id}",
        show_alert=True
    )
    
    
# =============================== Report Callback =================================

@rt.callback_query(F.data.startswith("report:"))
async def handle_report(cb:CallbackQuery,db_session:AsyncSession):
    # send dm to owner with the report details
    data=cb.data.split(":")
    r_type=data[1]
    tele_id=int(data[2])
    uid=int(data[3])
    user=await UserRepo(db_session).get_by_tele_id(tele_id)
    if not user:
        await cb.answer("user not found",show_alert=True)
        return
    report_text=f"Report received for {r_type} card generation\n\n"
    report_text+=f"User details:\n"
    report_text+=f"Telegram ID: {user.telegram_id}\n"
    report_text+=f"Username: @{user.username}\n"
    report_text+=f"Display Name: {user.display_name}\n"
    report_text+=f"Game ID: {uid}\n"
    report_text+=f"Report Type: {r_type}\n"
    from bot.core.main import bot
    await bot.send_message(ADMIN_GC_ID,report_text)
    await cb.answer("report sent to bot admins",show_alert=True)

@rt.callback_query(F.data.startswith("ban_user:"))
async def handle_ban_user(cb:CallbackQuery,db_session:AsyncSession):
    data=cb.data.split(":")
    tapped_by=cb.from_user.id
    authority=await get_user_authority(db_session,tapped_by)
    if authority not in ["owner", "admin", "moderator"]:
        await cb.answer("you are not authorized to ban users",show_alert=True)
        return
    tele_id=int(data[1])
    await UserRepo(db_session).ban_user(tele_id)
    await db_session.commit()
    await cb.answer("user banned successfully",show_alert=True)
    from bot.core.main import bot
    user=await UserRepo(db_session).get_by_tele_id(tele_id)
    if not user:
        await cb.answer("user not found",show_alert=True)
        return
    await bot.send_message(
        ADMIN_GC_ID,
        f"User @{user.username if user.username else user.display_name} has been banned by @{cb.from_user.username if cb.from_user.username else cb.from_user.display_name}",
        reply_markup=InlineKeyboardBuilder().button(text="Unban User", callback_data=f"unban_user:{tele_id}").as_markup()
    )
    await bot.send_message(tele_id,f"You have been banned from the bot by @{cb.from_user.username if cb.from_user.username else cb.from_user.display_name}. Please contact the bot admins for more information.")


@rt.callback_query(F.data.startswith("unban_user:"))
async def handle_unban_user(cb:CallbackQuery,db_session:AsyncSession):
    data=cb.data.split(":")
    tapped_by=cb.from_user.id
    authority=await get_user_authority(db_session,tapped_by)
    if authority not in ["owner", "admin", "moderator"]:
        await cb.answer("you are not authorized to unban users",show_alert=True)
        return
    tele_id=int(data[1])
    await UserRepo(db_session).unban_user(tele_id)
    await db_session.commit()
    await cb.answer("user unbanned successfully",show_alert=True)
    from bot.core.main import bot
    user=await UserRepo(db_session).get_by_tele_id(tele_id)
    if not user:
        await cb.answer("user not found",show_alert=True)
        return
    await bot.send_message(ADMIN_GC_ID,f"User @{user.username if user.username else user.display_name} has been unbanned by @{cb.from_user.username if cb.from_user.username else cb.from_user.display_name}")
    await bot.send_message(tele_id,f"You have been unbanned from the bot by @{cb.from_user.username if cb.from_user.username else cb.from_user.display_name}. You can now use the bot again.")
    await cb.message.edit_text("User unbanned successfully",reply_markup=None)
    await cb.answer()
