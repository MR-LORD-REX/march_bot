from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import FSInputFile

import html
import logging
from pathlib import Path

from DB.repo.user_setting_repo import UserSettingsRepo
from DB.repo.user_repo import UserRepo
from DB.repo.game_ids_repo import GameIDs_repo
from shared.config.settings import ADMIN_GC_ID
from shared.i18n import available_languages, language_for, normalize_language, t

rt = Router()
logger = logging.getLogger(__name__)

img_path = Path(__file__).parent.parent / "assets" / "settings"
DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━"


def _toggle_icon(state: bool) -> str:
    return "🟢 ON" if state else "🔴 OFF"


def _language_name(code: str) -> str:
    languages = available_languages()
    return languages.get(normalize_language(code), languages.get("en", "English"))


def build_settings_keyboard(settings, lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if settings:
        builder.button(
            text=f"🖼️ {t('settings.profile_template_button', lang)}",
            callback_data="tpl_list:profile",
        )
        builder.button(
            text=f"🎴 {t('settings.character_template_button', lang)}",
            callback_data="tpl_list:character",
        )
        state = t("common.on" if settings.dalies_reminder else "common.off", lang)
        builder.button(
            text=f"🔔 {t('settings.daily_reminder_button', lang, state=state)}",
            callback_data="toggle_daily",
        )
        builder.button(
            text=f"🌐 {t('settings.language_button', lang, language=_language_name(lang))}",
            callback_data="lang_menu",
        )
        builder.adjust(1)
    return builder.as_markup()


def _build_settings_text(user, game_ids, active_game, settings, lang: str = "en") -> str:
    username = html.escape(str(user.username or "—"))
    display_name = html.escape(str(user.display_name or "—"))
    status = (
        f"🚫 <b>{t('settings.banned', lang)}</b>"
        if user.banned
        else f"✅ {t('settings.active', lang)}"
    )
    lines = [
        f"🌸 <b>{t('settings.title', lang)}</b>",
        DIVIDER,
        "",
        f"👤 <b>{t('settings.trailblazer_header', lang)}</b>",
        t("settings.username", lang, username=username),
        t("settings.display_name", lang, display_name=display_name),
        t("settings.status", lang, status=status),
        "",
        f"🎮 <b>{t('settings.accounts_header', lang)}</b>",
    ]

    if game_ids:
        for idx, game in enumerate(game_ids, 1):
            active_tag = f" 〔{t('settings.active_tag', lang).strip(' []')}〕" if game.active else ""
            prefix = "  └" if idx == len(game_ids) else "  ├"
            lines.append(f"{prefix} {t('settings.account_line', lang, uid=html.escape(str(game.game_id)), active=active_tag)}")
    else:
        lines.append(f"  └ <i>{t('settings.no_accounts', lang)}</i>")
    lines.append("")

    if settings:
        lines += [
            f"⚙️ <b>{t('settings.preferences_header', lang)}</b>",
            t("settings.profile_template", lang, value=settings.profile_template),
            t("settings.character_template", lang, value=settings.character_template),
            t("settings.language", lang, value=_language_name(settings.lang)),
            "",
            f"🔔 <b>{t('settings.reminders_header', lang)}</b>",
            t("settings.daily_reminder", lang, value=_toggle_icon(settings.dalies_reminder)),
        ]
    else:
        lines.append(f"⚙️ <i>{t('settings.no_preferences', lang)}</i>")

    lines += ["", DIVIDER]
    return "\n".join(lines)


async def _render_settings(tele_id: int, db_session: AsyncSession):
    user = await UserRepo(db_session).get_by_tele_id(tele_id)
    settings = await UserSettingsRepo(db_session).get_user_settings(tele_id)
    game_ids = await GameIDs_repo(db_session).get_UIDs(tele_id)
    active_game = await GameIDs_repo(db_session).get_active_UID(tele_id)
    lang = await language_for(db_session, tele_id)
    return user, settings, game_ids, active_game, lang


@rt.message(Command("settings"))
async def cmd_settings(msg: Message, db_session: AsyncSession):
    tele_id = msg.from_user.id
    user, settings, game_ids, active_game, lang = await _render_settings(tele_id, db_session)
    if not user:
        await msg.reply(t("common.login_required", lang))
        return

    text = _build_settings_text(user, game_ids, active_game, settings, lang)
    kb = build_settings_keyboard(settings, lang)
    await msg.reply(text, parse_mode="HTML", reply_markup=kb)


@rt.callback_query(lambda c: c.data == "settings_main")
async def handle_settings_main(cb: CallbackQuery, db_session: AsyncSession):
    tele_id = cb.from_user.id
    user, settings, game_ids, active_game, lang = await _render_settings(tele_id, db_session)
    if not user:
        await cb.answer(t("common.login_required", lang), show_alert=True)
        return

    text = _build_settings_text(user, game_ids, active_game, settings, lang)
    kb = build_settings_keyboard(settings, lang)

    if cb.message.photo:
        await cb.message.delete()
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


@rt.callback_query(lambda c: c.data == "lang_menu")
async def handle_language_menu(cb: CallbackQuery, db_session: AsyncSession):
    lang = await language_for(db_session, cb.from_user.id)
    builder = InlineKeyboardBuilder()
    for code, name in available_languages().items():
        marker = "✅ " if code == lang else ""
        builder.button(text=f"{marker}{name}", callback_data=f"lang_set:{code}")
    builder.button(text=f"🔙 {t('common.back', lang)}", callback_data="settings_main")
    builder.adjust(1)
    await cb.message.edit_text(
        t("settings.language_menu", lang),
        reply_markup=builder.as_markup(),
    )
    await cb.answer()


@rt.callback_query(lambda c: c.data.startswith("lang_set:"))
async def handle_language_set(cb: CallbackQuery, db_session: AsyncSession):
    code = cb.data.split(":", 1)[1]
    languages = available_languages()
    if code not in languages:
        await cb.answer("Unsupported language.", show_alert=True)
        return

    tele_id = cb.from_user.id
    await UserSettingsRepo(db_session).change_user_settings(tele_id, lang=code)
    await db_session.commit()

    user, settings, game_ids, active_game, lang = await _render_settings(tele_id, db_session)
    if not user:
        await cb.answer(t("common.login_required", lang), show_alert=True)
        return

    text = _build_settings_text(user, game_ids, active_game, settings, lang)
    kb = build_settings_keyboard(settings, lang)
    if cb.message.photo:
        await cb.message.delete()
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer(t("settings.language_set", lang, language=languages[code]))


@rt.callback_query(lambda c: c.data.startswith("tpl_list:"))
async def handle_tpl_list(cb: CallbackQuery, db_session: AsyncSession):
    tpl_type = cb.data.split(":")[1]
    lang = await language_for(db_session, cb.from_user.id)
    template = "Profile" if tpl_type == "profile" else "Character"
    builder = InlineKeyboardBuilder()

    if tpl_type == "profile":
        builder.button(text="1", callback_data="tpl_prev:profile:1")
    else:
        builder.button(text="1", callback_data="tpl_prev:character:1")

    builder.button(text=f"🔙 {t('common.back', lang)}", callback_data="settings_main")
    builder.adjust(2 if tpl_type == "profile" else 3, 1)

    text = t("settings.template_list", lang, template=template)

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
    lang = await language_for(db_session, tele_id)
    template = "Profile" if tpl_type == "profile" else "Character"

    curr = None
    if settings:
        curr = settings.profile_template if tpl_type == "profile" else settings.character_template
        await cb.answer(f"Current template: {curr}")

    prefix = "pfp" if tpl_type == "profile" else "char"
    photo_path = img_path / f"{prefix}_{num}.png"

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"✅ {t('common.set', lang)}",
        callback_data=f"tpl_set:{tpl_type}:{num}",
    )
    builder.button(text=f"🔙 {t('common.back', lang)}", callback_data=f"tpl_list:{tpl_type}")
    builder.adjust(2)

    caption = t("settings.template_preview", lang, template=template, number=num)
    if curr is not None:
        caption += f"\n\n{t('settings.template_current', lang, value=curr)}"

    photo = FSInputFile(photo_path)
    await cb.message.delete()
    await cb.message.answer_photo(photo=photo, caption=caption, reply_markup=builder.as_markup())


