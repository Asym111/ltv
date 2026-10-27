from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("tenant_id", "request_id", name="uq_transactions_request"),)

    id = Column(Integer, primary_key=True, index=True)

    # ✅ tenant-изоляция
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    amount = Column(Integer, nullable=False)
    paid_amount = Column(Integer, default=0, nullable=False)

    redeem_points = Column(Integer, default=0, nullable=False)
    earned_points = Column(Integer, default=0, nullable=False)
    earning_mode = Column(String(16), nullable=True)
    earn_percent = Column(Numeric(5, 2), nullable=True)
    earn_base_amount = Column(Integer, nullable=True)
    created_by_id = Column(Integer, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(36), nullable=True)
    request_fingerprint = Column(String(64), nullable=True)

    payment_method = Column(String, default="CASH", nullable=False)
    comment = Column(String, nullable=True)

    # ✅ Возвраты
    status = Column(String, nullable=False, default="completed")  # completed / partially_refunded / refunded
    refunded_amount = Column(Integer, nullable=False, default=0)
    refunded_at = Column(DateTime, nullable=True)
    refunded_earned_points = Column(Integer, default=0, nullable=False)
    refunded_redeem_points = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="transactions")

    # ✅ начисления бонусов, привязанные к этой транзакции
    bonus_grants = relationship("BonusGrant", back_populates="transaction")
