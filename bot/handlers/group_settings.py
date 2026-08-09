"""Per-group settings panel, driven by group admins rather than bot admins.

Two kinds of setting live here:
  * command toggles -- which bot features this group allows (GROUP_TOGGLEABLE)
  * spoiler mode    -- whether lore answers arrive hidden behind a spoiler

Both store "no row / NULL" as inherit, so a group that never touches the panel
keeps following the bot-wide default instead of freezing today's value.
"""

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.config.config import OWNER_TELE_ID
from bot.DB.repo.group_settings_repo import GroupCommandSettingsRepo, GROUP_TOGGLEABLE
from bot.DB.repo.tele_group_repo import TeleGroupRepo
from bot.services.lorebot.runtime import settings as lore_settings

rt = Router()
logger = logging.getLogger(__name__)

GROUP_TYPES = ("group", "supergroup")

SPOILER_LABELS = {
    None: "inherit",
    True: "on",
    False: "off",
}


async def is_group_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Group creators and admins may change their group's settings; the bot
    owner may too, for support."""
    if user_id == OWNER_TELE_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as e:
        logger.warning(f"get_chat_member failed for {user_id} in {chat_id}: {e}")
        return False
    return member.status in ("creator", "administrator")


async def _build_panel(
    group_id: int, db_session: AsyncSession
) -> tuple[str, InlineKeyboardMarkup]:
    overrides = await GroupCommandSettingsRepo(db_session).get_all(group_id)
    group = await TeleGroupRepo(db_session).get_group(group_id)
    spoiler = group.lore_spoiler if group else None

    default_spoiler = "on" if lore_settings.spoiler_default else "off"
    effective = default_spoiler if spoiler is None else SPOILER_LABELS[bool(spoiler)]

    lines = [
        "⚙️ <b>Group Settings</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "<b>Commands</b>",
    ]
    for cmd, label in GROUP_TOGGLEABLE.items():
        state = overrides.get(cmd, True)
        lines.append(f"• /{cmd} — {label}: <b>{'on' if state else 'off'}</b>")

    lines += [
        "",
        "<b>Lore spoilers</b>",
        f"• Answers hidden behind a spoiler: <b>{effective}</b>"
        + (" (following bot default)" if spoiler is None else ""),
        "",
        "<i>Tap a button to change a setting.</i>",
    ]

    kb = InlineKeyboardBuilder()
    for cmd in GROUP_TOGGLEABLE:
        state = overrides.get(cmd, True)
        kb.button(
            text=f"/{cmd}: {'on ✅' if state else 'off 🚫'}",
            callback_data=f"gs_cmd:{group_id}:{cmd}:{'off' if state else 'on'}",
        )
    kb.adjust(1)

    # A dot marks the group's current choice; "default" clears the override
    # rather than writing today's effective value.
    kb.row(*[
        InlineKeyboardButton(
            text=f"Spoiler: {label}" + (" ●" if spoiler is value else ""),
            callback_data=f"gs_spoiler:{group_id}:{key}",
        )
        for key, value, label in (
            ("on", True, "on"),
            ("off", False, "off"),
            ("default", None, "default"),
        )
    ])

    return "\n".join(lines), kb.as_markup()


@rt.message(Command("group_settings"))
async def group_settings(msg: Message, bot: Bot, db_session: AsyncSession):
    if msg.chat.type not in GROUP_TYPES:
        await msg.reply(
            "This command only works inside a group.",
            parse_mode=None,
        )
        return
    if not msg.from_user:
        return

    if not await is_group_admin(bot, msg.chat.id, msg.from_user.id):
        await msg.reply(
            "Only group admins can change group settings.",
            parse_mode=None,
        )
        return

    # The panel keys off a telegram_groups row; make sure one exists so a
    # first-time toggle does not trip the foreign key.
    await TeleGroupRepo(db_session).add_group(msg.chat.id, msg.chat.title or "")
    await db_session.commit()

    text, kb = await _build_panel(msg.chat.id, db_session)
    await msg.reply(text, parse_mode="HTML", reply_markup=kb)


@rt.callback_query(F.data.startswith("gs_cmd:"))
async def toggle_group_cmd(cb: CallbackQuery, bot: Bot, db_session: AsyncSession):
    _, raw_group, cmd, new_state = cb.data.split(":")
    group_id = int(raw_group)

    # Re-check on every tap: the panel may be old, and admin rights change.
    if not await is_group_admin(bot, group_id, cb.from_user.id):
        await cb.answer("Only group admins can change this.", show_alert=True)
        return

    enabled = new_state == "on"
    ok = await GroupCommandSettingsRepo(db_session).set_enabled(group_id, cmd, enabled)
    if not ok:
        await cb.answer("That command cannot be toggled per group.", show_alert=True)
        return
    await db_session.commit()

    text, kb = await _build_panel(group_id, db_session)
    if cb.message:
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning(f"could not refresh group settings panel: {e}")
    await cb.answer(f"/{cmd} is now {'enabled' if enabled else 'disabled'} here.")


@rt.callback_query(F.data.startswith("gs_spoiler:"))
async def toggle_group_spoiler(cb: CallbackQuery, bot: Bot, db_session: AsyncSession):
    _, raw_group, choice = cb.data.split(":")
    group_id = int(raw_group)

    if not await is_group_admin(bot, group_id, cb.from_user.id):
        await cb.answer("Only group admins can change this.", show_alert=True)
        return

    value = {"on": True, "off": False, "default": None}[choice]
    ok = await TeleGroupRepo(db_session).set_lore_spoiler(group_id, value)
    if not ok:
        await cb.answer("Could not find this group in my records.", show_alert=True)
        return
    await db_session.commit()

    text, kb = await _build_panel(group_id, db_session)
    if cb.message:
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning(f"could not refresh group settings panel: {e}")

    if value is None:
        await cb.answer("Spoilers now follow the bot-wide default.")
    else:
        await cb.answer(f"Lore spoilers {'on' if value else 'off'} for this group.")
