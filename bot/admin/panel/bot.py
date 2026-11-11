from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.admin.panel.sessions import create_login_token
from bot.auth.authority import get_authority
from bot.config.config import PANEL_URL

rt = Router()


def panel_url_for(token: str) -> str:
    base = PANEL_URL.rstrip('/')
    return f"{base}/admin/login?token={quote(token)}&next=/admin/"


@rt.message(Command("admin_panel"))
async def admin_panel(message: Message, db_session: AsyncSession):
    tele_id = message.from_user.id
    authority = await get_authority(db_session, tele_id)
    if authority not in {"owner", "admin", "moderator"}:
        await message.reply("This command is available to bot staff only.", parse_mode=None)
        return

    if not PANEL_URL:
        await message.reply(
            "The web panel URL is not configured. Set PANEL_URL to the bot API's public HTTPS URL.",
            parse_mode=None,
        )
        return

    token = await create_login_token(tele_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="Open control room", url=panel_url_for(token))
    await message.reply(
        "Your one-time admin panel link is ready. It expires in 10 minutes and can be used once.\n\n"
        "Keep it private — anyone who opens it first could use your session.",
        reply_markup=kb.as_markup(),
        parse_mode=None,
    )