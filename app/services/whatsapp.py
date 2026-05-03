# app/services/whatsapp.py
"""
WhatsApp клиент через собственный микросервис ltv-wa-service.
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


def normalize_phone(phone: str) -> str:
    """Приводим к формату 77001234567 (без +, без скобок)."""
    p = "".join(c for c in str(phone or "") if c.isdigit())
    if p.startswith("8") and len(p) == 11:
        p = "7" + p[1:]
    if len(p) == 10:
        p = "7" + p
    return p


# ── Status ────────────────────────────────────────────────────
def get_status(tenant_id: str = "default") -> dict:
    """Проверяет состояние WhatsApp-сессии через микросервис."""
    if not _is_configured():
        return {"ok": False, "error": "WA-сервис не настроен. Укажи WA_SERVICE_URL и WA_INTERNAL_TOKEN в .env"}

    url = f"{settings.WA_SERVICE_URL}/session/{tenant_id}"

    try:
        r = httpx.get(url, headers=_headers(), timeout=10)
        data = r.json()
        return {"ok": data.get("connected", False), **data}
    except Exception as e:
        logger.error(f"WA status error: {e}")
        return {"ok": False, "error": str(e)}


# ── QR-код ────────────────────────────────────────────────────
def get_qr(tenant_id: str = "default") -> dict:
    """Получает QR-код для подключения WhatsApp."""
    if not _is_configured():
        return {"ok": False, "error": "WA-сервис не настроен"}

    url = f"{settings.WA_SERVICE_URL}/session/{tenant_id}/qr"

    try:
        r = httpx.get(url, headers=_headers(), timeout=10)
        return {"ok": True, **r.json()}
    except Exception as e:
        logger.error(f"WA QR error: {e}")
        return {"ok": False, "error": str(e)}


# ── Logout ────────────────────────────────────────────────────
def logout(tenant_id: str = "default") -> dict:
    """Отключает WhatsApp-сессию."""
    if not _is_configured():
        return {"ok": False, "error": "WA-сервис не настроен"}

    url = f"{settings.WA_SERVICE_URL}/session/{tenant_id}/logout"

    try:
        r = httpx.post(url, headers=_headers(), timeout=10)
        return {"ok": True, **r.json()}
    except Exception as e:
        logger.error(f"WA logout error: {e}")
        return {"ok": False, "error": str(e)}


# ── Send single message ───────────────────────────────────────
def send_message(phone: str, text: str, tenant_id: str = "default") -> dict:
    """Отправляет текстовое сообщение одному клиенту."""
    if not _is_configured():
        return {"ok": False, "error": "WA-сервис не настроен"}

    url = f"{settings.WA_SERVICE_URL}/send"
    phone_clean = normalize_phone(phone)

    try:
        r = httpx.post(
            url,
            headers=_headers(),
            json={"tenantId": tenant_id, "phone": phone_clean, "message": text},
            timeout=15,
        )
        data = r.json()
        if r.status_code == 200 and data.get("success"):
            return {"ok": True, "phone": phone_clean}
        return {"ok": False, "error": data.get("error") or str(data), "status": r.status_code}
    except Exception as e:
        logger.error(f"WA send error to {phone}: {e}")
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
    tenant_id: str = "default",
) -> dict:
    """Массовая рассылка по списку получателей."""
    sent    = []
    failed  = []
    skipped = []

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
