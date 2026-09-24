# app/models/wa_official.py
"""
Официальный WhatsApp (WhatsApp Business Platform через 360dialog / Meta Cloud API)
и внутренний баланс кредитов для рассылок.

WaOfficialChannel — подключение официального номера. Настраивается суперадмином
                    (мы — партнёр 360dialog и сами оплачиваем сообщения).
                    Привязка к тенанту-отправителю; если у филиала своего канала
                    нет — используется канал корня сети.
WaCreditAccount   — баланс кредитов компании (сети). 1 кредит = 1 сообщение.
WaCreditLedger    — журнал движений: пополнение, списание, возврат, корректировка.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Index

from app.core.database import Base


class WaOfficialChannel(Base):
    __tablename__ = "wa_official_channels"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, unique=True, index=True)

    # 360dialog | meta
    provider = Column(String(16), nullable=False, default="360dialog")
    # 360dialog: D360-API-KEY канала; meta: постоянный токен System User. Шифруется.
    api_key_enc = Column(Text, nullable=True)
    # Только для meta: phone_number_id и waba_id из WhatsApp Manager
    phone_number_id = Column(String(64), nullable=True)
    waba_id = Column(String(64), nullable=True)

    display_phone = Column(String(32), nullable=True)   # для отображения: +7 700 ...
    display_name = Column(String(120), nullable=True)

    # Секрет в URL вебхука статусов доставки
    webhook_secret = Column(String(64), nullable=False)

    enabled = Column(Boolean, nullable=False, default=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class WaCreditAccount(Base):
    __tablename__ = "wa_credit_accounts"

    id = Column(Integer, primary_key=True, index=True)
    # Корень сети: кредиты общие на компанию, тратят все филиалы
    network_id = Column(Integer, nullable=False, unique=True, index=True)
    balance = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class WaCreditLedger(Base):
    __tablename__ = "wa_credit_ledger"

    id = Column(Integer, primary_key=True, index=True)
    network_id = Column(Integer, nullable=False, index=True)

    # >0 пополнение/возврат, <0 списание
    delta = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)

    # topup | charge | refund | adjust
    kind = Column(String(16), nullable=False)

    broadcast_id = Column(Integer, nullable=True)
    wa_message_id = Column(Integer, nullable=True)

    # Для пополнений: сумма оплаты в тенге (справочно) и комментарий
    amount_kzt = Column(Integer, nullable=True)
    comment = Column(String(255), nullable=True)
    created_by = Column(String(64), nullable=True)   # "superadmin" / id пользователя

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_wa_credit_ledger_network_created", "network_id", "created_at"),
    )
