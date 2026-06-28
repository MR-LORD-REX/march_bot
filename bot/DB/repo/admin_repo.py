from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Type , Literal

from bot.DB.repo.base import BaseRepo
from bot.DB.models.admins import Admins

class AdminRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(Admins, session)
        self.model: type[Admins] = Admins
    
    async def get_admin(self, telegram_id: int) -> Admins | None:
        query = select(self.model).where(self.model.telegram_id == telegram_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def add_admin(
        self,
        telegram_id: int,
        authority: Literal["basic","moderator","admin","owner"],
        display_name: str | None = None,
        username: str | None = None,
    ) -> Admins:
        admin = Admins(
            telegram_id=telegram_id,
            authority=authority,
            display_name=display_name,
            username=username,
        )
        await self.add(admin)
        return admin
    
    async def remove_admin(self, telegram_id: int) -> bool:
        admin = await self.get_admin(telegram_id)
        if not admin:
            return False
        await self.delete(admin)
        return True

    async def update_admin(
        self,
        telegram_id: int,
        authority: Literal["basic","moderator","admin","owner"],
        username: str | None = None,
        display_name: str | None = None,
    ) -> Admins | None:
        admin = await self.get_admin(telegram_id)
        if not admin:
            return None 
        if username:
            admin.username = username
        if display_name:
            admin.display_name = display_name
        if authority:
            admin.authority = authority
        await self.update(admin)
        return admin
    
    async def get_all_admins(self) -> list[Admins]:
        query = select(self.model)
        result = await self.session.execute(query)
        return result.scalars().all()
    