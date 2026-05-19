# app/services/whatsapp.py
"""
WhatsApp клиент через собственный микросервис ltv-wa-service.

ВАЖНО: tenant_id теперь обязательный параметр во всех функциях.
Это предотвращает отправку сообщений через WhatsApp-сессию другого тенанта
(например, чтобы клиенты Астаны не получали сообщения от номера Алматы).
"""
from __future__ import annotations

import httpx
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(settings.WA_SERVICE_URL and settings.WA_INTERNAL_TOKEN)


def _headers() -> dict:
    return {
        "x-internal-token": settings.WA_INTERNAL_TOKEN or "",
        "Content-Type": "application/json",
    }


def _validate_tenant(tenant_id) -> str:
    """Жёсткая валидация tenant_id чтобы избежать кросс-тенантной отправки."""
    if tenant_id is None or tenant_id == "" or tenant_id == "default":
        raise ValueError(
            "tenant_id is required and cannot be 'default'. "
            "Pass an actual tenant_id (e.g. '3' or '4') to avoid cross-tenant messaging."
        )
    return str(tenant_id)


def normalize_phone(phone: str) -> str:
    """Приводим к формату 77001234567 (без +, без скобок)."""
    p = "".join(c for c in str(phone or "") if c.isdigit())
    if p.startswith("8") and len(p) == 11:
        p = "7" + p[1:]
    if len(p) == 10:
        p = "7" + p
    return p


# ── Status ────────────────────────────────────────────────────
def get_status(tenant_id) -> dict:
    """Проверяет состояние WhatsApp-сессии конкретного тенанта."""
    if not _is_configured():
        return {"ok": False, "error": "WA-сервис не настроен. Укажи WA_SERVICE_URL и WA_INTERNAL_TOKEN в .env"}

    try:
        tid = _validate_tenant(tenant_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    url = f"{settings.WA_SERVICE_URL}/session/{tid}"

    try:
        r = httpx.get(url, headers=_headers(), timeout=10)
        data = r.json()
        return {"ok": data.get("connected", False), **data}
    except Exception as e:
        logger.error(f"WA status error (tenant={tid}): {e}")
        return {"ok": False, "error": str(e)}


# ── QR-код ────────────────────────────────────────────────────
def get_qr(tenant_id) -> dict:
    """Получает QR-код для подключения WhatsApp конкретного тенанта."""
    if not _is_configured():
        return {"ok": False, "error": "WA-сервис не настроен"}

    try:
        tid = _validate_tenant(tenant_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    url = f"{settings.WA_SERVICE_URL}/session/{tid}/qr"

    try:
        r = httpx.get(url, headers=_headers(), timeout=10)
        return {"ok": True, **r.json()}
    except Exception as e:
        logger.error(f"WA QR error (tenant={tid}): {e}")
        return {"ok": False, "error": str(e)}


# ── Logout ────────────────────────────────────────────────────
def logout(tenant_id) -> dict:
    """Отключает WhatsApp-сессию конкретного тенанта."""
    if not _is_configured():
        return {"ok": False, "error": "WA-сервис не настроен"}

    try:
        tid = _validate_tenant(tenant_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    url = f"{settings.WA_SERVICE_URL}/session/{tid}/logout"

    try:
        r = httpx.post(url, headers=_headers(), timeout=10)
        return {"ok": True, **r.json()}
    except Exception as e:
        logger.error(f"WA logout error (tenant={tid}): {e}")
        return {"ok": False, "error": str(e)}


# ── Send single message ───────────────────────────────────────
def send_message(phone: str, text: str, tenant_id) -> dict:
    """Отправляет текстовое сообщение одному клиенту через WhatsApp нужного тенанта."""
    if not _is_configured():
        return {"ok": False, "error": "WA-сервис не настроен"}

    try:
        tid = _validate_tenant(tenant_id)
    except ValueError as e:
        logger.error(f"WA send blocked (no tenant_id): {e}")
        return {"ok": False, "error": str(e)}

    url = f"{settings.WA_SERVICE_URL}/send"
    phone_clean = normalize_phone(phone)

    try:
        r = httpx.post(
            url,
            headers=_headers(),
            json={"tenantId": tid, "phone": phone_clean, "message": text},
            timeout=15,
        )
        data = r.json()
        if r.status_code == 200 and data.get("success"):
            return {"ok": True, "phone": phone_clean}
        return {"ok": False, "error": data.get("error") or str(data), "status": r.status_code}
    except Exception as e:
        logger.error(f"WA send error to {phone} (tenant={tid}): {e}")
        return {"ok": False, "error": str(e)}


# ── Render template ───────────────────────────────────────────
def render_template(template: str, variables: dict) -> str:
    """Подставляет переменные в шаблон сообщения."""
    try:
        return template.format(**variables)
    except KeyError as e:
        logger.warning(f"Template var missing: {e}")
        return template


# ── Send campaign ─────────────────────────────────────────────
def send_campaign_messages(
    recipients: list[dict],
    template: str,
    dry_run: bool = False,
    tenant_id=None,
) -> dict:
    """Массовая рассылка по списку получателей. tenant_id обязателен (кроме dry_run)."""
    sent    = []
    failed  = []
    skipped = []

    # Валидация tenant_id (кроме dry_run, где сообщения не уходят)
    if not dry_run:
        try:
            _validate_tenant(tenant_id)
        except ValueError as e:
            return {
                "total": len(recipients),
                "sent": 0,
                "failed": len(recipients),
                "skipped": 0,
                "details": {"sent": [], "failed": [{"error": str(e)}], "skipped": []},
                "dry_run": False,
                "error": str(e),
            }

    for rec in recipients:
        phone = rec.get("phone") or rec.get("user_phone") or ""
        if not phone:
            skipped.append({"phone": "?", "reason": "no phone"})
            continue

        name  = rec.get("name") or rec.get("full_name") or "Клиент"
        bonus = rec.get("bonus") or rec.get("suggested_bonus") or 0

        text = render_template(template, {
            "name":  name,
            "phone": phone,
            "bonus": bonus,
            **rec,
        })

        if dry_run:
            sent.append({"phone": phone, "text": text, "dry_run": True})
            continue

        result = send_message(phone, text, tenant_id=tenant_id)
        if result["ok"]:
            sent.append({"phone": phone})
        else:
            failed.append({"phone": phone, "error": result.get("error")})

    return {
        "total":    len(recipients),
        "sent":     len(sent),
        "failed":   len(failed),
        "skipped":  len(skipped),
        "details":  {"sent": sent, "failed": failed, "skipped": skipped},
        "dry_run":  dry_run,
    }