@rt.callback_query(lambda c: c.data.startswith("tpl_set:"))
async def handle_tpl_set(cb: CallbackQuery, db_session: AsyncSession):
    _, tpl_type, num = cb.data.split(":")
    tele_id = cb.from_user.id

    if tpl_type == "profile":
        await UserSettingsRepo(db_session).change_user_settings(tele_id, profile_template=int(num))
    else:
        await UserSettingsRepo(db_session).change_user_settings(tele_id, character_template=int(num))
    await db_session.commit()

    lang = await language_for(db_session, tele_id)
    template = "Profile" if tpl_type == "profile" else "Character"
    await cb.answer(
        t("settings.template_set", lang, template=template, number=num),
        show_alert=True,
    )

    user, updated, game_ids, active_game, lang = await _render_settings(tele_id, db_session)
    text = _build_settings_text(user, game_ids, active_game, updated, lang)
    kb = build_settings_keyboard(updated, lang)

    await cb.message.delete()
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@rt.callback_query(lambda c: c.data == "toggle_daily")
async def toggle_daily_reminder(callback: CallbackQuery, db_session: AsyncSession):
    tele_id = callback.from_user.id
    settings = await UserSettingsRepo(db_session).get_user_settings(tele_id)

    if not settings:
        await callback.answer("Settings not found!", show_alert=True)
        return

    updated = await UserSettingsRepo(db_session).change_user_settings(
        tele_id,
        dalies_reminder=not settings.dalies_reminder,
    )
    await db_session.commit()

    user, updated, game_ids, active_game, lang = await _render_settings(tele_id, db_session)
    text = _build_settings_text(user, game_ids, active_game, updated, lang)
    kb = build_settings_keyboard(updated, lang)

    if callback.message.photo:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    state_word = t("common.on" if updated.dalies_reminder else "common.off", lang)
    await callback.answer(
        t("settings.daily_reminder_button", lang, state=state_word)
    )


