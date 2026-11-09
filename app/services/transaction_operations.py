"""Purchase and refund mutations own a single database commit."""
import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.security import encrypt_field
from app.models.auth import Tenant
from app.models.bonus_grant import BonusGrant
from app.models.refund import RefundRecord
from app.models.transaction import Transaction
from app.models.user import User
from app.services.loyalty_engine import (
    _now, consume_available, get_balances, get_settings,
    extend_active_bonuses, grant_purchase_bonus, purchase_earning, redeem_cap,
)


def _fingerprint(payload, external_id=None):
    data = payload.model_dump(mode="json", exclude={"request_id"})
    if external_id is not None:
        data["external_id"] = external_id
    value = json.dumps(data, sort_keys=True)
    return hashlib.sha256(value.encode()).hexdigest()


def _check_retry(row, fingerprint):
    if row.request_fingerprint != fingerprint:
        raise HTTPException(409, "Этот идентификатор запроса уже использован с другими данными")


def _update_tier(db, user, settings):
    tiers = settings.tiers_json or []
    if not tiers:
        return
    spent = db.scalar(select(func.coalesce(func.sum(
        Transaction.paid_amount - Transaction.refunded_amount
    ), 0)).where(Transaction.user_id == user.id))
    user.tier = "Bronze"
    for tier in sorted(tiers, key=lambda t: t.get("spend_from", 0), reverse=True):
        if int(spent) >= tier.get("spend_from", 0):
            user.tier = tier.get("name", "Bronze")
            break


def create_purchase(db, payload, tenant_id, network_id, actor_id, phone, *, integration_key_id=None, external_id=None):
    settings = get_settings(db, tenant_id)
    request_id = str(payload.request_id) if payload.request_id else None
    fingerprint = _fingerprint(payload, external_id)
    paid = payload.paid_amount if payload.paid_amount is not None else payload.amount
    if not phone or len(phone) != 11 or not phone.isdigit():
        raise HTTPException(422, "Укажите корректный номер телефона из 11 цифр")
    if paid > payload.amount:
        raise HTTPException(422, "Сумма до списания бонусов не может превышать сумму чека")
    try:
        # Serialize new-customer creation within the network before locking the wallet.
        phone_hash = hashlib.sha256(phone.encode()).hexdigest()
        user_query = select(User).where(User.tenant_id == network_id, User.phone_hash == phone_hash).execution_options(populate_existing=True)
        user = db.scalar(user_query.with_for_update())
        if user is None:
            db.scalar(select(Tenant).where(Tenant.id == network_id).with_for_update())
            user = db.scalar(user_query.with_for_update())
        if request_id or external_id:
            matches = []
            if request_id:
                matches.append(Transaction.request_id == request_id)
            if external_id:
                matches.append(Transaction.external_id == external_id)
            existing_rows = db.scalars(select(Transaction).where(
                Transaction.tenant_id == tenant_id, or_(*matches),
            )).all()
            if len(existing_rows) > 1:
                raise HTTPException(409, "Номер чека и идентификатор запроса относятся к разным покупкам")
            if existing_rows:
                existing = existing_rows[0]
                _check_retry(existing, fingerprint)
                existing_user = db.get(User, existing.user_id)
                return existing, existing_user, {}, False
        if user is None:
            user = User(tenant_id=network_id, phone=encrypt_field(phone), phone_hash=phone_hash,
                        full_name=encrypt_field(payload.full_name or ""), birth_date=payload.birth_date,
                        tier=payload.tier or "Bronze", bonus_balance=0)
            db.add(user)
            db.flush()
        else:
            if payload.full_name:
                user.full_name = encrypt_field(payload.full_name)
            if payload.birth_date:
                user.birth_date = payload.birth_date

        balances = get_balances(db, user.id, commit=False)
        cap = redeem_cap(paid, settings)
        requested = min(balances["available"], cap) if payload.redeem_all else payload.redeem_points
        if requested > balances["available"]:
            raise HTTPException(409, f"Недостаточно активных бонусов. Доступно: {balances['available']}")
        if requested > cap:
            raise HTTPException(422, f"Превышен лимит списания. Максимум: {cap}")
        base = paid - requested
        try:
            mode, rate, earned = purchase_earning(base, user.tier, settings, payload.manual_percent)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        redeemed = consume_available(db, user.id, requested, commit=False)
        if redeemed != requested:
            raise HTTPException(409, "Баланс изменился. Обновите данные клиента")
        tx = Transaction(
            tenant_id=tenant_id, user_id=user.id, amount=payload.amount, paid_amount=paid,
            redeem_points=redeemed, earned_points=earned, payment_method=payload.payment_method,
            comment=payload.comment, status="completed", refunded_amount=0,
            earning_mode=mode, earn_percent=rate, earn_base_amount=base,
            created_by_id=actor_id, request_id=request_id, request_fingerprint=fingerprint,
            integration_key_id=integration_key_id, external_id=external_id,
        )
        db.add(tx)
        db.flush()
        # Любая покупка продлевает срок жизни всех действующих бонусов клиента
        extend_active_bonuses(db, user.id, settings, commit=False)
        grant_purchase_bonus(db, user.id, earned, settings, txn_id=tx.id, tenant_id=tenant_id, commit=False)
        balances = get_balances(db, user.id, commit=False)
        user.bonus_balance = balances["total"]
        _update_tier(db, user, settings)
        db.commit()
        return tx, user, balances, True
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Конфликт данных покупки. Обновите данные и повторите запрос") from exc
    except Exception:
        db.rollback()
        raise


