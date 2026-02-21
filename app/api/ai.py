# app/api/ai.py
from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.config import settings

from app.schemas.ai import AiAskIn, AiAskOut, AiRecoOut
from app.ai.prompts import SYSTEM_PROMPT_RU, build_user_prompt
from app.ai.openai_client import openai_generate_json, OpenAIError

from app.models.user import User
from app.models.transaction import Transaction
from app.models.bonus_grant import BonusGrant
from app.ai.insights import build_overview_payload
from app.services.loyalty_engine import get_balances

from app.services.campaigns import (
    create_campaign as svc_create_campaign,
    build_recipients as svc_build_recipients,
)

router = APIRouter(prefix="/ai", tags=["ai"])


# =========================
# Provider helpers
# =========================
def _mock_allowed() -> bool:
    v = getattr(settings, "AI_MOCK_IF_NO_KEY", None)
    if v is None:
        return True
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _provider_order() -> list[str]:
    p = str(getattr(settings, "AI_PROVIDER", "auto") or "auto").strip().lower()
    if p == "off":
        return []
    return ["openai"]


# =========================
# Phone normalize
# =========================
def _norm_phone(raw: str) -> str:
    s = "".join(ch for ch in (raw or "") if ch.isdigit())
    if s.startswith("8") and len(s) == 11:
        s = "7" + s[1:]
    if len(s) == 10:
        s = "7" + s
    if len(s) > 11:
        s = s[-11:]
    return s


# =========================
# Target sanitize
# =========================
AI_TARGET_POLICY_RU = (
    "ВАЖНО: В блоке recommendations всегда заполняй поле target строго в формате "
    "'nav:/admin/...' (только внутренние страницы админки). "
    "Для начисления бонусов: 'action:grant_bonus|phone=77001234567|amount=5000|reason=...'.\n"
    "Примеры target:\n"
    "- nav:/admin/analytics\n"
    "- nav:/admin/campaigns?create=1&name=Winback&segment_key=risk&bonus=5000&build=1\n"
    "- nav:/admin/client/77001234567\n"
    "- action:grant_bonus|phone=77001234567|amount=5000|reason=Подарок от AI\n"
    "Никаких http(s) ссылок, никаких SQL/команд."
)


def _sanitize_target(target: str) -> str:
    t = (target or "").strip()
    if t.startswith("action:grant_bonus"):
        return t  # проверяем при execute
    if not t.startswith("nav:"):
        return "—"
    url = t[4:].strip()
    if not url.startswith("/admin/"):
        return "—"
    return f"nav:{url}"


def _build_user_prompt_safe(context: str, payload: dict[str, Any], question: str) -> str:
    try:
        base = build_user_prompt(context, payload, question)
    except TypeError:
        base = build_user_prompt(payload)  # type: ignore[call-arg]
    return f"{base}\n\n{AI_TARGET_POLICY_RU}".strip()


# =========================
# LLM call
# =========================
def _validate_llm_shape(obj: dict[str, Any]) -> tuple[str, list[str], list[AiRecoOut]]:
    answer = obj.get("answer")
    insights = obj.get("insights")
    recos = obj.get("recommendations")

    if not isinstance(answer, str):
        raise OpenAIError("JSON missing 'answer'")
    if not isinstance(insights, list):
        raise OpenAIError("JSON missing 'insights'")
    if not isinstance(recos, list):
        raise OpenAIError("JSON missing 'recommendations'")

    out_recos: list[AiRecoOut] = []
    for r in recos[:10]:
        if not isinstance(r, dict):
            continue
        raw_target = str(r.get("target") or "").strip()
        safe_target = _sanitize_target(raw_target)
        out_recos.append(
            AiRecoOut(
                action=str(r.get("action") or "").strip() or "—",
                target=safe_target,
                why=str(r.get("why") or "").strip() or "—",
                suggested_bonus=int(r.get("suggested_bonus") or 0),
                expected_effect=str(r.get("expected_effect") or "").strip() or "—",
                risk=str(r.get("risk") or "").strip() or "—",
            )
        )

    return answer.strip(), [str(x) for x in insights[:10]], out_recos


