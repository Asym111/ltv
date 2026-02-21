# app/services/whatsapp.py
"""
GreenAPI WhatsApp клиент.
Документация: https://green-api.com/docs/

Настройка:
  1. Зарегистрируйтесь на green-api.com
  2. Создайте инстанс, получите INSTANCE_ID и API_TOKEN
  3. Добавьте в .env:
       GREENAPI_INSTANCE_ID=1234567890
       GREENAPI_API_TOKEN=your_token_here
  4. Авторизуйте WhatsApp через QR-код в личном кабинете
"""
from __future__ import annotations

import httpx
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(settings.GREENAPI_INSTANCE_ID and settings.GREENAPI_API_TOKEN)


def _base(instance_id: str, token: str) -> str:
    return f"{settings.GREENAPI_BASE_URL}/waInstance{instance_id}/{{}}/{token}"


def normalize_phone(phone: str) -> str:
    """Приводим к формату 77001234567 (без +, без скобок)."""
    p = "".join(c for c in str(phone or "") if c.isdigit())
    if p.startswith("8") and len(p) == 11:
        p = "7" + p[1:]
    if len(p) == 10:
        p = "7" + p
    return p


def to_chat_id(phone: str) -> str:
    """GreenAPI ожидает формат: 77001234567@c.us"""
    return normalize_phone(phone) + "@c.us"


# ── Status ────────────────────────────────────────────────────
def get_status() -> dict:
    """Проверяет состояние инстанса GreenAPI."""
    if not _is_configured():
        return {"ok": False, "error": "GreenAPI не настроен. Укажи GREENAPI_INSTANCE_ID и GREENAPI_API_TOKEN в .env"}

    iid   = settings.GREENAPI_INSTANCE_ID
    token = settings.GREENAPI_API_TOKEN
    url   = f"{settings.GREENAPI_BASE_URL}/waInstance{iid}/getStateInstance/{token}"

    try:
        r = httpx.get(url, timeout=10)
        data = r.json()
        state = data.get("stateInstance", "unknown")
        return {
            "ok":        state == "authorized",
            "state":     state,
            "raw":       data,
            "instance":  iid,
        }
    except Exception as e:
        logger.error(f"GreenAPI status error: {e}")
        return {"ok": False, "error": str(e)}


# ── Send single message ───────────────────────────────────────
def send_message(phone: str, text: str) -> dict:
    """Отправляет текстовое сообщение одному клиенту."""
    if not _is_configured():
        return {"ok": False, "error": "GreenAPI не настроен"}

    iid   = settings.GREENAPI_INSTANCE_ID
    token = settings.GREENAPI_API_TOKEN
    url   = f"{settings.GREENAPI_BASE_URL}/waInstance{iid}/sendMessage/{token}"

    chat_id = to_chat_id(phone)

    try:
        r = httpx.post(url, json={"chatId": chat_id, "message": text}, timeout=15)
        data = r.json()
        if r.status_code == 200 and data.get("idMessage"):
            return {"ok": True, "message_id": data["idMessage"], "chat_id": chat_id}
        return {"ok": False, "error": data.get("message") or str(data), "status": r.status_code}
    except Exception as e:
        logger.error(f"GreenAPI send error to {phone}: {e}")
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
    recipients: list[dict],   # [{"phone": "...", "name": "...", "bonus": 0, ...}]
    template: str,
    dry_run: bool = False,
) -> dict:
    """
    Массовая рассылка по списку получателей.
    Возвращает статистику: sent, failed, skipped.
    """
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

        result = send_message(phone, text)
        if result["ok"]:
            sent.append({"phone": phone, "message_id": result.get("message_id")})
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