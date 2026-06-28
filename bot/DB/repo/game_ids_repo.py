from typing import Type,List,Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.DB.base import base
from bot.DB.repo.base import BaseRepo
from bot.DB.models.game_ids import GameID

logger=logging.getLogger(__name__)

class GameIDs_repo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(GameID, session)
        self.model:type[GameID]=GameID
        
    async def get_UIDs(self,tele_id:int)-> Sequence[GameID]:
        query=select(self.model).where(self.model.user_id==tele_id)
        UIDs=await self.session.execute(query)
        return UIDs.scalars().all()
    
    async def get_UID(self,tele_id:int,game_id:int)-> GameID|None:
        query=select(self.model).where(self.model.user_id==tele_id,self.model.game_id==game_id)
        UIDs=await self.session.execute(query)
        return UIDs.scalars().first()
    
    async def get_active_UID(self,tele_id:int)-> GameID|None:
        query=select(self.model).where(self.model.user_id==tele_id,self.model.active==True)
        UIDs=await self.session.execute(query)
        return UIDs.scalars().first()
    
    async def add_game_UID(self,tele_id:int,game_id:int)-> GameID|bool:
        uid= await self.get_UID(tele_id=tele_id,game_id=game_id)
        all_uids= await self.get_UIDs(tele_id)
        if uid:
            logger.error(f"user : {tele_id} already has game id :{game_id} set")
            return False
        for existing_uid in all_uids:
            existing_uid.active = False
            await self.update(existing_uid)
        uid=GameID(
            user_id=tele_id,
            game_id=game_id,
            active=True
        )
        await self.add(uid)
        return uid
    
    async def remove_game_UID(self,tele_id:int,game_id:int)-> GameID|None:
        uid= await self.get_UID(tele_id=tele_id,game_id=game_id)
        if not uid:
            logger.error(f"user : {tele_id} has not set game id :{game_id} ")
            return None
        await self.delete(uid)
        
        remaining_uids = await self.get_UIDs(tele_id)
        if remaining_uids:
            next_uid = remaining_uids[0]
            next_uid.active = True
            await self.session.merge(next_uid)
            return next_uid
        return None
    
    async def switch_uid(self,tele_id:int,game_id:int) -> GameID|None :
        current=await self.get_active_UID(tele_id)
        target=await self.get_UID(tele_id,game_id)
        if not current or not target:
            return None
        current.active=False
        target.active=True
        await self.update(current)
        await self.update(target)
        return target
    
    async def add_auth_token(self,tele_id:int,auth_token:str) -> GameID | None :
        current=await self.get_active_UID(tele_id)
        if not current :
            return None
        current.auth_token=auth_token
        await self.update(current)
        return current
    
    async def remove_auth_token(self,tele_id:int) -> bool:
        current=await self.get_active_UID(tele_id)
        if not current or not current.auth_token:
            return False
        current.auth_token=None
        await self.update(current)
        return True