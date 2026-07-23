from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import FSInputFile

import logging
from pathlib import Path

from bot.DB.repo.user_setting_repo import UserSettingsRepo
from bot.DB.repo.user_repo import UserRepo
from bot.DB.repo.game_ids_repo import GameIDs_repo
from bot.config.config import ADMIN_GC_ID

rt = Router()
logger = logging.getLogger(__name__)

img_path=Path(__file__).parent.parent / "assets" / "settings"




def _toggle_icon(state: bool) -> str:
    return "🟢 ON" if state else "🔴 OFF"


def build_settings_keyboard(settings) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if settings:
        builder.button(text="🖼️ Profile Template", callback_data="tpl_list:profile")
        builder.button(text="🎴 Character Template", callback_data="tpl_list:character")
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


@rt.callback_query(lambda c: c.data == "settings_main")
async def handle_settings_main(cb: CallbackQuery, db_session: AsyncSession):
    tele_id = cb.from_user.id
    user = await UserRepo(db_session).get_by_tele_id(tele_id)
    settings = await UserSettingsRepo(db_session).get_user_settings(tele_id)
    game_ids = await GameIDs_repo(db_session).get_UIDs(tele_id)
    active_game = await GameIDs_repo(db_session).get_active_UID(tele_id)

    text = _build_settings_text(user, game_ids, active_game, settings)
    kb = build_settings_keyboard(settings)

    if cb.message.photo:
        await cb.message.delete()
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@rt.callback_query(lambda c: c.data.startswith("tpl_list:"))
async def handle_tpl_list(cb: CallbackQuery):
    tpl_type = cb.data.split(":")[1]
    builder = InlineKeyboardBuilder()
    
    if tpl_type == "profile":
        builder.button(text="1", callback_data="tpl_prev:profile:1")
    else:
        builder.button(text="1", callback_data="tpl_prev:character:1")
        
    builder.button(text="🔙 Back", callback_data="settings_main")
    builder.adjust(2 if tpl_type == "profile" else 3, 1)
    
    text = f"Select a {tpl_type.capitalize()} Template to preview:"
    
    if cb.message.photo:
        await cb.message.delete()
        await cb.message.answer(text, reply_markup=builder.as_markup())
    else:
        await cb.message.edit_text(text, reply_markup=builder.as_markup())
    await cb.answer()


@rt.callback_query(lambda c: c.data.startswith("tpl_prev:"))
async def handle_tpl_prev(cb: CallbackQuery, db_session: AsyncSession):
    _, tpl_type, num = cb.data.split(":")
    tele_id = cb.from_user.id
    settings = await UserSettingsRepo(db_session).get_user_settings(tele_id)
    
    if settings:
        curr = settings.profile_template if tpl_type == "profile" else settings.character_template
        await cb.answer(f"Your current {tpl_type} template is {curr}")
    
    prefix = "pfp" if tpl_type == "profile" else "char"
    photo_path = img_path / f"{prefix}_{num}.png"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Set", callback_data=f"tpl_set:{tpl_type}:{num}")
    builder.button(text="🔙 Back", callback_data=f"tpl_list:{tpl_type}")
    builder.adjust(2)
    
    caption = f"Previewing {tpl_type.capitalize()} Template {num}"
    if settings:
        caption += f"\n\nYour current template is: {curr}"
    
    photo = FSInputFile(photo_path)
    
    await cb.message.delete()
    await cb.message.answer_photo(photo=photo, caption=caption, reply_markup=builder.as_markup())


@rt.callback_query(lambda c: c.data.startswith("tpl_set:"))
async def handle_tpl_set(cb: CallbackQuery, db_session: AsyncSession):
    _, tpl_type, num = cb.data.split(":")
    tele_id = cb.from_user.id
    
    if tpl_type == "profile":
        updated = await UserSettingsRepo(db_session).change_user_settings(tele_id, profile_template=int(num))
    else:
        updated = await UserSettingsRepo(db_session).change_user_settings(tele_id, character_template=int(num))
    await db_session.commit()
    
    await cb.answer(f"{tpl_type.capitalize()} template set to {num}!", show_alert=True)
    
    user = await UserRepo(db_session).get_by_tele_id(tele_id)
    game_ids = await GameIDs_repo(db_session).get_UIDs(tele_id)
    active_game = await GameIDs_repo(db_session).get_active_UID(tele_id)
    
    text = _build_settings_text(user, game_ids, active_game, updated)
    kb = build_settings_keyboard(updated)
    
    await cb.message.delete()
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


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

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    state_word = "turned ON 🟢" if updated.dalies_reminder else "turned OFF 🔴"
    await callback.answer(f"Daily Reminder {state_word}")

@rt.message(Command("suggestions"))
async def handle_suggestions(msg: Message, db_session: AsyncSession):
    if not msg.chat.type == "private":
        await msg.reply("Please send your suggestions in a private chat with the bot. 🌸")
        return
    tele_id = msg.from_user.id
    user = await UserRepo(db_session).get_by_tele_id(tele_id)
    if not user:
        await msg.reply("Hey Trailblazer! You need to log in first. Try /login 🌸")
        return
    suggestion=msg.text.replace("/suggestions ","")
    
    if len(suggestion) > 1000:
        await msg.reply("Suggestion is too long. Please send a shorter suggestion. 🌸")
        return
    if not suggestion:
        await msg.reply("Usage: /suggestions <suggestion>")
        return
    text=f"Suggestion from {user.username} - {user.display_name}\n\n{suggestion}"
    kb=InlineKeyboardBuilder()
    kb.button(text="Ban User", callback_data=f"ban_user:{tele_id}")
    from bot.core.main import bot
    await bot.send_message(ADMIN_GC_ID,text,reply_markup=kb.as_markup())
    await msg.reply("Suggestion sent to bot admins. Thank you for your feedback! 🌸")
    await db_session.commit()
