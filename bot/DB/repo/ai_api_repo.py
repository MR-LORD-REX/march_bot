from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.DB.repo.base import BaseRepo
from bot.DB.models.ai_api import AiApi
from bot.DB.models.ai_models import AiModels
from bot.utils.auth import encrypt_str, decrypt_str

logger = logging.getLogger(__name__)


class AiApiRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(AiApi, session)
        self.model: type[AiApi] = AiApi

    async def get_by_name(self, api_name: str) -> AiApi | None:
        query = select(self.model).where(self.model.api_name == api_name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def add_key(
        self,
        api_name: str,
        api_key: str,
        models: list[tuple[str, int, int]],
    ) -> AiApi | None:
        """Store a key plus one quota bucket per model. Returns None if the
        name is taken -- names are how admins refer to a key they can't see."""
        if await self.get_by_name(api_name):
            logger.warning(f"api key name already exists: {api_name}")
            return None

        entry = AiApi(
            api_name=api_name,
            api_key=encrypt_str(api_key),
            is_active=True,
        )
        await self.add(entry)

        for model_name, rpm, rpd in models:
            await self.add(
                AiModels(
                    model_name=model_name,
                    rpm=rpm,
                    rpd=rpd,
                    api_name=api_name,
                    is_active=True,
                )
            )
        return entry

    async def remove_key(self, api_name: str) -> bool:
        entry = await self.get_by_name(api_name)
        if not entry:
            logger.warning(f"api key not found: {api_name}")
            return False
        await self.delete(entry)
        return True

    async def set_active(self, api_name: str, active: bool) -> bool:
        entry = await self.get_by_name(api_name)
        if not entry:
            logger.warning(f"api key not found: {api_name}")
            return False
        entry.is_active = active
        await self.update(entry)
        return True

    async def get_all_with_models(self) -> Sequence[AiApi]:
        query = select(self.model).options(selectinload(AiApi.models))
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_active_buckets(self) -> list[dict]:
        """Every usable (key, model) pair, keys decrypted, for the rotator.

        A key that fails to decrypt is skipped rather than raised: one bad
        row (say, after a FERNET_KEY rotation) should cost that bucket, not
        every /ask in the bot.
        """
        query = (
            select(self.model)
            .where(self.model.is_active.is_(True))
            .options(selectinload(AiApi.models))
        )
        result = await self.session.execute(query)

        buckets: list[dict] = []
        for entry in result.scalars().all():
            try:
                plain = decrypt_str(entry.api_key)
            except Exception as e:
                logger.error(f"failed to decrypt api key '{entry.api_name}': {e}")
                continue
            for m in entry.models:
                if not m.is_active:
                    continue
                buckets.append({
                    "api_name": entry.api_name,
                    "api_key": plain,
                    "model_name": m.model_name,
                    "rpm": m.rpm,
                    "rpd": m.rpd,
                })
        return buckets

    async def sync_models(self, models: list[tuple[str, int, int]]) -> int:
        """Give every stored key a bucket for each model in `models`.

        Called on startup so adding a model to LORE_MODELS backfills the keys
        that were added before it existed. Returns the number of rows created.
        """
        keys = await self.get_all_with_models()
        created = 0
        for entry in keys:
            have = {m.model_name for m in entry.models}
            for model_name, rpm, rpd in models:
                if model_name in have:
                    continue
                await self.add(
                    AiModels(
                        model_name=model_name,
                        rpm=rpm,
                        rpd=rpd,
                        api_name=entry.api_name,
                        is_active=True,
                    )
                )
                created += 1
        return created


class AiModelsRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(AiModels, session)
        self.model: type[AiModels] = AiModels

    async def get_bucket(self, api_name: str, model_name: str) -> AiModels | None:
        query = select(self.model).where(
            self.model.api_name == api_name,
            self.model.model_name == model_name,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def set_limits(
        self,
        model_name: str,
        rpm: int | None = None,
        rpd: int | None = None,
    ) -> int:
        """Update limits for a model across every key. Returns rows touched."""
        query = select(self.model).where(self.model.model_name == model_name)
        result = await self.session.execute(query)
        rows = result.scalars().all()
        for row in rows:
            if rpm is not None:
                row.rpm = rpm
            if rpd is not None:
                row.rpd = rpd
            await self.update(row)
        return len(rows)

    async def set_active(self, model_name: str, active: bool) -> int:
        query = select(self.model).where(self.model.model_name == model_name)
        result = await self.session.execute(query)
        rows = result.scalars().all()
        for row in rows:
            row.is_active = active
            await self.update(row)
        return len(rows)
