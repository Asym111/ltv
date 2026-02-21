# app/core/roles.py
"""
Централизованные хелперы для проверки ролей.
Используется во всех API-роутах через Depends или вызов напрямую.

Роли:
  owner — полный доступ: настройки, аккаунты, аналитика, кампании, клиенты
  admin — транзакции, клиенты, аналитика, кампании (без настроек tenant/accounts)
  staff — только транзакции и просмотр клиентов
"""
from __future__ import annotations
from fastapi import HTTPException, Request


def _get_role(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    return str(user.get("role") or "staff").lower()


def _get_user(request: Request) -> dict:
    return getattr(request.state, "user", None) or {}


# ── Базовые проверки ──────────────────────────────────

def require_owner(request: Request) -> dict:
    """Только owner."""
    user = _get_user(request)
    if _get_role(request) != "owner":
        raise HTTPException(status_code=403, detail="Доступ запрещён. Требуется роль: owner")
    return user


def require_admin_or_owner(request: Request) -> dict:
    """owner или admin."""
    user = _get_user(request)
    if _get_role(request) not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Доступ запрещён. Требуется роль: admin или owner")
    return user


def require_any(request: Request) -> dict:
    """Любой авторизованный пользователь (owner/admin/staff)."""
    user = _get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return user


# ── Удобные bool-проверки (для шаблонов / условий) ──

def is_owner(request: Request) -> bool:
    return _get_role(request) == "owner"


def is_admin_or_owner(request: Request) -> bool:
    return _get_role(request) in ("owner", "admin")


def is_staff(request: Request) -> bool:
    return _get_role(request) == "staff"


# ── Матрица доступа к страницам ──────────────────────
#
# Страница          owner  admin  staff
# /admin/           ✅     ✅     ✅
# /admin/clients    ✅     ✅     ✅
# /admin/client/*   ✅     ✅     ✅  (просмотр)
# /admin/transactions ✅   ✅     ✅
# /admin/analytics  ✅     ✅     ❌
# /admin/campaigns  ✅     ✅     ❌
# /admin/settings   ✅     ❌     ❌
# /admin/accounts   ✅     ❌     ❌
# /admin/whatsapp   ✅     ✅     ❌
# /admin/news       ✅     ✅     ✅
# /admin/videos     ✅     ✅     ✅

ROLE_PAGES: dict[str, list[str]] = {
    # pages accessible only by owner
    "owner_only": [
        "/admin/settings",
        "/admin/accounts",
    ],
    # pages for admin + owner
    "admin_plus": [
        "/admin/analytics",
        "/admin/campaigns",
        "/admin/whatsapp",
    ],
    # pages for all roles
    "all": [
        "/admin/",
        "/admin/clients",
        "/admin/client/",
        "/admin/transactions",
        "/admin/news",
        "/admin/videos",
    ],
}