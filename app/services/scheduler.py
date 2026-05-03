"""
Фоновые задачи: уведомления о днях рождения и сгорании бонусов.
"""
from datetime import datetime, timedelta, date
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.user import User
from app.models.bonus_grant import BonusGrant
from app.services.whatsapp import send_message

scheduler = BackgroundScheduler()


def send_birthday_greetings():
    db: Session = SessionLocal()
    try:
        today = date.today()
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
                msg = f"С Днём рождения, {user.full_name or 'клиент'}! 🎂 Ваш баланс: {int(user.bonus_balance or 0)} бонусов."
                send_message(user.phone, msg)
            except Exception:
                pass
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
                    send_message(user.phone, msg)
                except Exception:
                    pass
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(send_birthday_greetings, 'cron', hour=4, minute=0, id='birthday')
    scheduler.add_job(send_burn_reminders, 'cron', hour=5, minute=0, id='burn')
    scheduler.start()
