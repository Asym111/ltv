from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base


class RefundRecord(Base):
    __tablename__ = "transaction_refunds"
    __table_args__ = (
        UniqueConstraint("transaction_id", "request_id", name="uq_refunds_request"),
        UniqueConstraint("tenant_id", "external_id", name="uq_refunds_external"),
    )

    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(36), nullable=True)
    request_fingerprint = Column(String(64), nullable=False)
    external_id = Column(String(128), nullable=True)
    integration_key_id = Column(Integer, ForeignKey("integration_keys.id", ondelete="SET NULL"), nullable=True)
    amount = Column(Integer, nullable=False)
    earned_reversed = Column(Integer, nullable=False)
    redeemed_restored = Column(Integer, nullable=False)
    comment = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
