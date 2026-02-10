# app/models/bonus.py
from __future__ import annotations

# ✅ ВАЖНО: никаких второй раз объявлений __tablename__="bonus_grants"
# Используем единственную модель из bonus_grant.py
from app.models.bonus_grant import BonusGrant

__all__ = ["BonusGrant"]