def refund_purchase(db, tx_id, payload, allowed_ids, network_id, actor_id, *, integration_key_id=None, external_id=None):
    tx = db.scalar(select(Transaction).where(
        Transaction.id == tx_id, Transaction.tenant_id.in_(allowed_ids),
    ))
    if tx is None:
        raise HTTPException(404, "Транзакция не найдена")
    settings = get_settings(db, tx.tenant_id)
    fingerprint = _fingerprint(payload, external_id)
    request_id = str(payload.request_id) if payload.request_id else None
    now = _now()
    try:
        # All wallet mutations use the same lock order: customer, then purchase/grants.
        user = db.scalar(select(User).where(
            User.id == tx.user_id, User.tenant_id == network_id,
        ).with_for_update().execution_options(populate_existing=True))
        if user is None:
            raise HTTPException(404, "Клиент не найден")
        tx = db.scalar(select(Transaction).where(Transaction.id == tx_id).with_for_update()
                       .execution_options(populate_existing=True))
        if request_id or external_id:
            matches = []
            if request_id:
                matches.append((RefundRecord.transaction_id == tx.id) & (RefundRecord.request_id == request_id))
            if external_id:
                matches.append((RefundRecord.tenant_id == tx.tenant_id) & (RefundRecord.external_id == external_id))
            existing_rows = db.scalars(select(RefundRecord).where(or_(*matches))).all()
            if len(existing_rows) > 1:
                raise HTTPException(409, "Номер возврата и идентификатор запроса относятся к разным операциям")
            if existing_rows:
                existing = existing_rows[0]
                if existing.transaction_id != tx.id:
                    raise HTTPException(409, "Этот номер возврата уже использован для другой покупки")
                _check_retry(existing, fingerprint)
                return tx, user, {}, None
        left = tx.paid_amount - tx.refunded_amount
        if tx.status == "refunded" or left <= 0:
            raise HTTPException(409, "Транзакция уже полностью возвращена")
        amount = left if payload.full_refund else payload.amount
        if amount is None or amount <= 0:
            raise HTTPException(422, "Укажите положительную сумму возврата")
        if amount > left:
            raise HTTPException(422, f"Сумма возврата превышает остаток: {left}")

        get_balances(db, user.id, now, commit=False)
        cumulative = tx.refunded_amount + amount
        reverse = tx.earned_points * cumulative // tx.paid_amount - tx.refunded_earned_points
        restore = tx.redeem_points * cumulative // tx.paid_amount - tx.refunded_redeem_points
        if restore:
            db.add(BonusGrant(user_id=user.id, tenant_id=tx.tenant_id, transaction_id=tx.id,
                              amount=restore, remaining=restore, status="available", available_from=now,
                              expires_at=now + timedelta(days=max(1, settings.burn_days)),
                              source="refund_redeem"))
            db.flush()
        if reverse:
            grant = db.scalar(select(BonusGrant).where(
                BonusGrant.user_id == user.id, BonusGrant.transaction_id == tx.id,
                BonusGrant.source == "purchase",
            ).with_for_update().execution_options(populate_existing=True))
            # Expired rewards are already gone: do not charge another grant for them.
            shortfall = 0 if grant is not None and grant.expires_at <= now else reverse
            if grant is not None and shortfall:
                take = min(grant.remaining, shortfall)
                grant.remaining -= take
                shortfall -= take
                if grant.remaining == 0:
                    grant.status = "expired"
                db.flush()
            if shortfall:
                spent = consume_available(db, user.id, shortfall, now, commit=False)
                if spent != shortfall:
                    raise HTTPException(409, "Начисленные бонусы уже потрачены. Недостаточно бонусов "
                                        "для отмены начисления; возврат не выполнен")

        tx.refunded_amount = cumulative
        tx.refunded_at = now
        tx.refunded_earned_points += reverse
        tx.refunded_redeem_points += restore
        tx.status = "refunded" if cumulative == tx.paid_amount else "partially_refunded"
        record = RefundRecord(transaction_id=tx.id, tenant_id=tx.tenant_id, created_by_id=actor_id,
                              request_id=request_id, request_fingerprint=fingerprint,
                              amount=amount, earned_reversed=reverse, redeemed_restored=restore,
                              integration_key_id=integration_key_id, external_id=external_id,
                              comment=payload.comment, created_at=now)
        db.add(record)
        db.flush()
        balances = get_balances(db, user.id, now, commit=False)
        user.bonus_balance = balances["total"]
        _update_tier(db, user, settings)
        db.commit()
        return tx, user, balances, record
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Номер возврата уже используется. Проверьте данные запроса") from exc
    except Exception:
        db.rollback()
        raise
