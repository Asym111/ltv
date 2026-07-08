# app/core/migrations.py
"""
Лёгкие стартовые миграции схемы.

Base.metadata.create_all создаёт только НОВЫЕ таблицы и не умеет добавлять
колонки в существующие. Alembic в проекте фактически не используется, поэтому
недостающие колонки добавляем здесь идемпотентно (SQLite и PostgreSQL).

Вызывается из main.py сразу после create_all.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _has_column(inspector, table: str, column: str) -> bool:
    try:
        return any(c["name"] == column for c in inspector.get_columns(table))
    except Exception:
        # Таблицы ещё нет — создаст create_all, колонка будет в модели
        return True


def run_startup_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    is_pg = engine.dialect.name == "postgresql"
    false_literal = "false" if is_pg else "0"

    with engine.begin() as conn:
        # --- users.wa_opt_out: отписка клиента от WhatsApp-рассылок ---
        if not _has_column(inspector, "users", "wa_opt_out"):
            conn.execute(text(
                f"ALTER TABLE users ADD COLUMN wa_opt_out BOOLEAN NOT NULL DEFAULT {false_literal}"
            ))
            logger.info("[migrate] users.wa_opt_out added")

        # --- bonus_grants.tenant_id: филиал начисления (для отчётов) ---
        if not _has_column(inspector, "bonus_grants", "tenant_id"):
            conn.execute(text("ALTER TABLE bonus_grants ADD COLUMN tenant_id INTEGER"))
            # Бэкфилл: приоритет — филиал транзакции, иначе тенант клиента
            conn.execute(text(
                "UPDATE bonus_grants SET tenant_id = ("
                "  SELECT t.tenant_id FROM transactions t WHERE t.id = bonus_grants.transaction_id"
                ") WHERE tenant_id IS NULL AND transaction_id IS NOT NULL"
            ))
            conn.execute(text(
                "UPDATE bonus_grants SET tenant_id = ("
                "  SELECT u.tenant_id FROM users u WHERE u.id = bonus_grants.user_id"
                ") WHERE tenant_id IS NULL"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bonus_grants_tenant_id ON bonus_grants (tenant_id)"
            ))
            logger.info("[migrate] bonus_grants.tenant_id added + backfilled")
