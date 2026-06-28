from typing import Type , Literal , Sequence
from datetime import datetime, timedelta , timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.DB.repo.base import BaseRepo
from bot.DB.models.cache import Cache
from bot.config.config import CACHE_TTL


class CacheRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(Cache, session)
        self.model: type[Cache] = Cache
        
    async def get_cache(
        self,tele_id:int,
        cache_type:Literal['PFP','CHAR','MOC','PF','ANO','AS'],
        slot:int|None=None
        )->Cache|None:
        
        query=select(self.model).where(
            self.model.telegram_id==tele_id,
            self.model.type==cache_type,
            self.model.slot==slot
            )
        
        result=await self.session.execute(query)
        cache_entry = result.scalars().first()
        if cache_entry:
            age=datetime.now(timezone.utc)-cache_entry.created_at
            if age<timedelta(seconds=CACHE_TTL):
                return cache_entry
            else:
                await self.delete(cache_entry)
        return None
        
    async def set_cache(
        self,tele_id:int,
        file_id:str,
        cache_type:Literal['PFP','CHAR','MOC','PF','ANO','AS'],
        data:str|None,
        slot:int|None=None
        )->None:
        cache=await self.get_cache(tele_id,cache_type,slot=slot)
        if cache:
            cache.file_id=file_id
            cache.data=data
            cache.slot=slot
            cache.created_at=datetime.now(timezone.utc)
            await self.update(cache)
        else:
            new=Cache(
                telegram_id=tele_id,
                file_id=file_id,
                data=data,
                slot=slot,
                type=cache_type,
                created_at=datetime.now(timezone.utc)
            )
            await self.add(new)
    
    async def get_all_cache(self,tele_id:int)->Sequence[Cache]:
        query=select(self.model).where(self.model.telegram_id==tele_id)
        result=await self.session.execute(query)
        return result.scalars().all()
    
    async def delete_all_cache(self,tele_id:int)->None:
        all_cache=await self.get_all_cache(tele_id)
        for cache in all_cache:
            await self.delete(cache)
        