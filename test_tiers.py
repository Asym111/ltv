#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from app.api.transactions import create_transaction
from app.schemas.transaction import TransactionCreate
from datetime import date

db = SessionLocal()
try:
    # Test 1: Bronze user
    payload1 = TransactionCreate(
        user_phone='77491234567',
        amount=1000,
        paid_amount=None,  # Test with None
        redeem_points=0,
        full_name='Bob',
        birth_date=date(1990, 1, 1),
        tier='Bronze',
        payment_method='CASH',
        comment='Test Bronze'
    )
    result1 = create_transaction(payload1, db)
    print(f'Bronze: ID={result1.id}, earned={result1.earned_points} (expected 30: 1000*0.03)')
    
    # Test 2: Silver user
    payload2 = TransactionCreate(
        user_phone='77492234567',
        amount=2000,
        paid_amount=1900,
        redeem_points=100,
        full_name='Carol',
        birth_date=date(1995, 5, 15),
        tier='Silver',
        payment_method='CARD',
        comment='Test Silver'
    )
    result2 = create_transaction(payload2, db)
    print(f'Silver: ID={result2.id}, earned={result2.earned_points} (expected 90: (1900-100)*0.05)')
    
    # Test 3: Gold user
    payload3 = TransactionCreate(
        user_phone='77493234567',
        amount=5000,
        paid_amount=4500,
        redeem_points=500,
        full_name='David',
        birth_date=date(1992, 3, 20),
        tier='Gold',
        payment_method='TRANSFER',
        comment='Test Gold'
    )
    result3 = create_transaction(payload3, db)
    print(f'Gold: ID={result3.id}, earned={result3.earned_points} (expected 280: (4500-500)*0.07)')
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
