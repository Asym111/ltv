# app/services/wa_credits.py
"""
Внутренний баланс кредитов для официальных WhatsApp-рассылок.

1 кредит = 1 сообщение. Компания платит нам, суперадмин пополняет баланс.

Списание — атомарно в момент отправки (UPDATE ... WHERE balance >= n), поэтому
баланс не уходит в минус даже при нескольких воркерах. Если сообщение не ушло
(ошибка API или вебхук сообщил failed) — кредит возвращается.

Журнал: пополнения и корректировки — отдельной строкой; списания и возвраты
по рассылке — одной агрегированной строкой на рассылку (иначе рассылка на
5 000 человек дала бы 5 000 строк журнала).
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.wa_official import WaCreditAccount, WaCreditLedger

logger = logging.getLogger(__name__)


class InsufficientCredits(Exception):
    pass


def _ensure_account(db: Session, network_id: int) -> WaCreditAccount:
    acc = db.query(WaCreditAccount).filter(WaCreditAccount.network_id == int(network_id)).first()
    if acc is None:
        acc = WaCreditAccount(network_id=int(network_id), balance=0)
        db.add(acc)
        db.commit()
        db.refresh(acc)
    return acc


def get_balance(db: Session, network_id: int) -> int:
    acc = db.query(WaCreditAccount).filter(WaCreditAccount.network_id == int(network_id)).first()
    return int(acc.balance) if acc else 0


def _current_balance(db: Session, network_id: int) -> int:
    return int(db.execute(
        text("SELECT balance FROM wa_credit_accounts WHERE network_id = :n"),
        {"n": int(network_id)},
    ).scalar() or 0)


def topup(
    db: Session,
    network_id: int,
    credits: int,
    comment: str = "",
    amount_kzt: int | None = None,
    created_by: str = "superadmin",
    kind: str = "topup",
) -> int:
    """Пополнение (credits > 0) или корректировка (любой знак, kind='adjust'). Возвращает новый баланс."""
    credits = int(credits)
    if credits == 0:
        return get_balance(db, network_id)
    _ensure_account(db, network_id)

    if credits < 0:
        # Корректировка вниз не должна уводить баланс в минус
        res = db.execute(
            text("UPDATE wa_credit_accounts SET balance = balance + :d, updated_at = :t "
                 "WHERE network_id = :n AND balance + :d >= 0"),
            {"d": credits, "n": int(network_id), "t": datetime.utcnow()},
        )
        if (res.rowcount or 0) != 1:
            db.rollback()
            raise InsufficientCredits("Нельзя списать больше, чем есть на балансе")
    else:
        db.execute(
            text("UPDATE wa_credit_accounts SET balance = balance + :d, updated_at = :t WHERE network_id = :n"),
            {"d": credits, "n": int(network_id), "t": datetime.utcnow()},
        )

    bal = _current_balance(db, network_id)
    db.add(WaCreditLedger(
        network_id=int(network_id), delta=credits, balance_after=bal,
        kind=kind, amount_kzt=amount_kzt, comment=(comment or "")[:255],
        created_by=str(created_by)[:64],
    ))
    db.commit()
    return bal


def _bump_aggregate(db: Session, network_id: int, broadcast_id: int | None, kind: str, delta: int) -> None:
    bal = _current_balance(db, network_id)
    row = None
    if broadcast_id:
        row = (
            db.query(WaCreditLedger)
            .filter(
                WaCreditLedger.network_id == int(network_id),
                WaCreditLedger.broadcast_id == int(broadcast_id),
                WaCreditLedger.kind == kind,
            )
            .first()
        )
    if row is None:
        db.add(WaCreditLedger(
            network_id=int(network_id), delta=int(delta), balance_after=bal,
            kind=kind, broadcast_id=broadcast_id,
            comment=("Рассылка #%s" % broadcast_id) if broadcast_id else None,
            created_by="system",
        ))
    else:
        row.delta = int(row.delta) + int(delta)
        row.balance_after = bal
        row.created_at = datetime.utcnow()


def charge(db: Session, network_id: int, credits: int = 1, broadcast_id: int | None = None) -> bool:
    """
    Атомарно списывает кредиты. False — кредитов не хватает (ничего не списано).
    Коммит делает вызывающий код вместе с остальными изменениями.
    """
    credits = int(credits)
    if credits <= 0:
        return True
    res = db.execute(
        text("UPDATE wa_credit_accounts SET balance = balance - :c, updated_at = :t "
             "WHERE network_id = :n AND balance >= :c"),
        {"c": credits, "n": int(network_id), "t": datetime.utcnow()},
    )
    if (res.rowcount or 0) != 1:
        return False
    _bump_aggregate(db, network_id, broadcast_id, "charge", -credits)
    return True


def refund(db: Session, network_id: int, credits: int = 1, broadcast_id: int | None = None) -> None:
    """Возврат кредитов за неотправленное/недоставленное сообщение."""
    credits = int(credits)
    if credits <= 0:
        return
    _ensure_account(db, network_id)
    db.execute(
        text("UPDATE wa_credit_accounts SET balance = balance + :c, updated_at = :t WHERE network_id = :n"),
        {"c": credits, "n": int(network_id), "t": datetime.utcnow()},
    )
    _bump_aggregate(db, network_id, broadcast_id, "refund", credits)


def ledger(db: Session, network_id: int, limit: int = 100) -> list[dict]:
    rows = (
        db.query(WaCreditLedger)
        .filter(WaCreditLedger.network_id == int(network_id))
        .order_by(WaCreditLedger.created_at.desc(), WaCreditLedger.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "delta": int(r.delta),
            "balance_after": int(r.balance_after),
            "kind": r.kind,
            "broadcast_id": r.broadcast_id,
            "amount_kzt": r.amount_kzt,
            "comment": r.comment,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
