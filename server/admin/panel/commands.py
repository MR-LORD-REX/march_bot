"""Telegram command menu synchronization and runtime command toggles.

The database remains the source of truth for enable/disable state. Telegram
command scopes are presentation only: they affect quick-access menus, never
authorization, so staff checks stay in the handler and panel layers.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from DB.repo.cmd_meta_repo import CommandMetaRepo
from shared.config.settings import ADMIN_GC_ID, cmdavailability
from shared.i18n import available_languages, t

logger = logging.getLogger(__name__)

PUBLIC_COMMANDS = {
    "start": "Start the bot",
    "help": "Show available commands",
    "login": "Link a game account",
    "logout": "Unlink the active game account",
    "switch": "Switch the active game account",
    "myuid": "Show linked game accounts",
    "myc": "Generate your profile card",
    "settings": "Open preferences",
    "notes": "Show live in-game notes",
    "banners": "Show current banners",
    "events": "Show current events",
    "endgames": "Show endgame information",
    "moc": "Generate a Memory of Chaos card",
    "purefiction": "Generate a Pure Fiction card",
    "apoc": "Generate an Apocalyptic Shadow card",
    "anomaly": "Generate an Anomaly Arbitration card",
    "ask": "Ask about HSR lore",
    "ask_reset": "Start a fresh lore conversation",
    "ask_status": "Show lore usage",
    "suggestions": "Send feedback to the staff",
    "token_help": "How to add HoYoLAB cookies",
}

ADMIN_COMMANDS = {
    "admin_help": "Show staff commands",
    "admin_panel": "Open the web control room",
    "r": "Reply to a report",
    "report_close": "Close a report",
    "edit_commands": "Manage command availability",
    "update_assets": "Refresh game assets",
    "broadcast": "Broadcast a message",
}

DEFAULT_SCOPES = {"public", "private", "groups", "admins"}


def _descriptions(commands: dict[str, str], language: str = "en") -> list[BotCommand]:
    localized: dict[str, str] = {}
    for name, fallback in commands.items():
        key = f"commands.{name}"
        value = t(key, language)
        localized[name] = fallback if value == key else value
    return [BotCommand(command=name, description=description[:256]) for name, description in localized.items()]


async def sync_menu(bot: Bot, enabled: dict[str, bool], scope: str = "public") -> None:
    """Push one menu scope. Disabled commands are omitted, not described as off."""
    if scope == "public":
        target = BotCommandScopeDefault()
        commands = PUBLIC_COMMANDS
    elif scope == "private":
        target = BotCommandScopeAllPrivateChats()
        commands = PUBLIC_COMMANDS
    elif scope == "groups":
        target = BotCommandScopeAllGroupChats()
        commands = PUBLIC_COMMANDS
    elif scope == "admins":
        target = BotCommandScopeChat(chat_id=ADMIN_GC_ID)
        commands = {**PUBLIC_COMMANDS, **ADMIN_COMMANDS}
    else:
        raise ValueError(f"unknown command scope {scope!r}")

    available = [name for name in commands if enabled.get(name, True)]
    payload = _descriptions({name: commands[name] for name in available})
    if payload:
        await bot.set_my_commands(payload, scope=target)
    else:
        await bot.delete_my_commands(scope=target)


async def sync_all_menus(bot: Bot, enabled: dict[str, bool], scopes: set[str] | None = None) -> list[str]:
    results: list[str] = []
    for scope in sorted(scopes or DEFAULT_SCOPES):
        try:
            await sync_menu(bot, enabled, scope)
            results.append(scope)
        except Exception as exc:
            logger.warning("could not synchronize command scope %s: %s", scope, exc)
    return results


async def set_command_state(repo: CommandMetaRepo, cmd: str, active: bool, reason: str = "") -> dict[str, bool]:
    meta = await repo.get_command_meta(cmd)
    if not meta:
        raise KeyError(cmd)
    meta.active = active
    meta.reason = "" if active else reason
    await repo.update(meta)
    await repo.session.commit()
    status = await repo.get_all_commands()
    cmdavailability.load(status)
    return status


async def current_state(repo: CommandMetaRepo) -> dict[str, bool]:
    return await repo.get_all_commands()


def supported_languages() -> dict[str, str]:
    return available_languages()