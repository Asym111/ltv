from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class BonusGrant(Base):
    __tablename__ = "bonus_grants"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # ✅ Связь начисления с транзакцией (для корректных возвратов)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True, index=True)

    amount = Column(Integer, nullable=False, default=0)
    remaining = Column(Integer, nullable=False, default=0)

    # pending / available / expired
    status = Column(String, nullable=False, default="pending")

    available_from = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    # purchase / birthday / refund_redeem / etc
    source = Column(String, nullable=False, default="purchase")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="bonus_grants")
    transaction = relationship("Transaction", back_populates="bonus_grants")
