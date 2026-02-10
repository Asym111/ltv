from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.config import settings

from app.schemas.ai import AiAskIn, AiAskOut, AiRecoOut
from app.ai.prompts import SYSTEM_PROMPT_RU, build_user_prompt
from app.ai.gemini_client import gemini_generate_json, GeminiError
from app.ai.openai_client import openai_generate_json, OpenAIError

from app.models.user import User
from app.models.transaction import Transaction
from app.ai.insights import build_overview_payload  # business overview
from app.services.loyalty_engine import get_balances  # pending/available


router = APIRouter(prefix="/ai", tags=["ai"])


def _mock_allowed() -> bool:
    v = getattr(settings, "AI_MOCK_IF_NO_KEY", None)
    if v is None:
        return True
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _provider() -> str:
    p = str(getattr(settings, "AI_PROVIDER", "auto") or "auto").strip().lower()
    # auto | openai | gemini | off
    if p not in ("auto", "openai", "gemini", "off"):
        return "auto"
    return p


def _provider_order() -> list[str]:
    p = _provider()
    if p == "openai":
        return ["openai"]
    if p == "gemini":
        return ["gemini"]
    if p == "off":
        return []
    return ["openai", "gemini"]  # auto


def normalize_phone(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if s.startswith("+"):
        s = s[1:]
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) > 11:
        digits = digits[-11:]
    return digits


def _build_user_prompt_safe(context: str, payload: dict[str, Any], question: str) -> str:
    """
    Защита от разных версий build_user_prompt.
    - новая сигнатура: build_user_prompt(context, payload, question)
    - старая сигнатура: build_user_prompt(payload)
    """
    try:
        return build_user_prompt(context, payload, question)  # type: ignore[misc]
    except TypeError:
        base = build_user_prompt(payload)  # type: ignore[call-arg]
        return f"{base}\n\nВопрос:\n{question}".strip()


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
        last_purchase_at = payload.get("last_purchase_at")

        insights.append(f"Уровень клиента: {tier}. Покупок: {purchases}. Total paid: {total}.")
        insights.append(f"Бонусы: доступно {avail}, в ожидании {pending}.")
        if last_purchase_at:
            insights.append(f"Последняя покупка: {last_purchase_at} (R={recency_days} дней).")

        # Навигационные рекомендации (машиночитаемый target)
        if purchases == 0:
            recos.append(
                AiRecoOut(
                    action="Создать приветственную кампанию для новых",
                    target="nav:/admin/campaigns",
                    why="Нет истории покупок — важна вторая покупка и быстрый повторный контакт",
                    suggested_bonus=0,
                    expected_effect="Рост вероятности 2-й покупки",
                    risk="Нужно задать оффер и сегментацию (new/first-buy)",
                )
            )
        else:
            # если давно не покупал — ведем в сегмент risk
            if isinstance(recency_days, int) and recency_days >= 30:
                recos.append(
                    AiRecoOut(
                        action="Открыть сегмент риска и подготовить win-back оффер",
                        target="nav:/admin/analytics/segment/risk",
                        why="Клиент давно не покупал — риск ухода повышается",
                        suggested_bonus=0,
                        expected_effect="Возврат части клиентов и рост повторов",
                        risk="Нужны корректные пороги RFM и текст/канал",
                    )
                )
            else:
                recos.append(
                    AiRecoOut(
                        action="Открыть кампании и подготовить персональный оффер",
                        target="nav:/admin/campaigns",
                        why="Есть история — можно стимулировать повтор по сегменту",
                        suggested_bonus=0,
                        expected_effect="Рост повторных покупок",
                        risk="Без категорий/интересов оффер будет общим",
                    )
                )

        # быстрый переход на транзакции клиента
        if phone:
            recos.append(
                AiRecoOut(
                    action="Проверить транзакции клиента",
                    target=f"nav:/admin/transactions?phone={phone}",
                    why="Уточнить последние суммы/списания/начисления перед контактом",
                    suggested_bonus=0,
                    expected_effect="Точнее следующий шаг (NBA)",
                    risk="Нет",
                )
            )

        answer = (
            "Собрал профиль клиента по имеющимся данным. "
            "Для точных рекомендаций полезно добавить: категории покупок, интервалы между покупками, предпочтительный канал (WA/TG/SMS)."
        )
        return AiAskOut(
            mode="heuristic",
            context=context,  # type: ignore
            answer=answer,
            insights=insights[:10],
            recommendations=recos[:10],
            payload=payload,
            llm_error="LLM недоступен или отключён",
        )

    answer = (
        "Сформировал краткий обзор. Для более точных рекомендаций нужны: периоды 7/30/90, "
        "разрез по каналам/менеджерам и маржинальность."
    )
    insights.append("LLM недоступен — показаны базовые эвристики.")
    recos.append(
        AiRecoOut(
            action="Открыть аналитику и проверить алерты",
            target="nav:/admin/analytics",
            why="Без динамики 7/30/90 рекомендации по удержанию будут неточны",
            suggested_bonus=0,
            expected_effect="Появится управляемая retention-картина",
            risk="Потребуется ввести/подтянуть дополнительные метрики",
        )
    )
    recos.append(
        AiRecoOut(
            action="Открыть VIP сегмент и спланировать оффер",
            target="nav:/admin/analytics/segment/vip",
            why="VIP дают диспропорциональную долю выручки (Pareto)",
            suggested_bonus=0,
            expected_effect="Увеличение повторов и среднего чека",
            risk="Важно не демпинговать бонусом без правил",
        )
    )
    return AiAskOut(
        mode="heuristic",
        context=context,  # type: ignore
        answer=answer,
        insights=insights[:10],
        recommendations=recos[:10],
        payload=payload,
        llm_error="LLM недоступен или отключён",
    )


