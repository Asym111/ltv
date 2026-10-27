from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String

from app.core.database import Base


class IntegrationKey(Base):
    __tablename__ = "integration_keys"

    id = Column(Integer, primary_key=True)
    public_id = Column(String(16), nullable=False, unique=True, index=True)
    token_hash = Column(String(64), nullable=False)
    name = Column(String(80), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    network_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    created_by_id = Column(Integer, ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True)
    scopes = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    usage_window = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)

