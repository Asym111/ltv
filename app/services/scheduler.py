"""
Фоновые задачи: уведомления о днях рождения и сгорании бонусов.
"""
from datetime import datetime, timedelta, date
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.user import User
from app.models.bonus_grant import BonusGrant
from app.models.transaction import Transaction
from app.services.whatsapp import send_message

scheduler = BackgroundScheduler()

# Период неактивности для даунгрейда тира (дней)
TIER_DOWNGRADE_DAYS = 90


def send_birthday_greetings():
    db: Session = SessionLocal()
    try:
        today = date.today()
        now_dt = datetime.now()
        users = (
            db.query(User)
            .filter(
                User.birth_date.isnot(None),
                db.func.extract('month', User.birth_date) == today.month,
                db.func.extract('day', User.birth_date) == today.day,
            )
            .all()
        )
        for user in users:
            if not user.phone:
                continue
            try:
                from app.services.loyalty_engine import get_settings
                from app.core.config import settings as app_settings

                settings = get_settings(db, tenant_id=user.tenant_id)
                amount = int(settings.bday_bonus_amount or 0)

                if amount > 0:
                    burn_days = max(1, int(settings.bday_bonus_burn_days or 14))
                    expires_at = now_dt + timedelta(days=burn_days)

                    grant = BonusGrant(
                        user_id=user.id,
                        amount=amount,
                        remaining=amount,
                        status="available",
                        available_from=now_dt,
                        expires_at=expires_at,
                        source="birthday",
                    )
                    db.add(grant)
                    db.commit()

                name = user.full_name or "клиент"
                msg = app_settings.BDAY_MESSAGE_TEMPLATE.format(
                    name=name,
                    amount=amount,
                    expires_at=(now_dt + timedelta(days=max(1, int(settings.bday_bonus_burn_days or 14)))).strftime("%d.%m.%Y"),
                )
                # ВАЖНО: передаём tenant_id, чтобы сообщение ушло через WhatsApp нужного филиала
                send_message(user.phone, msg, tenant_id=str(user.tenant_id))

            except Exception:
                db.rollback()
    finally:
        db.close()


def send_burn_reminders():
    db: Session = SessionLocal()
    try:
        today = date.today()
        for days_before in [7, 3, 1]:
            target_date = today + timedelta(days=days_before)
            grants = (
                db.query(BonusGrant)
                .filter(
                    BonusGrant.status == "available",
                    BonusGrant.remaining > 0,
                    db.func.date(BonusGrant.expires_at) == target_date,
                )
                .all()
            )
            for grant in grants:
                user = db.query(User).filter(User.id == grant.user_id).first()
                if not user or not user.phone:
                    continue
                try:
                    msg = f"Внимание! {grant.remaining} бонусов сгорят через {days_before} дн. ({target_date.strftime('%d.%m.%Y')}). Успейте использовать!"
                    # ВАЖНО: передаём tenant_id владельца бонуса
                    send_message(user.phone, msg, tenant_id=str(user.tenant_id))
                except Exception:
                    pass
    finally:
        db.close()


def process_pending_bonuses():
    """Ежедневный перевод pending бонусов в available."""
    db: Session = SessionLocal()
    try:
        now = datetime.now()
        grants = (
            db.query(BonusGrant)
            .filter(
                BonusGrant.status == "pending",
                BonusGrant.remaining > 0,
                BonusGrant.available_from <= now,
            )
            .all()
        )
        for grant in grants:
            grant.status = "available"
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def check_tier_downgrade():
    """
    Авто-даунгрейд тира при неактивности.
    Если клиент Gold/Silver и последняя транзакция была > 90 дней назад,
    понижаем на один уровень.
    """
    db: Session = SessionLocal()
    try:
        cutoff_date = datetime.now() - timedelta(days=TIER_DOWNGRADE_DAYS)

        # Все клиенты с тиром выше Bronze
        users = (
            db.query(User)
            .filter(User.tier.in_(["Gold", "Silver"]))
            .all()
        )

        for user in users:
            # Последняя транзакция клиента
            last_tx = (
                db.query(func.max(Transaction.created_at))
                .filter(Transaction.user_id == user.id)
                .scalar()
            )

            if last_tx is None or last_tx < cutoff_date:
                old_tier = user.tier
                if old_tier == "Gold":
                    user.tier = "Silver"
                elif old_tier == "Silver":
                    user.tier = "Bronze"

                db.commit()

                # Уведомление клиенту
                if user.phone:
                    try:
                        msg = f"Ваш уровень лояльности понижен до {user.tier} из-за длительного отсутствия покупок. Совершите покупку чтобы вернуть уровень!"
                        # ВАЖНО: передаём tenant_id клиента
                        send_message(user.phone, msg, tenant_id=str(user.tenant_id))
                    except Exception:
                        pass
    except Exception:
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(process_pending_bonuses, 'cron', hour=3, minute=0, id='process_pending')
    scheduler.add_job(send_birthday_greetings, 'cron', hour=4, minute=0, id='birthday')
    scheduler.add_job(send_burn_reminders, 'cron', hour=5, minute=0, id='burn')
    scheduler.add_job(check_tier_downgrade, 'cron', hour=6, minute=0, id='tier_downgrade')
    scheduler.start()