async def _try_llm(
    provider: str,
    context: str,
    payload: dict[str, Any],
    question: str,
) -> tuple[str, str, list[str], list[AiRecoOut]]:
    user_prompt = _build_user_prompt_safe(context, payload, question)

    if provider == "openai":
        api_key = str(getattr(settings, "OPENAI_API_KEY", "") or "").strip()
        model   = str(getattr(settings, "OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini").strip()
        obj = await openai_generate_json(
            SYSTEM_PROMPT_RU, user_prompt,
            api_key=api_key, model=model,
        )
        answer, insights, recos = _validate_llm_shape(obj)
        return "openai", answer, insights, recos

    raise OpenAIError(f"Unknown provider: {provider}")


# =========================
# Client payload builder
# =========================
def _build_client_payload(db: Session, raw_phone: str) -> dict[str, Any]:
    phone = _norm_phone(raw_phone)
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        return {"error": "client_not_found", "phone": phone}

    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .limit(50)
        .all()
    )

    total_spent = sum(t.paid_amount for t in txs if t.paid_amount)
    purchases_count = len(txs)
    avg_check = round(total_spent / purchases_count, 2) if purchases_count else 0.0

    last_tx = txs[0] if txs else None
    last_purchase_at = last_tx.created_at.isoformat() if last_tx else None
    recency_days: int | None = None
    if last_tx:
        recency_days = (datetime.utcnow() - last_tx.created_at).days

    balances = get_balances(db, user.id)

    return {
        "phone": phone,
        "full_name": user.full_name,
        "tier": user.tier,
        "bonus": {
            "available": balances.get("available", 0),
            "pending": balances.get("pending", 0),
        },
        "total_spent": total_spent,
        "purchases_count": purchases_count,
        "avg_check": avg_check,
        "last_purchase_at": last_purchase_at,
        "recency_days": recency_days,
        "nav_whitelist": {
            "client_card": f"nav:/admin/client/{phone}",
            "transactions": f"nav:/admin/transactions?phone={phone}",
            "grant_bonus": f"action:grant_bonus|phone={phone}|amount=5000|reason=Подарок от AI",
        },
    }