@rt.message(Command("suggestions"))
async def handle_suggestions(msg: Message, db_session: AsyncSession):
    lang = await language_for(db_session, msg.from_user.id)
    if msg.chat.type != "private":
        await msg.reply(t("settings.suggestions_private", lang))
        return

    tele_id = msg.from_user.id
    user = await UserRepo(db_session).get_by_tele_id(tele_id)
    if not user:
        await msg.reply(t("common.login_required", lang))
        return

    args = msg.text.split(maxsplit=1)
    suggestion = args[1].strip() if len(args) > 1 else ""
    if len(suggestion) > 1000:
        await msg.reply(t("settings.suggestions_too_long", lang))
        return
    if not suggestion:
        await msg.reply(t("settings.suggestions_usage", lang))
        return

    from shared.runtime import bot_runtime

    username = html.escape(str(user.username or "unknown"))
    display_name = html.escape(str(user.display_name or "unknown"))
    text = f"Suggestion from {username} - {display_name}\n\n{html.escape(suggestion)}"
    kb = InlineKeyboardBuilder()
    kb.button(text="Ban User", callback_data=f"ban_user:{tele_id}")
    await bot_runtime.bot.send_message(ADMIN_GC_ID, text, reply_markup=kb.as_markup())
    await msg.reply(t("settings.suggestions_sent", lang))
    await db_session.commit()