from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from DB.repo.tele_group_repo import TeleGroupRepo
from DB.repo.user_repo import UserRepo
from DB.repo.users_in_group_repo import UsersInGroupRepo

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher


class CommandsAvailability:
    def __init__(self) -> None:
        self._command_store: Dict[str, bool] = {}

    def load(self, new_status: Dict[str, bool]) -> None:
        self._command_store = new_status.copy()

    def is_enabled(self, cmd: str) -> bool:
        return bool(self._command_store.get(cmd, False))


class Auser(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tele_id: int
    username: str | None
    display_name: str | None


class Agroup(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    group_id: int
    members: set[int]


class UsersRecord:
    def __init__(self) -> None:
        self._record: Dict[int, Auser] = {}

    def is_registered(self, tele_id: int) -> bool:
        return tele_id in self._record

    def get_user(self, tele_id: int) -> Auser | None:
        return self._record.get(tele_id)

    def get_username(self, tele_id: int) -> str | None:
        user = self.get_user(tele_id)
        return user.username if user else None

    def get_display_name(self, tele_id: int) -> str | None:
        user = self.get_user(tele_id)
        return user.display_name if user else None


class GroupsRecord:
    def __init__(self) -> None:
        self._record: Dict[int, Agroup] = {}

    def is_registered(self, group_id: int) -> bool:
        return group_id in self._record

    def get_group(self, group_id: int) -> Agroup | None:
        return self._record.get(group_id)

    def is_user_in_group(self, tele_id: int, group_id: int) -> bool:
        group = self.get_group(group_id)
        return bool(group and tele_id in group.members)


async def load_users(session: AsyncSession, record: UsersRecord) -> None:
    all_users = await UserRepo(session).get_all()
    record._record = {
        user.telegram_id: Auser(
            tele_id=user.telegram_id,
            username=user.username,
            display_name=user.display_name,
        )
        for user in all_users
    }


async def load_groups(session: AsyncSession, record: GroupsRecord) -> None:
    groups = await TeleGroupRepo(session).get_all()
    memberships = await UsersInGroupRepo(session).get_all_grouped_by_group()
    record._record = {
        group.group_id: Agroup(
            group_id=group.group_id,
            members=memberships.get(group.group_id, set()),
        )
        for group in groups
    }


class BotRuntime:
    """Process-wide aiogram objects set once by the server entrypoint.

    Handlers and shared services need the running bot for out-of-band sends,
    but must not import ``server.runtime`` directly. Keeping this accessor in
    ``shared`` preserves the one-way dependency bot -> shared.
    """

    def __init__(self) -> None:
        self._bot: "Bot | None" = None
        self._dispatcher: "Dispatcher | None" = None

    def bind(self, bot: "Bot", dispatcher: "Dispatcher | None" = None) -> None:
        self._bot = bot
        self._dispatcher = dispatcher

    @property
    def bot(self) -> "Bot":
        if self._bot is None:
            raise RuntimeError("bot runtime has not been initialised")
        return self._bot

    @property
    def dispatcher(self) -> "Dispatcher":
        if self._dispatcher is None:
            raise RuntimeError("dispatcher runtime has not been initialised")
        return self._dispatcher


bot_runtime = BotRuntime()