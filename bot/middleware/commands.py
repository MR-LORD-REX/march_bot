from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.filters import CommandObject
from aiogram.types import Message

from DB.asyncsessions import session_factory
from DB.repo.cmd_meta_repo import CommandMetaRepo
from DB.repo.user_repo import UserRepo
from shared.runtime import CommandsAvailability

__all__ = ["CommandsAvailability", "CommandChecker"]


class CommandChecker(BaseMiddleware):
    def __init__(self, availability: CommandsAvailability) -> None:
        self.availability = availability

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        from shared.config.settings import OWNER_TELE_ID

        if event.from_user and event.from_user.id != OWNER_TELE_ID:
            db_session = data.get("db_session")
            if db_session and await UserRepo(db_session).is_banned(event.from_user.id):
                await event.answer(
                    "You have been banned from using this bot. Contact bot admins for help."
                )
                return

        cmd: CommandObject | None = data.get("command")
        if cmd:
            cmd_name = cmd.command.lower()
            if not self.availability.is_enabled(cmd_name):
                async with session_factory() as db_session:
                    command_meta = await CommandMetaRepo(db_session).get_command_meta(
                        cmd_name
                    )
                    reason = command_meta.reason if command_meta else None
                    if reason:
                        await event.answer(
                            f"The command :{cmd_name} is disabled right now .\n"
                            f"Reason: {reason}"
                        )
                    return
        return await handler(event, data)