# =========================
# Heuristic fallback
# =========================
def _heuristic_answer(context: str, payload: dict[str, Any], question: str) -> AiAskOut:
    insights: list[str] = []
    recos: list[AiRecoOut] = []

    if context in ("client", "operator"):
        phone = str(payload.get("phone") or "")
        purchases = int(payload.get("purchases_count") or 0)
        total = int(payload.get("total_spent") or 0)
        tier = payload.get("tier") or "Bronze"
        avail = int((payload.get("bonus") or {}).get("available") or 0)
        pending = int((payload.get("bonus") or {}).get("pending") or 0)
        recency_days = payload.get("recency_days")

        insights.append(f"Уровень клиента: {tier}. Покупок: {purchases}. Сумма: {total} ₸.")
        insights.append(f"Бонусы: доступно {avail}, в ожидании {pending}.")

        if purchases == 0:
            recos.append(AiRecoOut(
                action="Начислить приветственные бонусы",
                target=f"action:grant_bonus|phone={phone}|amount=1000|reason=Приветственные бонусы",
                why="Нет покупок — стимулируем первый визит бонусами",
                suggested_bonus=1000,
                expected_effect="Рост вероятности первой покупки",
                risk="Минимальный",
            ))
        elif isinstance(recency_days, int) and recency_days >= 30:
            recos.append(AiRecoOut(
                action="Начислить бонусы для возврата клиента",
                target=f"action:grant_bonus|phone={phone}|amount=3000|reason=Win-back бонус",
                why=f"Клиент не покупал {recency_days} дней — риск ухода",
                suggested_bonus=3000,
                expected_effect="Возврат клиента в течение 2 недель",
                risk="Клиент может использовать бонус и уйти снова",
            ))
            recos.append(AiRecoOut(
                action="Создать win-back кампанию",
                target="nav:/admin/campaigns?create=1&name=Winback+30d&segment_key=risk&bonus=3000&build=1",
                why="Быстро собрать кампанию по сегменту риска",
                suggested_bonus=3000,
                expected_effect="Ускорение запуска win-back",
                risk="Проверь тексты перед отправкой",
            ))
        else:
            recos.append(AiRecoOut(
                action="Начислить бонусы за активность",
                target=f"action:grant_bonus|phone={phone}|amount=2000|reason=Бонус лояльному клиенту",
                why="Активный клиент — стимулируем ещё одну покупку",
                suggested_bonus=2000,
                expected_effect="Повторная покупка в течение недели",
                risk="Минимальный",
            ))

        answer = (
            f"Клиент {phone} ({tier}): {purchases} покупок, {total} ₸ оборот. "
            f"Бонусов доступно: {avail}. "
            + (f"Последняя покупка {recency_days} дней назад." if recency_days else "")
        )
    else:
        # business context
        s = (payload.get("summary") or {})
        clients = int(s.get("clients") or 0)
        active = int(s.get("active_30d") or 0)
        risk = int(s.get("churn_risk") or 0)
        revenue = int(s.get("total_revenue_30d") or 0)

        insights.append(f"Клиентов: {clients}. Активных за 30 дней: {active}.")
        insights.append(f"В зоне риска оттока: {risk} клиентов.")
        insights.append(f"Выручка за 30 дней: {revenue:,} ₸.")

        if risk > 0:
            recos.append(AiRecoOut(
                action="Запустить win-back кампанию для ушедших",
                target="nav:/admin/campaigns?create=1&name=Winback+30d&segment_key=risk&bonus=5000&build=1",
                why=f"{risk} клиентов не покупали 30+ дней",
                suggested_bonus=5000,
                expected_effect="Возврат 15-30% сегмента риска",
                risk="Бюджет на бонусы",
            ))

        recos.append(AiRecoOut(
            action="Посмотреть аналитику и сегменты",
            target="nav:/admin/analytics",
            why="Полная картина удержания и активности",
            suggested_bonus=0,
            expected_effect="Выявление точек роста",
            risk="Нет",
        ))

        answer = (
            f"Обзор бизнеса: {clients} клиентов, {active} активных за 30 дней, "
            f"{risk} в зоне риска. Выручка за месяц: {revenue:,} ₸."
        )

    return AiAskOut(
        mode="heuristic",
        context=context,
        answer=answer,
        insights=insights,
        recommendations=recos,
        payload=payload,
        llm_error=None,
    )


# =========================
# Endpoints: overview + ask
# =========================
@router.get("/overview")
async def ai_overview(db: Session = Depends(get_db)) -> AiAskOut:
    payload = build_overview_payload(db)
    question = (
        "Дай краткий обзор бизнеса: что хорошо, что требует внимания, "
        "топ-3 приоритета для роста LTV."
    )

    last_err: str | None = None
    for prov in _provider_order():
        try:
            mode, answer, insights, recos = await _try_llm(prov, "business", payload, question)
            return AiAskOut(
                mode=mode, context="business",
                answer=answer, insights=insights,
                recommendations=recos, payload=payload, llm_error=None,
            )
        except Exception as e:
            last_err = str(e)

    if _mock_allowed():
        fb = _heuristic_answer("business", payload, question)
        fb.llm_error = last_err or "LLM disabled"
        return fb

    return AiAskOut(
        mode="error", context="business",
        answer="", insights=[], recommendations=[],
        payload=payload, llm_error=last_err or "LLM disabled",
    )


