# app/models/broadcast.py
"""
Модели центра WhatsApp-рассылок.

Broadcast   — рассылка (аудитория, текст, настройки безопасности, статус, счётчики)
WaMessage   — журнал сообщений: и получатели рассылки, и одиночные/авто-отправки
WaTemplate  — сохранённые шаблоны сообщений (общие на сеть)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id = Column(Integer, primary_key=True, index=True)

    # Филиал-отправитель (его WhatsApp-номер) и корень сети (чья база клиентов)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    network_id = Column(Integer, nullable=False, index=True)

    name = Column(String(200), nullable=False, default="Рассылка")
    message_template = Column(Text, nullable=False)

    # all | bonus_gt_zero | inactive_days | tier | segment | campaign | manual
    audience_kind = Column(String(32), nullable=False, default="all")
    audience_json = Column(JSON, nullable=True)

    # Пропускать тех, кто получал рассылку за последние N дней (0 = не пропускать)
    exclude_recent_days = Column(Integer, nullable=False, default=7)

    # draft | running | paused | done | cancelled | failed
    status = Column(String(20), nullable=False, default="draft", index=True)

    total = Column(Integer, nullable=False, default=0)
    sent = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    skipped = Column(Integer, nullable=False, default=0)

    # Настройки безопасной отправки
    delay_min_sec = Column(Integer, nullable=False, default=7)
    delay_max_sec = Column(Integer, nullable=False, default=14)
    batch_size = Column(Integer, nullable=False, default=25)
    batch_pause_sec = Column(Integer, nullable=False, default=90)
    daily_cap = Column(Integer, nullable=False, default=250)

    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    created_by = Column(Integer, nullable=True)  # AuthUser.id
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    messages = relationship("WaMessage", back_populates="broadcast")


class WaMessage(Base):
    __tablename__ = "wa_messages"

    id = Column(Integer, primary_key=True, index=True)

    # NULL для одиночных и автоматических сообщений
    broadcast_id = Column(Integer, ForeignKey("broadcasts.id"), nullable=True, index=True)

    # Тенант-отправитель (чей WhatsApp-номер использован) — для дневного лимита
    tenant_id = Column(Integer, nullable=False, index=True)

    user_id = Column(Integer, nullable=True)  # клиент (users.id), если известен
    phone = Column(String(32), nullable=False)
    display_name = Column(String(120), nullable=True)

    # broadcast | single | auto
    kind = Column(String(16), nullable=False, default="broadcast")

    text = Column(Text, nullable=True)  # финальный отправленный текст

    # pending | sent | failed | skipped
    status = Column(String(16), nullable=False, default="pending", index=True)
    error = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True, index=True)

    broadcast = relationship("Broadcast", back_populates="messages")

    __table_args__ = (
        Index("ix_wa_messages_broadcast_status", "broadcast_id", "status"),
        Index("ix_wa_messages_tenant_sent", "tenant_id", "sent_at"),
    )


class WaTemplate(Base):
    __tablename__ = "wa_templates"

    id = Column(Integer, primary_key=True, index=True)
    # Шаблоны общие на сеть — хранятся на корне (network_id)
    tenant_id = Column(Integer, nullable=False, index=True)
    title = Column(String(120), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
