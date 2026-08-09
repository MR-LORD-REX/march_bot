from sqlalchemy import Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.DB.base import base


class AiModels(base):
    """One quota bucket: a single model on a single key.

    Adding a key inserts one row per model in LORE_MODELS, so N keys give
    N x len(LORE_MODELS) independent rpm/rpd budgets. model_name is unique
    per api_name rather than globally -- the same model on two keys is two
    separate buckets, which is the whole point of adding keys.
    """

    __tablename__ = "ai_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    rpm: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    rpd: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    api_name: Mapped[str] = mapped_column(
        String,
        ForeignKey("ai_api.api_name", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("api_name", "model_name", name="uq_ai_models_api_model"),
    )

    api: Mapped["AiApi"] = relationship("AiApi", back_populates="models")
