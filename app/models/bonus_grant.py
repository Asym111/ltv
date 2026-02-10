from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class BonusGrant(Base):
    """
    Начисление бонусов отдельными партиями (грантами), чтобы:
    - корректно активировать через N дней
    - корректно сжигать через burn_days
    - списывать FIFO (сначала те, что раньше сгорят)
    """
    __tablename__ = "bonus_grants"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    amount = Column(Integer, nullable=False, default=0)      # начислено всего
    remaining = Column(Integer, nullable=False, default=0)   # осталось к списанию

    status = Column(String, nullable=False, default="pending")  # pending | available | expired

    available_from = Column(DateTime, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)

    source = Column(String, nullable=False, default="purchase")  # purchase | birthday | manual
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="bonus_grants")
