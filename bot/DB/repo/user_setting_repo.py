from typing import Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.DB.base import base
from bot.DB.models.user_settings import UserSettings
from bot.DB.repo.base import BaseRepo

class UserSettingsRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(UserSettings, session)
        self.model: Type[UserSettings]=UserSettings
        
    async def add_user_settings(self,tele_id:int)->UserSettings:
        query = select(self.model).where(self.model.user_id == tele_id)
        result = await self.session.execute(query)
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = UserSettings(
                user_id=tele_id,
            )
            await self.add(settings)
        return settings
    
    async def get_user_settings(self, tele_id: int) -> UserSettings:
        query = select(self.model).where(self.model.user_id == tele_id)
        result = await self.session.execute(query)
        settings = result.scalar_one_or_none()
        return settings
    
    async def change_user_settings(self, tele_id: int, **kwargs) -> UserSettings:
        settings = await self.get_user_settings(tele_id)
        if settings is None:
            settings = await self.add_user_settings(tele_id)
        
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        
        await self.update(settings)
        return settings
    
    async def get_all_users_with_daily_reminder(self) -> list[int]:
        query = select(self.model).where(self.model.dalies_reminder == True)
        result = await self.session.execute(query)
        settings_list = result.scalars().all()
        return [settings.user_id for settings in settings_list]
    
    async def get_all_users_with_weekly_reminder(self) -> list[int]:
        query = select(self.model).where(self.model.weekly_reminder == True)
        result = await self.session.execute(query)
        settings_list = result.scalars().all()
        return [settings.user_id for settings in settings_list]
    
    async def get_all_users_with_perform_daily(self) -> list[int]:
        query = select(self.model).where(self.model.perform_daily == True)
        result = await self.session.execute(query)
        settings_list = result.scalars().all()
        return [settings.user_id for settings in settings_list]