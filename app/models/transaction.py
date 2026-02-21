from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    # ✅ tenant-изоляция
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    amount = Column(Integer, nullable=False)
    paid_amount = Column(Integer, default=0, nullable=False)

    redeem_points = Column(Integer, default=0, nullable=False)
    earned_points = Column(Integer, default=0, nullable=False)

    payment_method = Column(String, default="CASH", nullable=False)
    comment = Column(String, nullable=True)

    # ✅ Возвраты
    status = Column(String, nullable=False, default="completed")  # completed / partially_refunded / refunded
    refunded_amount = Column(Integer, nullable=False, default=0)
    refunded_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="transactions")

    # ✅ начисления бонусов, привязанные к этой транзакции
    bonus_grants = relationship("BonusGrant", back_populates="transaction")
