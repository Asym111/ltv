from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base


class WaSessionState(Base):
    """
    Последнее известное состояние WhatsApp-сессии тенанта.

    Одна строка на тенанта. Заполняется фоновой проверкой (scheduler),
    чтобы дашборд суперадмина читал состояние из базы, а не ходил
    по HTTP в WA-сервис за каждым филиалом на каждый рендер страницы.
    """

    __tablename__ = "wa_session_state"

    tenant_id = Column(Integer, primary_key=True, index=True)

    connected = Column(Boolean, nullable=False, default=False)
    last_checked_at = Column(DateTime, nullable=True)
    last_connected_at = Column(DateTime, nullable=True)   # когда видели живым в последний раз
    last_change_at = Column(DateTime, nullable=True)      # когда состояние менялось
    last_error = Column(String, nullable=True)

    # Пока False — тенант ещё ни разу не подключал WhatsApp.
    # Про такого нельзя сказать «отключился», поэтому тревогу не поднимаем.
    ever_connected = Column(Boolean, nullable=False, default=False)


class WaHealthEvent(Base):
    """
    Событие смены состояния — это и есть лента уведомлений суперадмина.

    Пишется ТОЛЬКО на переходе, а не на каждой проверке, иначе лента
    превратится в поток одинаковых строк каждые несколько минут.
    """

    __tablename__ = "wa_health_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    tenant_name = Column(String, nullable=True)     # снимок имени на момент события

    # disconnected | connected
    event = Column(String, nullable=False, default="disconnected")
    detail = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Суперадмин отметил уведомление прочитанным
    acknowledged_at = Column(DateTime, nullable=True)

    # Для события disconnected — когда связь вернулась (закрывает тревогу сама собой)
    resolved_at = Column(DateTime, nullable=True)
