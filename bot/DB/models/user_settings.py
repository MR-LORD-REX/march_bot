from sqlalchemy import Column, Integer, String , Boolean , BIGINT , ForeignKey , Text, Enum
from sqlalchemy.orm import relationship,mapped_column, Mapped

from bot.DB.base import base

class UserSettings(base):
    __tablename__ = "user_settings"
    
    user_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False , primary_key=True)
    profile_template: Mapped[int] = mapped_column(Integer, default=1)
    lang: Mapped[str] = mapped_column(String, default="en")
    character_template: Mapped[int] = mapped_column(Integer, default=1)
    dalies_reminder: Mapped[bool] = mapped_column(Boolean, default=False)
    weekly_reminder: Mapped[bool] = mapped_column(Boolean, default=False)
    perform_daily: Mapped[bool] = mapped_column(Boolean, default=False)
    
    user: Mapped["Users"] = relationship("Users", back_populates="settings")