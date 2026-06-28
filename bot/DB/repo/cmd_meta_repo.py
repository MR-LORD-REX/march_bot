

from typing import Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.DB.base import base
from bot.DB.repo.base import BaseRepo
from bot.DB.models.command_meta import CommandsMeta

logger=logging.getLogger(__name__)

class CommandMetaRepo(BaseRepo):
    def __init__(self,session: AsyncSession):
        super().__init__(CommandsMeta, session)
        self.model: type[CommandsMeta] = CommandsMeta
        
    async def add_commands(
        self,
        cmds:set[str]
        )-> CommandsMeta|None:
            all=await self.get_all()
            existing_cmds = {cmd_obj.cmd for cmd_obj in all}
            
            for cmd in cmds:
                if cmd not in existing_cmds:
                    new_cmd = CommandsMeta(cmd=cmd, active=True)
                    await self.add(new_cmd)
            
            await self.session.commit()
    
    async def remove_cmd(self, cmd: str) -> bool:
        query = select(self.model).where(self.model.cmd == cmd)
        result = await self.session.execute(query)
        command = result.scalar_one_or_none()
        
        if not command:
            logger.warning(f"command not found: {cmd}")
            return False
        
        await self.delete(command)
        return True
    
    async def update_cmd(self, cmd: str, active: bool) -> bool:
        query = select(self.model).where(self.model.cmd == cmd)
        result = await self.session.execute(query)
        command = result.scalar_one_or_none()
        
        if not command:
            logger.warning(f"command not found: {cmd}")
            return False
        
        command.active = active
        await self.update(command)
        return True
    
    async def get_all_commands(self) -> dict[str, bool]:
        all_cmds = await self.get_all()
        return {cmd.cmd: cmd.active for cmd in all_cmds} 
    
    