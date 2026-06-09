"""
Фоновые задачи: уведомления о днях рождения и сгорании бонусов.
"""
from datetime import datetime, timedelta, date
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import SessionLocal
from app.core.security import decrypt_field
from app.models.user import User
from app.models.bonus_grant import BonusGrant
from app.models.transaction import Transaction
from app.services.whatsapp import send_message

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

# Период неактивности для даунгрейда тира (дней)
TIER_DOWNGRADE_DAYS = 90

# За сколько дней до сгорания напоминать
BURN_REMINDER_DAYS = [15, 7, 3, 1]


def _safe_phone(user) -> str | None:
    """Расшифровывает телефон клиента. Возвращает None если не получилось."""
    raw = decrypt_field(user.phone)
    if not raw:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(digits) < 10:
        return None
    return digits


def _safe_name(user) -> str:
    """Расшифровывает имя клиента, с фолбэком."""
    raw = decrypt_field(user.full_name)
    name = (raw or "").strip()
    return name or "клиент"


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
            phone = _safe_phone(user)
            if not phone:
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

                name = _safe_name(user)
                msg = app_settings.BDAY_MESSAGE_TEMPLATE.format(
                    name=name,
                    amount=amount,
                    expires_at=(now_dt + timedelta(days=max(1, int(settings.bday_bonus_burn_days or 14)))).strftime("%d.%m.%Y"),
                )
                send_message(phone, msg, tenant_id=str(user.tenant_id))

            except Exception as e:
                db.rollback()
                logger.warning(f"birthday greeting failed for user {user.id}: {e}")
    finally:
        db.close()


def send_burn_reminders():
    """
    Напоминания о скором сгорании бонусов.
    Группируем по клиенту: если у клиента несколько грантов сгорают в один день,
    отправляем ОДНО сообщение с суммарным количеством, а не несколько подряд.
    """
    db: Session = SessionLocal()
    try:
        today = date.today()
        for days_before in BURN_REMINDER_DAYS:
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

            # Группируем remaining по user_id
            by_user: dict[int, int] = {}
            for grant in grants:
                by_user[grant.user_id] = by_user.get(grant.user_id, 0) + int(grant.remaining or 0)

            for user_id, total_remaining in by_user.items():
                if total_remaining <= 0:
                    continue
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    continue
                phone = _safe_phone(user)
                if not phone:
                    continue

                name = _safe_name(user)
                # Склонение слова "день"
                if days_before == 1:
                    day_word = "1 день"
                elif days_before in (3,):
                    day_word = f"{days_before} дня"
                else:
                    day_word = f"{days_before} дней"

                msg = (
                    f"{name}, напоминаем: у вас {total_remaining} бонусов сгорят через "
                    f"{day_word} ({target_date.strftime('%d.%m.%Y')}). "
                    f"Успейте использовать при следующей покупке!"
                )

                result = send_message(phone, msg, tenant_id=str(user.tenant_id))
                if not result.get("ok"):
                    logger.warning(
                        f"burn reminder failed user={user_id} tenant={user.tenant_id}: "
                        f"{result.get('error')}"
                    )
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
    except Exception as e:
        db.rollback()
        logger.warning(f"process_pending_bonuses failed: {e}")
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
                phone = _safe_phone(user)
                if phone:
                    try:
                        name = _safe_name(user)
                        msg = (
                            f"{name}, ваш уровень лояльности понижен до {user.tier} "
                            f"из-за длительного отсутствия покупок. "
                            f"Совершите покупку чтобы вернуть уровень!"
                        )
                        send_message(phone, msg, tenant_id=str(user.tenant_id))
                    except Exception as e:
                        logger.warning(f"tier downgrade notify failed user={user.id}: {e}")
    except Exception as e:
        db.rollback()
        logger.warning(f"check_tier_downgrade failed: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(process_pending_bonuses, 'cron', hour=3, minute=0, id='process_pending')
    scheduler.add_job(send_birthday_greetings, 'cron', hour=4, minute=0, id='birthday')
    scheduler.add_job(send_burn_reminders, 'cron', hour=5, minute=0, id='burn')
    scheduler.add_job(check_tier_downgrade, 'cron', hour=6, minute=0, id='tier_downgrade')
    scheduler.start()
