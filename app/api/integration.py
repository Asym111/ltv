"""Small, branch-scoped API for external cash desks. No browser-session identity."""
import hashlib
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.integration_auth import API_PREFIX, IntegrationContext, authenticate_integration, require_integration_scope
from app.models.refund import RefundRecord
from app.models.auth import Tenant
from app.models.integration_key import IntegrationKey
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.integration import (
    BalanceIn, BalanceOut, IntegrationTransactionOut, PurchaseIn, RefundIn, RefundResponse,
)
from app.schemas.transaction import TransactionCreate, TransactionRefund
from app.services.loyalty_engine import get_balances, get_settings, redeem_cap
from app.services.transaction_operations import create_purchase, refund_purchase


router = APIRouter(prefix=API_PREFIX, tags=["integration v1"], dependencies=[Depends(authenticate_integration)])


def normalize_phone(raw):
    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) != 11 or not digits.startswith("7"):
        raise HTTPException(422, "Укажите корректный номер Казахстана из 11 цифр")
    return digits


def transaction_response(tx, replayed=False):
    return IntegrationTransactionOut(
        id=tx.id, external_id=tx.external_id, status=tx.status, amount=tx.amount,
        cash_amount=tx.paid_amount - tx.redeem_points,
        redeem_points=tx.redeem_points, earned_points=tx.earned_points,
        earning_mode=tx.earning_mode, earn_percent=tx.earn_percent, earn_base_amount=tx.earn_base_amount,
        refunded_amount=tx.refunded_amount, refundable_amount=max(0, tx.paid_amount - tx.refunded_amount),
        refunded_earned_points=tx.refunded_earned_points, refunded_redeem_points=tx.refunded_redeem_points,
        replayed=replayed,
    )


def find_transaction(db, context, tx_id=None, external_id=None):
    query = select(Transaction).join(User).where(
        Transaction.tenant_id == context.tenant_id, User.tenant_id == context.network_id,
    )
    query = query.where(Transaction.id == tx_id) if tx_id is not None else query.where(Transaction.external_id == external_id)
    tx = db.scalar(query)
    if tx is None:
        raise HTTPException(404, "Транзакция не найдена")
    return tx


def queue_message(db, context, user, text):
    try:
        from app.core.security import decrypt_field
        from app.services.notify_queue import enqueue_notification, PRIORITY_TRANSACTIONAL
        enqueue_notification(db, tenant_id=context.tenant_id, phone=decrypt_field(user.phone),
                             text_=text, user_id=user.id, priority=PRIORITY_TRANSACTIONAL)
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("Integration notification failed")


@router.get("/me")
def who_am_i(context: IntegrationContext = Depends(authenticate_integration), db: Session = Depends(get_db)):
    settings = get_settings(db, context.tenant_id)
    return {"key_id": context.key_id, "tenant_id": context.tenant_id, "network_id": context.network_id,
            "organization": db.get(Tenant, context.network_id).name,
            "branch": db.get(Tenant, context.tenant_id).name,
            "expires_at": db.get(IntegrationKey, context.key_id).expires_at,
            "scopes": list(context.scopes), "earning_mode": settings.earning_mode}


@router.post("/balance", response_model=BalanceOut)
def customer_balance(payload: BalanceIn,
                     context: IntegrationContext = Depends(require_integration_scope("balance:read")),
                     db: Session = Depends(get_db)):
    phone = normalize_phone(payload.phone)
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()
    user = db.scalar(select(User).where(User.tenant_id == context.network_id, User.phone_hash == phone_hash))
    balances = get_balances(db, user.id) if user else {"available": 0, "pending": 0, "total": 0}
    settings = get_settings(db, context.tenant_id)
    return BalanceOut(found=user is not None, phone=phone, **balances, earning_mode=settings.earning_mode,
                      redeem_max_percent=settings.redeem_max_percent,
                      max_redeem=min(balances["available"], redeem_cap(payload.amount, settings)))


@router.post("/transactions", response_model=IntegrationTransactionOut)
def create_transaction(payload: PurchaseIn,
                       context: IntegrationContext = Depends(require_integration_scope("transactions:write")),
                       db: Session = Depends(get_db)):
    phone = normalize_phone(payload.phone)
    purchase = TransactionCreate(
        user_phone=phone, amount=payload.amount, redeem_points=payload.redeem_points,
        manual_percent=payload.manual_percent, payment_method=payload.payment_method,
        full_name=payload.full_name, birth_date=payload.birth_date, comment=payload.comment,
        request_id=payload.request_id,
    )
    tx, user, balances, created = create_purchase(
        db, purchase, context.tenant_id, context.network_id, None, phone,
        integration_key_id=context.key_id, external_id=payload.external_id,
    )
    response = transaction_response(tx, replayed=not created)
    if created and (tx.redeem_points or tx.earned_points):
        queue_message(db, context, user, f"Спасибо за покупку! Списано {tx.redeem_points}, "
                      f"начислено {tx.earned_points} бонусов. Баланс: {balances['total']}.")
    return response


@router.get("/transactions/by-external/{external_id:path}", response_model=IntegrationTransactionOut)
def get_by_external(external_id: str,
                    context: IntegrationContext = Depends(require_integration_scope("transactions:read")),
                    db: Session = Depends(get_db)):
    return transaction_response(find_transaction(db, context, external_id=external_id))


@router.get("/transactions/{tx_id}", response_model=IntegrationTransactionOut)
def get_transaction(tx_id: int,
                    context: IntegrationContext = Depends(require_integration_scope("transactions:read")),
                    db: Session = Depends(get_db)):
    return transaction_response(find_transaction(db, context, tx_id=tx_id))


@router.post("/transactions/{tx_id}/refunds", response_model=RefundResponse)
def refund_transaction(tx_id: int, payload: RefundIn,
                       context: IntegrationContext = Depends(require_integration_scope("refunds:write")),
                       db: Session = Depends(get_db)):
    find_transaction(db, context, tx_id=tx_id)
    refund = TransactionRefund(full_refund=payload.full_refund, amount=payload.amount,
                               comment=payload.comment, request_id=payload.request_id)
    tx, user, balances, record = refund_purchase(
        db, tx_id, refund, [context.tenant_id], context.network_id, None,
        integration_key_id=context.key_id, external_id=payload.external_id,
    )
    replayed = record is None
    if record is None:
        record = db.scalar(select(RefundRecord).where(
            RefundRecord.transaction_id == tx.id, RefundRecord.external_id == payload.external_id,
        ))
    response = RefundResponse(transaction=transaction_response(tx), refund=record, replayed=replayed)
    if not replayed:
        queue_message(db, context, user, f"Возврат на {record.amount}₸. "
                      f"Возвращено {record.redeemed_restored}, отменено {record.earned_reversed} бонусов. "
                      f"Баланс: {balances['total']}.")
    return response
