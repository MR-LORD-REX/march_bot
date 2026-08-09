from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.DB.base import base


class AiApi(base):
    """One Gemini API key. The key itself is Fernet-encrypted at rest --
    it is a live credential and the users table is dumped by /users."""

    __tablename__ = "ai_api"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    api_key: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    models: Mapped[list["AiModels"]] = relationship(
        "AiModels",
        back_populates="api",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
