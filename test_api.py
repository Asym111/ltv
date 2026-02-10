#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from app.api.transactions import create_transaction
from app.schemas.transaction import TransactionCreate
from datetime import date

db = SessionLocal()
try:
    payload = TransactionCreate(
        user_phone='77471234567',
        amount=2000,
        paid_amount=2000,
        redeem_points=10,
        full_name='Alice',
        birth_date=date(1995, 5, 15),
        tier='Silver',
        payment_method='CARD',
        comment='Test'
    )
    result = create_transaction(payload, db)
    print('Success! ID:', result.id, 'earned_points:', result.earned_points)
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
