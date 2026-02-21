from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # ✅ Дата окончания доступа (подписка). None = бессрочно.
    access_until = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    users = relationship("AuthUser", back_populates="tenant")


class AuthUser(Base):
    __tablename__ = "auth_users"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    tenant = relationship("Tenant", back_populates="users")

    phone = Column(String(32), unique=True, index=True, nullable=False)
    name = Column(String(120), default="Owner", nullable=False)

    # owner/admin/staff/superadmin
    role = Column(String(32), default="owner", nullable=False)

    password_salt = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