def _validate_llm_shape(obj: dict[str, Any]) -> tuple[str, list[str], list[AiRecoOut]]:
    answer = obj.get("answer")
    insights = obj.get("insights")
    recos = obj.get("recommendations")

    if not isinstance(answer, str):
        raise GeminiError("JSON missing 'answer' (string)")
    if not isinstance(insights, list) or not all(isinstance(x, str) for x in insights):
        raise GeminiError("JSON missing 'insights' (list[str])")
    if not isinstance(recos, list):
        raise GeminiError("JSON missing 'recommendations' (list)")

    out_recos: list[AiRecoOut] = []
    for r in recos[:10]:
        if not isinstance(r, dict):
            continue
        out_recos.append(
            AiRecoOut(
                action=str(r.get("action") or "").strip() or "—",
                target=str(r.get("target") or "").strip() or "—",
                why=str(r.get("why") or "").strip() or "—",
                suggested_bonus=int(r.get("suggested_bonus") or 0),
                expected_effect=str(r.get("expected_effect") or "").strip() or "—",
                risk=str(r.get("risk") or "").strip() or "—",
            )
        )

    return answer.strip(), insights[:10], out_recos


def _build_client_payload(db: Session, phone: str) -> dict[str, Any]:
    p = normalize_phone(phone)
    if not p:
        raise HTTPException(status_code=400, detail="Invalid phone")

    user = db.query(User).filter(User.phone == p).first()
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")

    # базовые итоги
    total_spent, purchases_count = (
        db.query(
            func.coalesce(func.sum(Transaction.paid_amount), 0),
            func.count(Transaction.id),
        )
        .filter(Transaction.user_id == user.id)
        .first()
    )

    total_spent = int(total_spent or 0)
    purchases_count = int(purchases_count or 0)
    avg_check = (total_spent / purchases_count) if purchases_count else 0.0

    # окна 30/90
    now = datetime.utcnow()
    since_30d = now - timedelta(days=30)
    since_90d = now - timedelta(days=90)

    revenue_30d, purchases_30d = (
        db.query(
            func.coalesce(func.sum(Transaction.paid_amount), 0),
            func.count(Transaction.id),
        )
        .filter(Transaction.user_id == user.id)
        .filter(Transaction.created_at >= since_30d)
        .first()
    )
    revenue_90d, purchases_90d = (
        db.query(
            func.coalesce(func.sum(Transaction.paid_amount), 0),
            func.count(Transaction.id),
        )
        .filter(Transaction.user_id == user.id)
        .filter(Transaction.created_at >= since_90d)
        .first()
    )

    revenue_30d = int(revenue_30d or 0)
    purchases_30d = int(purchases_30d or 0)
    revenue_90d = int(revenue_90d or 0)
    purchases_90d = int(purchases_90d or 0)

    # последняя транзакция
    last_tx = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .first()
    )

    last_purchase_at = last_tx.created_at.isoformat() if last_tx and last_tx.created_at else None
    recency_days: int | None = None
    if last_tx and last_tx.created_at:
        recency_days = int((now - last_tx.created_at).days)

    balances = get_balances(db, user_id=user.id)

    return {
        "phone": user.phone,
        "full_name": user.full_name or None,
        "tier": user.tier or "Bronze",
        "total_spent": total_spent,
        "purchases_count": purchases_count,
        "avg_check": round(float(avg_check), 2),
        "last_purchase_at": last_purchase_at,
        "recency_days": recency_days,
        "windows": {
            "revenue_30d": revenue_30d,
            "purchases_30d": purchases_30d,
            "revenue_90d": revenue_90d,
            "purchases_90d": purchases_90d,
        },
        "last_tx": {
            "paid_amount": int(last_tx.paid_amount) if last_tx else 0,
            "amount": int(last_tx.amount) if last_tx else 0,
            "earned_points": int(last_tx.earned_points) if last_tx else 0,
            "redeem_points": int(last_tx.redeem_points) if last_tx else 0,
            "payment_method": str(last_tx.payment_method) if last_tx else None,
            "comment": str(last_tx.comment) if last_tx and last_tx.comment else None,
        } if last_tx else None,
        "bonus": {
            "available": int(balances.get("available") or 0),
            "pending": int(balances.get("pending") or 0),
        },
        "rules_hint": {
            "tier_is_by_paid_amount": True,
            "activation_days_from_activation_date": True,
        },
    }


