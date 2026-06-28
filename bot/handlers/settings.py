from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.DB.repo.user_setting_repo import UserSettingsRepo
from bot.DB.repo.user_repo import UserRepo
from bot.DB.repo.game_ids_repo import GameIDs_repo

rt = Router()
logger = logging.getLogger(__name__)



def _toggle_icon(state: bool) -> str:
    return "🟢 ON" if state else "🔴 OFF"


def build_settings_keyboard(settings) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if settings:
        daily_label = f"🔔 Daily Reminder  {'✅' if settings.dalies_reminder else '❌'}"
        builder.button(text=daily_label, callback_data="toggle_daily")
        builder.adjust(1)
    return builder.as_markup()


def _build_settings_text(user, game_ids, active_game, settings) -> str:

    lines = [
        "🌸 <b>March 7th — Settings Panel</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "👤 <b>TRAILBLAZER INFO</b>",
        f"  ├ Username     : <code>{user.username or '—'}</code>",
        f"  ├ Display Name : <b>{user.display_name or '—'}</b>",
        f"  └ Status       : {'🚫 <b>BANNED</b>' if user.banned else '✅ Active'}",
        "",
    ]


    lines.append("🎮 <b>LINKED GAME ACCOUNTS</b>")
    if game_ids:
        for idx, game in enumerate(game_ids, 1):
            active_tag = " 〔active〕" if game.active else ""
            prefix = "  └" if idx == len(game_ids) else "  ├"
            lines.append(f"{prefix} <code>{game.game_id}</code>{active_tag}")
    else:
        lines.append("  └ <i>No accounts linked — use /login</i>")
    lines.append("")


    if settings:
        lines += [
            "⚙️ <b>PREFERENCES</b>",
            f"  ├ Profile Template  : <code>{settings.profile_template}</code>",
            f"  └ Char. Template    : <code>{settings.character_template}</code>",
            "",
            "🔔 <b>REMINDERS</b>",
            f"  └ Daily Reminder    : {_toggle_icon(settings.dalies_reminder)}",
        ]
    else:
        lines.append("⚙️ <i>No preferences saved yet.</i>")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    return "\n".join(lines)




@rt.message(Command("settings"))
async def cmd_settings(msg: Message, db_session: AsyncSession):
    tele_id = msg.from_user.id
    user = await UserRepo(db_session).get_by_tele_id(tele_id)
    if not user:
        await msg.reply("Hey Trailblazer! You need to log in first. Try /login 🌸")
        return

    settings    = await UserSettingsRepo(db_session).get_user_settings(tele_id)
    game_ids    = await GameIDs_repo(db_session).get_UIDs(tele_id)
    active_game = await GameIDs_repo(db_session).get_active_UID(tele_id)

    text = _build_settings_text(user, game_ids, active_game, settings)
    kb   = build_settings_keyboard(settings)
    await msg.reply(text, parse_mode="HTML", reply_markup=kb)


@rt.callback_query(lambda c: c.data == "toggle_daily")
async def toggle_daily_reminder(callback: CallbackQuery, db_session: AsyncSession):
    tele_id  = callback.from_user.id
    settings = await UserSettingsRepo(db_session).get_user_settings(tele_id)

    if not settings:
        await callback.answer("Settings not found!", show_alert=True)
        return

    updated = await UserSettingsRepo(db_session).change_user_settings(
        tele_id,
        dalies_reminder=not settings.dalies_reminder,
    )
    await db_session.commit()

    user        = await UserRepo(db_session).get_by_tele_id(tele_id)
    game_ids    = await GameIDs_repo(db_session).get_UIDs(tele_id)
    active_game = await GameIDs_repo(db_session).get_active_UID(tele_id)

    text = _build_settings_text(user, game_ids, active_game, updated)
    kb   = build_settings_keyboard(updated)

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    state_word = "turned ON 🟢" if updated.dalies_reminder else "turned OFF 🔴"
    await callback.answer(f"Daily Reminder {state_word}")