#!/usr/bin/env python
import sys
import requests
import json
from time import sleep

BASE_URL = "http://127.0.0.1:8000/api"

def test_post_transaction():
    print("\n=== TEST 1: POST Transaction (Bronze) ===")
    payload = {
        "user_phone": "77501234567",
        "amount": 1000,
        "paid_amount": 1000,
        "redeem_points": 0,
        "full_name": "Test User",
        "birth_date": "1990-01-01",
        "tier": "Bronze",
        "payment_method": "CASH",
        "comment": "Test transaction"
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/transactions/", json=payload)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"ID: {data['id']}")
            print(f"user_phone: {data['user_phone']}")
            print(f"amount: {data['amount']}")
            print(f"earned_points: {data['earned_points']}")
            print(f"redeem_points: {data['redeem_points']}")
            print("✓ PASSED")
            return True
        else:
            print(f"Error: {resp.text}")
            return False
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_get_by_phone():
    print("\n=== TEST 2: GET by phone ===")
    try:
        resp = requests.get(f"{BASE_URL}/transactions/by-phone/77501234567")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Transactions count: {len(data)}")
            if len(data) > 0:
                print(f"First transaction ID: {data[0]['id']}")
                print("✓ PASSED")
                return True
            else:
                print("No transactions found")
                return False
        else:
            print(f"Error: {resp.text}")
            return False
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

def test_get_crm():
    print("\n=== TEST 3: GET CRM client ===")
    try:
        resp = requests.get(f"{BASE_URL}/crm/client/77501234567")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"phone: {data['phone']}")
            print(f"full_name: {data['full_name']}")
            print(f"tier: {data['tier']}")
            print(f"total_spent: {data['total_spent']}")
            print(f"bonus_balance: {data['bonus_balance']}")
            print("✓ PASSED")
            return True
        else:
            print(f"Error: {resp.text}")
            return False
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

if __name__ == "__main__":
    print("Testing API endpoints...")
    sleep(1)  # Give server time to start
    
    results = []
    results.append(test_post_transaction())
    sleep(0.5)
    results.append(test_get_by_phone())
    sleep(0.5)
    results.append(test_get_crm())
    
    print("\n" + "="*50)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    if all(results):
        print("✓ All tests PASSED!")
        sys.exit(0)
    else:
        print("✗ Some tests FAILED")
        sys.exit(1)
