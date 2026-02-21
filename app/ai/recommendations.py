# app/ai/recommendations.py

from __future__ import annotations
from typing import Any

from sqlalchemy.orm import Session

from app.ai.insights import build_overview_payload


def heuristic_insights_and_recos(db: Session) -> dict[str, Any]:
    """
    Фолбэк без LLM: даём минимально полезные инсайты и рекомендации.
    """
    payload = build_overview_payload(db)  # передай tenant_id если нужна изоляция
    s = payload["summary"]
    pareto = payload["pareto"]

    insights = []
    recos = []

    if s["clients"] == 0:
        insights.append("В системе пока нет клиентов.")
        recos.append(
            {
                "action": "data_quality",
                "target": "onboarding",
                "why": "Нет данных для аналитики — сначала нужны транзакции и клиенты.",
                "suggested_bonus": 0,
                "expected_effect": "Появится база для LTV/retention.",
                "risk": "Нет",
            }
        )
        return {"payload": payload, "insights": insights, "recommendations": recos}

    insights.append(
        f"Активных за 30 дней: {s['active_30d']} из {s['clients']}."
    )
    insights.append(
        f"Клиентов в зоне риска оттока (30+ дней без покупок): {s['churn_risk']}."
    )

    if pareto["users_with_tx"] > 0:
        insights.append(
            f"Топ-20% клиентов дают ~{int(pareto['top_20_share']*100)}% выручки (по paid_amount)."
        )

    # рекомендации
    if s["churn_risk"] > 0:
        recos.append(
            {
                "action": "winback_campaign",
                "target": "inactive_30d",
                "why": "Есть сегмент клиентов без покупок 30+ дней — быстрый рост повторных продаж.",
                "suggested_bonus": 5000,
                "expected_effect": "Рост повторных покупок в сегменте 30+ дней.",
                "risk": "Часть клиентов купит только из-за бонуса — контролируй маржу.",
            }
        )

    recos.append(
        {
            "action": "tier_strategy",
            "target": "high_spenders",
            "why": "Сфокусируй коммуникацию на топ-клиентах — максимальный вклад в выручку.",
            "suggested_bonus": 0,
            "expected_effect": "Стабилизация выручки и удержание VIP.",
            "risk": "Если перегреть скидками — снизится маржа.",
        }
    )

    return {"payload": payload, "insights": insights, "recommendations": recos}