async def _try_llm(provider: str, context: str, payload: dict[str, Any], question: str) -> tuple[str, str, list[str], list[AiRecoOut]]:
    user_prompt = _build_user_prompt_safe(context, payload, question)

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise OpenAIError("OPENAI_API_KEY is missing")
        res = await openai_generate_json(
            SYSTEM_PROMPT_RU,
            user_prompt,
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
        )
        answer, insights, recos = _validate_llm_shape(res)
        return ("openai", answer, insights, recos)

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise GeminiError("GEMINI_API_KEY is missing")
        res = await gemini_generate_json(SYSTEM_PROMPT_RU, user_prompt)
        answer, insights, recos = _validate_llm_shape(res)
        return ("gemini", answer, insights, recos)

    raise RuntimeError("Unknown provider")


@router.get("/overview")
async def ai_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    payload = build_overview_payload(db)
    question = "Сделай Owner Overview по текущим данным"

    last_err: str | None = None
    for prov in _provider_order():
        try:
            mode, answer, insights, recos = await _try_llm(prov, "business", payload, question)
            return {
                "mode": mode,
                "payload": payload,
                "answer": answer,
                "insights": insights,
                "recommendations": [r.model_dump() for r in recos],
            }
        except Exception as e:
            last_err = str(e)

    if _mock_allowed():
        fb = _heuristic_answer("business", payload, "overview")
        fb.llm_error = last_err or "LLM disabled"
        return fb.model_dump()

    return {
        "mode": "error",
        "payload": payload,
        "error": last_err or "LLM disabled",
        "answer": "",
        "insights": [],
        "recommendations": [],
    }


@router.get("/ask")
async def ai_ask_get(
    context: str = "business",
    question: Optional[str] = None,
    phone: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Any:
    if not question:
        return {
            "ok": True,
            "message": "Используй POST /api/ai/ask с JSON {context, question, phone?} или GET /api/ai/overview",
        }

    try:
        payload_in = AiAskIn(context=context, question=question, phone=phone)  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await ai_ask(payload_in, db)


@router.post("/ask", response_model=AiAskOut)
async def ai_ask(payload_in: AiAskIn, db: Session = Depends(get_db)) -> AiAskOut:
    context = payload_in.context

    if context == "business":
        payload = build_overview_payload(db)
    else:
        if not payload_in.phone:
            raise HTTPException(status_code=400, detail="phone is required for client/operator context")
        payload = _build_client_payload(db, payload_in.phone)

    last_err: str | None = None
    for prov in _provider_order():
        try:
            mode, answer, insights, recos = await _try_llm(prov, context, payload, payload_in.question)
            return AiAskOut(
                mode=mode,  # openai|gemini
                context=context,
                answer=answer,
                insights=insights,
                recommendations=recos,
                payload=payload,
                llm_error=None,
            )
        except Exception as e:
            last_err = str(e)

    if _mock_allowed():
        fb = _heuristic_answer(context, payload, payload_in.question)
        fb.llm_error = last_err or "LLM disabled"
        return fb

    return AiAskOut(
        mode="error",
        context=context,
        answer="",
        insights=[],
        recommendations=[],
        payload=payload,
        llm_error=last_err or "LLM disabled",
    )
