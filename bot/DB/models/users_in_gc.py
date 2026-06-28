from sqlalchemy import  Boolean , BIGINT , ForeignKey 
from sqlalchemy.orm import relationship,mapped_column, Mapped

from bot.DB.base import base

class UsersInGroup(base):
    __tablename__="users_in_group"
    
    user_id:Mapped[int]=mapped_column(BIGINT,ForeignKey("users.telegram_id",ondelete="CASCADE"),primary_key=True,nullable=False)
    group_id:Mapped[int]=mapped_column(BIGINT,ForeignKey("telegram_groups.group_id",ondelete="CASCADE"),primary_key=True,nullable=False)
    
    user: Mapped["Users"] = relationship("Users", back_populates="groups")
    group: Mapped["TeleGroup"] = relationship("TeleGroup", back_populates="users")
    