@router.get("/ask")
async def ai_ask_get(
    context: str = "business",
    question: Optional[str] = None,
    phone: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Any:
    if not question:
        return {"ok": True, "message": "Используй POST /api/ai/ask"}
    payload_in = AiAskIn(context=context, question=question, phone=phone)  # type: ignore
    return await ai_ask(payload_in, db)


@router.post("/ask", response_model=AiAskOut)
async def ai_ask(payload_in: AiAskIn, db: Session = Depends(get_db)) -> AiAskOut:
    context = payload_in.context

    if context == "business":
        payload = build_overview_payload(db)
    else:
        if not payload_in.phone:
            raise HTTPException(status_code=400, detail="phone required for client context")
        payload = _build_client_payload(db, payload_in.phone)

    last_err: str | None = None
    for prov in _provider_order():
        try:
            mode, answer, insights, recos = await _try_llm(prov, context, payload, payload_in.question)
            return AiAskOut(
                mode=mode, context=context,
                answer=answer, insights=insights,
                recommendations=recos, payload=payload, llm_error=None,
            )
        except Exception as e:
            last_err = str(e)

    if _mock_allowed():
        fb = _heuristic_answer(context, payload, payload_in.question)
        fb.llm_error = last_err or "LLM disabled"
        return fb

    return AiAskOut(
        mode="error", context=context,
        answer="", insights=[], recommendations=[],
        payload=payload, llm_error=last_err or "LLM disabled",
    )


# =========================
# Execute
# =========================
class AiExecuteIn(BaseModel):
    context: str = Field(default="business")
    phone: Optional[str] = None
    recommendation: dict[str, Any]


class AiExecuteOut(BaseModel):
    ok: bool = True
    performed: bool = False
    action: str = ""
    nav: Optional[str] = None
    message: str = ""


def _qs_str(qs: dict, key: str, default: str = "") -> str:
    return ((qs.get(key) or [default])[0] or "").strip()


def _qs_int(qs: dict, key: str, default: int = 0) -> int:
    try:
        return int((_qs_str(qs, key) or str(default)))
    except Exception:
        return default


def _truthy(s: str) -> bool:
    return str(s or "").strip().lower() in ("1", "true", "yes", "y", "on")


@router.post("/execute", response_model=AiExecuteOut)
async def ai_execute(
    payload_in: AiExecuteIn,
    request: Request,
    db: Session = Depends(get_db),
) -> AiExecuteOut:
    """
    Whitelist executor:
      1. action:grant_bonus|phone=...|amount=...|reason=...  → начислить бонусы клиенту
      2. nav:/admin/campaigns?create=1&...                   → создать кампанию (+ build)
      3. nav:/admin/...                                      → безопасный переход
    """
    r   = payload_in.recommendation or {}
    action_label = str(r.get("action") or "").strip()
    target = str(r.get("target") or "").strip()

    if not target:
        raise HTTPException(status_code=400, detail="recommendation.target is required")

    # ── 1. Grant bonus action ─────────────────────────────────
    if target.startswith("action:grant_bonus"):
        return await _handle_grant_bonus(target, action_label, payload_in, db, request)

    # ── 2. Nav target ─────────────────────────────────────────
    if not target.startswith("nav:"):
        raise HTTPException(status_code=400, detail="Only nav: or action: targets are allowed")

    nav_url = target[4:].strip()
    if not nav_url.startswith("/admin/"):
        raise HTTPException(status_code=400, detail="Only /admin/* paths are allowed")

    parsed = urlparse(nav_url)
    qs = parse_qs(parsed.query or "", keep_blank_values=True)

    # ── 3. Campaign create ────────────────────────────────────
    if parsed.path == "/admin/campaigns" and _truthy(_qs_str(qs, "create")):
        return await _handle_create_campaign(qs, action_label, nav_url, db)

    # ── 4. Plain nav ──────────────────────────────────────────
    return AiExecuteOut(
        ok=True, performed=False,
        action=action_label, nav=nav_url,
        message="Переход подтверждён сервером.",
    )


async def _handle_grant_bonus(
    target: str,
    action_label: str,
    payload_in: AiExecuteIn,
    db: Session,
    request: Request,
) -> AiExecuteOut:
    """Начислить бонусы клиенту напрямую через AI."""

    # Парсим строку: action:grant_bonus|phone=...|amount=...|reason=...
    params: dict[str, str] = {}
    parts = target.split("|")
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            params[k.strip()] = v.strip()

    raw_phone = params.get("phone") or (payload_in.phone or "")
    phone = _norm_phone(raw_phone)
    if not phone:
        raise HTTPException(status_code=400, detail="phone required for grant_bonus")

    try:
        amount = int(params.get("amount") or 0)
    except Exception:
        amount = 0

    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    if amount > 100_000:
        raise HTTPException(status_code=400, detail="amount exceeds max 100,000 per AI action")

    reason = params.get("reason") or "Бонус от AI-ассистента"
    if len(reason) > 255:
        reason = reason[:255]

    # Находим клиента (tenant-aware)
    tenant_id: int | None = None
    current_user = getattr(request.state, "user", None) or {}
    tenant_id = current_user.get("tenant_id")

    q = db.query(User).filter(User.phone == phone)
    if tenant_id:
        q = q.filter(User.tenant_id == int(tenant_id))
    user = q.first()

    if not user:
        raise HTTPException(status_code=404, detail=f"Клиент {phone} не найден")

    # Начисляем бонусы через BonusGrant
    now = datetime.utcnow()
    # source содержит причину (reason) — поле note в модели отсутствует
    source_str = f"ai_grant:{reason[:40]}" if reason else "ai_grant"
    grant = BonusGrant(
        user_id=user.id,
        transaction_id=None,
        amount=amount,
        remaining=amount,
        source=source_str,
        status="available",
        available_from=now,
        expires_at=now + timedelta(days=30),
        created_at=now,
    )
    db.add(grant)

    # Обновляем баланс пользователя
    user.bonus_balance = (user.bonus_balance or 0) + amount
    db.commit()

    return AiExecuteOut(
        ok=True,
        performed=True,
        action=action_label or "Начисление бонусов",
        nav=f"/admin/client/{phone}",
        message=f"✓ Начислено {amount:,} бонусов клиенту {phone}. Причина: {reason}",
    )


async def _handle_create_campaign(
    qs: dict,
    action_label: str,
    nav_url: str,
    db: Session,
) -> AiExecuteOut:
    """Создать кампанию из AI-рекомендации."""
    name = _qs_str(qs, "name")
    segment_key = _qs_str(qs, "segment_key")
    bonus = _qs_int(qs, "bonus", 0)

    if not name or not segment_key:
        raise HTTPException(status_code=400, detail="name and segment_key required")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="name too long")
    if bonus < 0 or bonus > 10_000_000:
        raise HTTPException(status_code=400, detail="bonus out of range")

    c = svc_create_campaign(db, {
        "name": name,
        "segment_key": segment_key,
        "suggested_bonus": bonus,
        "r_min": _qs_int(qs, "r_min") or None,
        "f_min": _qs_int(qs, "f_min") or None,
        "m_min": _qs_int(qs, "m_min") or None,
        "note": _qs_str(qs, "note") or None,
    })

    built = False
    build_error: str | None = None
    if _truthy(_qs_str(qs, "build")):
        try:
            svc_build_recipients(db, c.id)
            built = True
        except Exception as e:
            # Не роняем всё из-за ошибки построения получателей
            build_error = str(e)

    return AiExecuteOut(
        ok=True,
        performed=True,
        action=action_label or "Создание кампании",
        nav=f"/admin/campaigns/{c.id}",
        message=(
            f"Кампания «{name}» создана (id={c.id}). "
            + ("Получатели построены. " if built else "")
            + ("Открываю кампанию." if not build_error else f"Создана, но получателей не удалось построить: {build_error}")
        ),
    )