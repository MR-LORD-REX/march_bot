from sqlalchemy import Select 
from sqlalchemy.ext.asyncio import AsyncSession
from typing import TypeVar, Generic, Type, Sequence

from bot.DB.base import base

T = TypeVar("T", bound=base)

class BaseRepo(Generic[T]):
    def __init__(self, model: Type[T], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_all(self) -> Sequence[T]:
        result = await self.session.execute(Select(self.model))
        return result.scalars().all()
    
    async def add(self, obj: T) -> None:
        self.session.add(obj)
        await self.session.flush()
        
    async def delete(self, obj: T) -> None:
        await self.session.delete(obj)
        await self.session.flush()
        
    async def update(self, obj: T) -> None:
        self.session.add(obj)
        await self.session.flush()