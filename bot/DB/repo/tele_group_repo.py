from typing import Type,List,Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.DB.base import base
from bot.DB.repo.base import BaseRepo
from bot.DB.models.tele_group import TeleGroup
from bot.DB.models.users_in_gc import UsersInGroup

logger=logging.getLogger(__name__)

class TeleGroupRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(TeleGroup, session)
        self.model:type[TeleGroup]=TeleGroup
        
    async def get_group(self,group_id:int)->TeleGroup|None:
        query=select(self.model).where(self.model.group_id==group_id)
        gc=await self.session.execute(query)
        if gc :
            return gc.scalar_one_or_none()
        return None
        
    async def add_group(self,group_id:int,group_name:str)->TeleGroup|bool:
        gc=await self.get_group(group_id)
        if gc:
            logger.error(f"group: {group_name} already exists")
            return False
        new_gc=TeleGroup(
            group_id=group_id,
            group_name=group_name,
            banned=False
        )
        await self.add(new_gc)
        await self.session.commit()
        return new_gc
    
    async def get_all_users(self, group_id: int) -> list[UsersInGroup]:
        query = select(TeleGroup).where(TeleGroup.group_id == group_id).options(
            selectinload(TeleGroup.users).selectinload(UsersInGroup.user)
        )
        result = await self.session.execute(query)
        group = result.scalar_one_or_none()
        
        if not group:
            logger.warning(f"group not found: {group_id}")
            return []
        
        return group.users
    
    