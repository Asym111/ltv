from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base


class Invite(Base):
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    role = Column(String(32), nullable=False, default="cashier")
    phone = Column(String(20), nullable=True)
    created_by = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, default=datetime.utcnow)