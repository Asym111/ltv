# app/services/wa_official.py
"""
Клиент официального WhatsApp Business Platform (Cloud API).

Поддерживаются два провайдера с одинаковым форматом сообщений:
  - 360dialog  — https://waba-v2.360dialog.io, заголовок D360-API-KEY
  - meta       — https://graph.facebook.com/<ver>/<phone_number_id>, Bearer-токен

Массовая рассылка в официальном WhatsApp возможна ТОЛЬКО шаблонами (template),
заранее одобренными Meta. Свободный текст можно слать лишь в течение 24 часов
после сообщения клиента — для рассылок это не подходит.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.security import encrypt_field, decrypt_field
from app.models.wa_official import WaOfficialChannel

logger = logging.getLogger(__name__)

D360_BASE = os.getenv("D360_BASE_URL", "https://waba-v2.360dialog.io").rstrip("/")
META_BASE = os.getenv("META_GRAPH_BASE_URL", "https://graph.facebook.com/v21.0").rstrip("/")

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

# Коды ошибок Cloud API
_RETRYABLE_CODES = {4, 80007, 130429, 131000, 131016, 131048, 131056, 133004}
_FATAL_CODES = {0, 10, 190, 200, 368, 131031, 131042, 132000, 132001, 132005,
                132007, 132012, 132015, 132016, 133010}


# ─────────────────────────────────────────────────────────────
# Канал
# ─────────────────────────────────────────────────────────────
def get_channel(db: Session, tenant_id: int, network_id: int | None = None) -> WaOfficialChannel | None:
    """Канал филиала, а если своего нет — канал корня сети."""
    ch = db.query(WaOfficialChannel).filter(WaOfficialChannel.tenant_id == int(tenant_id)).first()
    if ch is None and network_id and int(network_id) != int(tenant_id):
        ch = db.query(WaOfficialChannel).filter(WaOfficialChannel.tenant_id == int(network_id)).first()
    return ch


def upsert_channel(
    db: Session,
    tenant_id: int,
    provider: str,
    api_key: str | None,
    phone_number_id: str | None = None,
    waba_id: str | None = None,
    display_phone: str | None = None,
    display_name: str | None = None,
    enabled: bool = True,
) -> WaOfficialChannel:
    ch = db.query(WaOfficialChannel).filter(WaOfficialChannel.tenant_id == int(tenant_id)).first()
    if ch is None:
        ch = WaOfficialChannel(tenant_id=int(tenant_id), webhook_secret=secrets.token_urlsafe(24))
        db.add(ch)
    ch.provider = provider if provider in ("360dialog", "meta") else "360dialog"
    if api_key:  # пустое поле в форме = не менять ключ
        ch.api_key_enc = encrypt_field(api_key.strip())
    ch.phone_number_id = (phone_number_id or "").strip() or None
    ch.waba_id = (waba_id or "").strip() or None
    ch.display_phone = (display_phone or "").strip() or None
    ch.display_name = (display_name or "").strip() or None
    ch.enabled = bool(enabled)
    db.commit()
    db.refresh(ch)
    return ch


def channel_public(ch: WaOfficialChannel | None) -> dict:
    if ch is None:
        return {"configured": False}
    return {
        "configured": bool(ch.api_key_enc),
        "enabled": bool(ch.enabled),
        "provider": ch.provider,
        "tenant_id": ch.tenant_id,
        "display_phone": ch.display_phone,
        "display_name": ch.display_name,
        "last_error": ch.last_error,
    }


def _api_key(ch: WaOfficialChannel) -> str:
    return (decrypt_field(ch.api_key_enc) or "").strip() if ch.api_key_enc else ""


def _headers(ch: WaOfficialChannel) -> dict:
    key = _api_key(ch)
    if ch.provider == "meta":
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return {"D360-API-KEY": key, "Content-Type": "application/json"}


def _messages_url(ch: WaOfficialChannel) -> str:
    if ch.provider == "meta":
        return f"{META_BASE}/{ch.phone_number_id}/messages"
    return f"{D360_BASE}/messages"


def _ready(ch: WaOfficialChannel | None) -> str | None:
    if ch is None or not ch.api_key_enc:
        return "Официальный WhatsApp не подключён. Обратитесь к администратору платформы."
    if not ch.enabled:
        return "Официальный WhatsApp отключён администратором платформы."
    if ch.provider == "meta" and not (ch.phone_number_id and ch.waba_id):
        return "Для Meta Cloud API нужны phone_number_id и waba_id."
    return None


# ─────────────────────────────────────────────────────────────
# Шаблоны
# ─────────────────────────────────────────────────────────────
def _normalize_template(t: dict) -> dict:
    body = ""
    header_type = None
    for c in t.get("components") or []:
        ctype = str(c.get("type") or "").upper()
        if ctype == "BODY":
            body = str(c.get("text") or "")
        elif ctype == "HEADER":
            header_type = str(c.get("format") or "TEXT").upper()
    params = []
    for m in _PLACEHOLDER_RE.finditer(body):
        if m.group(1) not in params:
            params.append(m.group(1))
    return {
        "name": t.get("name"),
        "language": t.get("language"),
        "status": str(t.get("status") or "").upper(),
        "category": str(t.get("category") or "").upper(),
        "body": body,
        "params": params,                         # ["1","2"] или ["first_name"]
        "named": any(not p.isdigit() for p in params),
        "header_type": header_type,
    }


def list_templates(ch: WaOfficialChannel | None, approved_only: bool = True) -> dict:
    err = _ready(ch)
    if err:
        return {"ok": False, "error": err, "templates": []}
    urls = (
        [f"{META_BASE}/{ch.waba_id}/message_templates?limit=200"]
        if ch.provider == "meta"
        else [f"{D360_BASE}/message_templates?limit=200", f"{D360_BASE}/v1/configs/templates"]
    )
    last_err = ""
    for url in urls:
        try:
            r = httpx.get(url, headers=_headers(ch), timeout=20)
            if r.status_code >= 400:
                last_err = f"HTTP {r.status_code}: {r.text[:300]}"
                continue
            data = r.json()
            raw = data.get("data") or data.get("waba_templates") or []
            items = [_normalize_template(t) for t in raw if isinstance(t, dict)]
            if approved_only:
                items = [t for t in items if t["status"] == "APPROVED"]
            # Картинки/видео в шапке шаблона пока не поддерживаем
            items = [t for t in items if t["header_type"] in (None, "TEXT")]
            return {"ok": True, "templates": items}
        except Exception as e:
            last_err = str(e)
    return {"ok": False, "error": last_err or "Не удалось получить шаблоны", "templates": []}


# ─────────────────────────────────────────────────────────────
# Отправка
# ─────────────────────────────────────────────────────────────
def build_template_payload(phone: str, name: str, lang: str, params: list[str], param_names: list[str] | None = None) -> dict:
    tpl: dict[str, Any] = {"name": name, "language": {"code": lang or "ru"}}
    if params:
        body_params = []
        for i, val in enumerate(params):
            p: dict[str, Any] = {"type": "text", "text": str(val)[:1024] or "-"}
            if param_names and i < len(param_names) and not str(param_names[i]).isdigit():
                p["parameter_name"] = param_names[i]
            body_params.append(p)
        tpl["components"] = [{"type": "body", "parameters": body_params}]
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "".join(ch for ch in str(phone) if ch.isdigit()),
        "type": "template",
        "template": tpl,
    }


def send_template(
    ch: WaOfficialChannel | None,
    phone: str,
    template_name: str,
    lang: str,
    params: list[str],
    param_names: list[str] | None = None,
) -> dict:
    """
    Возвращает {ok, message_id} или {ok: False, error, code, retryable, fatal}.
      retryable — временно (лимит скорости, сбой): сообщение вернуть в очередь;
      fatal     — проблема канала/шаблона/ключа: рассылку ставим на паузу.
    """
    err = _ready(ch)
    if err:
        return {"ok": False, "error": err, "fatal": True}

    body = build_template_payload(phone, template_name, lang, params, param_names)
    try:
        r = httpx.post(_messages_url(ch), headers=_headers(ch), json=body, timeout=30)
    except Exception as e:
        return {"ok": False, "error": f"network: {e}", "retryable": True}

    try:
        data = r.json()
    except Exception:
        data = {}

    if r.status_code < 300 and (data.get("messages") or []):
        return {"ok": True, "message_id": data["messages"][0].get("id")}

    e = (data.get("error") or {}) if isinstance(data, dict) else {}
    code = e.get("code")
    details = (e.get("error_data") or {}).get("details") or e.get("message") or r.text[:300]
    msg = f"[{code}] {details}" if code is not None else f"HTTP {r.status_code}: {details}"
    retryable = r.status_code in (429, 500, 502, 503, 504) or code in _RETRYABLE_CODES
    fatal = r.status_code in (401, 403) or code in _FATAL_CODES
    return {"ok": False, "error": msg[:490], "code": code, "retryable": retryable, "fatal": fatal and not retryable}


def set_webhook(ch: WaOfficialChannel, url: str) -> dict:
    """360dialog: регистрирует URL вебхука статусов. Для Meta вебхук задаётся в настройках приложения."""
    if ch.provider != "360dialog":
        return {"ok": False, "error": "Для Meta укажите вебхук в настройках приложения Meta"}
    try:
        r = httpx.post(f"{D360_BASE}/v1/configs/webhook", headers=_headers(ch), json={"url": url}, timeout=20)
        if r.status_code < 300:
            return {"ok": True}
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def webhook_url_for(ch: WaOfficialChannel) -> str | None:
    base = (os.getenv("PUBLIC_BASE_URL", "") or "").rstrip("/")
    if not base:
        return None
    return f"{base}/wa-webhook/{ch.webhook_secret}"


def parse_statuses(payload: dict) -> list[dict]:
    """Достаёт статусы доставки из вебхука Cloud API: [{id, status, error}]."""
    out: list[dict] = []
    for entry in (payload or {}).get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for st in value.get("statuses") or []:
                errs = st.get("errors") or []
                err = None
                if errs:
                    e0 = errs[0]
                    err = f"[{e0.get('code')}] {e0.get('title') or ''} {(e0.get('error_data') or {}).get('details') or ''}".strip()
                out.append({"id": st.get("id"), "status": st.get("status"), "error": err})
    return out


def render_params(param_templates: list[str], variables: dict) -> list[str]:
    """Каждый параметр шаблона — строка с переменными {имя} {бонусы} {уровень}."""
    from app.services.broadcast_worker import render_message
    return [render_message(str(p or ""), variables).strip() or "-" for p in (param_templates or [])]
