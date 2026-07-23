from typing import Callable, Awaitable, Any , Dict 

from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.filters import CommandObject


from bot.DB.repo.user_repo import UserRepo

from bot.DB.repo.cmd_meta_repo import CommandMetaRepo



class CommandsAvailability:
    def __init__(self) -> None:
        self._command_store: Dict[str,bool]={}
        
    def load(self,new_status:Dict[str,bool])->None:
        self._command_store=new_status.copy()
        
    def is_enabled(self,cmd:str)->bool:
        res=self._command_store.get(cmd)
        if res is None:
            return False
        return res

class CommandChecker(BaseMiddleware):
    def __init__(self,availability:CommandsAvailability) -> None:
        self.availability=availability
        
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any]
    )->Any:
        from bot.config.config import OWNER_TELE_ID
        if event.from_user and event.from_user.id != OWNER_TELE_ID:
            db_session = data.get("db_session")
            if db_session and await UserRepo(db_session).is_banned(event.from_user.id):
                await event.answer(
                    "You have been banned from using this bot. Contact bot admins for help."
                )
                return

        cmd:CommandObject|None=data.get("command")
        if cmd:
            cmd_name=cmd.command.lower()
            print(f"checking availability for command : {cmd_name}")
            if not self.availability.is_enabled(cmd_name):
                from bot.DB.asyncsessions import session_factory
                async with session_factory() as db_session:
                    command_meta=await CommandMetaRepo(db_session).get_command_meta(cmd_name)
                    reason=command_meta.reason
                    if reason:
                        await event.answer(f"The command :{cmd_name} is disabled right now .\nReason: {reason}")
                    return
        return await handler(event,data)