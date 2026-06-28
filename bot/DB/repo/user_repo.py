from sqlalchemy import select 
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Sequence

from aiogram.types import Message

import logging

from bot.DB.repo.base import BaseRepo
from bot.DB import Users
from bot.DB.models.users_in_gc import UsersInGroup

logger=logging.getLogger(__name__)

class UserRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(Users, session)
        self.model: type[Users] = Users
        
    async def get_by_tele_id(self, telegram_id: int) -> Users | None:
        query = select(self.model).where(self.model.telegram_id == telegram_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def add_user(
        self,tele_id:int,
        user_name:str|None=None,
        display_name:str|None=None
        ) -> bool | Users:
        user=await self.get_by_tele_id(tele_id)
        user=Users(
            telegram_id=tele_id,
            username=user_name,
            display_name=display_name
        )
        await self.add(user)
        return user
    
    async def remove_user(self,tele_id:int)->bool:
        user=await self.get_by_tele_id(tele_id)
        if not user:
            logger.warning(f"user not found for tele_id {tele_id}")
            return False
        await self.delete(user)
        return True
    
    async def ban_user(self, tele_id:int)->bool:
        user= await self.get_by_tele_id(tele_id)
        if not user:
            logger.warning(f"user not found for tele_id {tele_id}")
            return False
        user.banned=True
        await self.update(user)
        return True
        
    async def add_warn(self,tele_id)-> bool:
        user=await self.get_by_tele_id(tele_id)
        if not user:
            logger.warning(f"user not found for tele_id {tele_id}")
            return False
        user.warns+=1
        await self.update(user)
        return True
    
    async def remove_warn(self,tele_id:int)-> bool:
        user= await self.get_by_tele_id(tele_id)
        if not user:
            logger.warning(f"user not found for tele_id {tele_id}")
            return False
        user.warns-=1
        await self.update(user)
        return True
    
    async def unban_user(self,tele_id:int)->bool:
        user=await self.get_by_tele_id(tele_id)
        if not user:
            logger.warning(f"user not found for tele_id {tele_id}")
            return False
        user.banned=False
        await self.update(user)
        return True
    
    async def get_groups(self, tele_id: int) -> Sequence[UsersInGroup]:
        query = select(self.model).where(self.model.telegram_id == tele_id).options(
            selectinload(Users.groups).selectinload(UsersInGroup.group)
        )
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"user not found for tele_id {tele_id}")
            return []
        
        return user.groups
    
    
    