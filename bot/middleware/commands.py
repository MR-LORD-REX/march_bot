from typing import Callable, Awaitable, Any , Dict 

from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.filters import CommandObject


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
        cmd:CommandObject|None=data.get("command")
        if cmd:
            cmd_name=cmd.command.lower()
            print(f"checking availability for command : {cmd_name}")
            if not self.availability.is_enabled(cmd_name):
                await event.answer(f"The command :{cmd_name} is disabled right now , contact bot admins for the query .")
                return
        return await handler(event,data)