"""Regression tests use a disposable database, never the deployed application."""
import os
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.models.auth import AuthUser, Tenant
from app.models.bonus_grant import BonusGrant
from app.models.refund import RefundRecord
from app.models.integration_key import IntegrationKey
from app.models.settings_model import Settings
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionRefund
from app.services import transaction_operations as operations
from app.services.loyalty_engine import _now, get_balances, consume_available


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [Tenant.__table__, AuthUser.__table__, IntegrationKey.__table__, User.__table__, Transaction.__table__,
              Settings.__table__, BonusGrant.__table__, RefundRecord.__table__]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine, autoflush=False) as session:
        session.add_all([Tenant(id=1, name="Lurea"), Tenant(id=2, name="Other"),
                         Tenant(id=3, name="Branch", parent_tenant_id=1)])
        session.add_all([Settings(tenant_id=1, earning_mode="manual", activation_days=0,
                                  redeem_max_percent=100, tiers_json=[]),
                         Settings(tenant_id=2, earning_mode="automatic", activation_days=0)])
        session.add(AuthUser(id=1, tenant_id=1, name="Owner", phone="77000000000",
                             role="owner", password_salt="test", password_hash="test"))
        session.add(AuthUser(id=2, tenant_id=2, name="Other owner", phone="77000000002",
                             role="owner", password_salt="test", password_hash="test"))
        session.commit()
        yield session
    engine.dispose()


def purchase(db, **overrides):
    values = dict(user_phone="77001234567", amount=1000, manual_percent="10", request_id=uuid4())
    values.update(overrides)
    payload = TransactionCreate(**values)
    return operations.create_purchase(db, payload, 1, 1, 1, payload.user_phone)


def refund(db, tx, **overrides):
    values = dict(full_refund=True, request_id=uuid4())
    values.update(overrides)
    return operations.refund_purchase(db, tx.id, TransactionRefund(**values), [1, 3], 1, 1)


def seed_points(db, user_id, amount):
    db.add(BonusGrant(user_id=user_id, tenant_id=1, amount=amount, remaining=amount,
                      source="test", status="available", available_from=_now(),
                      expires_at=_now() + timedelta(days=100)))
    db.commit()


def test_manual_percent_uses_net_base_and_records_audit(db):
    _, user, _, _ = purchase(db, amount=1, manual_percent=0)
    seed_points(db, user.id, 10000)
    tx, user, balances, _ = purchase(db, amount=250000, redeem_points=10000, manual_percent="5")
    assert tx.earn_base_amount == 240000
    assert tx.earned_points == 12000
    assert tx.earn_percent == Decimal("5")
    assert tx.earning_mode == "manual"
    assert tx.created_by_id == 1
    assert balances["available"] == 12000


@pytest.mark.parametrize("percent,expected", [("0", 0), ("100", 333), ("2.75", 9)])
def test_valid_manual_rates(db, percent, expected):
    tx, _, _, _ = purchase(db, amount=333, manual_percent=percent)
    assert tx.earned_points == expected


@pytest.mark.parametrize("percent", ["-1", "100.01", "2.751", "NaN", "Infinity"])
def test_invalid_manual_rates(percent):
    with pytest.raises(ValueError):
        TransactionCreate(user_phone="77001234567", amount=100, manual_percent=percent)


def test_missing_manual_rate_rolls_back_customer_creation(db):
    with pytest.raises(HTTPException) as error:
        purchase(db, manual_percent=None)
    assert error.value.status_code == 422
    assert db.scalar(select(func.count(User.id))) == 0


def test_automatic_mode_cannot_be_overridden(db):
    settings = db.scalar(select(Settings).where(Settings.tenant_id == 1))
    settings.earning_mode = "automatic"
    settings.earn_bronze_percent = 3
    db.commit()
    with pytest.raises(HTTPException):
        purchase(db, manual_percent="90")
    tx, _, _, _ = purchase(db, manual_percent=None)
    assert tx.earned_points == 30
    assert tx.earn_percent == 3


def test_legacy_settings_update_does_not_disable_manual_mode(db):
    from types import SimpleNamespace
    from app.api.settings_api import update_settings
    from app.schemas.settings_schema import SettingsUpdate
    request = SimpleNamespace(state=SimpleNamespace(user={"role": "owner", "tenant_id": 1, "network_id": 1}))
    update_settings(SettingsUpdate(bonus_name="points"), request, db)
    assert db.scalar(select(Settings).where(Settings.tenant_id == 1)).earning_mode == "manual"
    update_settings(SettingsUpdate(earning_mode="automatic"), request, db)
    assert db.scalar(select(Settings).where(Settings.tenant_id == 1)).earning_mode == "automatic"
    assert db.scalar(select(Settings).where(Settings.tenant_id == 2)).earning_mode == "automatic"


def test_purchase_retry_does_not_duplicate(db):
    key = uuid4()
    tx, _, _, _ = purchase(db, request_id=key)
    retry, _, _, created = purchase(db, request_id=key)
    assert retry.id == tx.id and created is False
    assert db.scalar(select(func.count(Transaction.id))) == 1
    assert db.scalar(select(func.count(BonusGrant.id))) == 1
    with pytest.raises(HTTPException) as error:
        purchase(db, request_id=key, amount=2000)
    assert error.value.status_code == 409


def test_full_refund_uses_original_reward_after_settings_change(db):
    tx, user, _, _ = purchase(db)
    settings = db.scalar(select(Settings).where(Settings.tenant_id == 1))
    settings.earning_mode = "automatic"
    settings.earn_bronze_percent = 90
    db.commit()
    tx, _, balances, record = refund(db, tx)
    assert tx.status == "refunded"
    assert balances["total"] == 0
    assert record.earned_reversed == 100
    assert tx.refunded_earned_points == 100


def test_partial_refunds_remove_rounding_remainder(db):
    tx, user, _, _ = purchase(db, amount=101, manual_percent=3)
    for amount in [33, 33, 35]:
        refund(db, tx, full_refund=False, amount=amount)
    assert tx.refunded_earned_points == tx.earned_points == 3
    assert get_balances(db, user.id)["total"] == 0
    assert db.scalar(select(func.sum(RefundRecord.earned_reversed))) == 3


def test_partial_refunds_restore_all_redeemed_points(db):
    _, user, _, _ = purchase(db, amount=1, manual_percent=0)
    seed_points(db, user.id, 100)
    tx, _, _, _ = purchase(db, amount=201, redeem_points=100, manual_percent=0)
    refund(db, tx, full_refund=False, amount=100)
    refund(db, tx)
    assert tx.refunded_redeem_points == 100
    assert get_balances(db, user.id)["available"] == 100


def test_refund_redeems_and_earning(db):
    _, user, _, _ = purchase(db, amount=1, manual_percent=0)
    seed_points(db, user.id, 100)
    tx, _, balances, _ = purchase(db, amount=100, redeem_points=20)
    assert balances["total"] == 88
    _, _, balances, record = refund(db, tx)
    assert balances["total"] == 100
    assert (record.earned_reversed, record.redeemed_restored) == (8, 20)


def test_refund_retry_does_not_duplicate(db):
    tx, _, _, _ = purchase(db)
    key = uuid4()
    refund(db, tx, request_id=key)
    _, _, _, record = refund(db, tx, request_id=key)
    assert record is None
    assert db.scalar(select(func.count(RefundRecord.id))) == 1
    with pytest.raises(HTTPException) as error:
        refund(db, tx, request_id=key, comment="different request")
    assert error.value.status_code == 409


def test_full_refund_cannot_repeat_with_new_key(db):
    tx, _, _, _ = purchase(db)
    refund(db, tx)
    with pytest.raises(HTTPException) as error:
        refund(db, tx)
    assert error.value.status_code == 409


def test_over_refund_is_rejected_not_silently_clamped(db):
    tx, _, _, _ = purchase(db)
    with pytest.raises(HTTPException) as error:
        refund(db, tx, full_refund=False, amount=1001)
    assert error.value.status_code == 422
    assert db.get(Transaction, tx.id).refunded_amount == 0


def test_spent_bonus_refund_rolls_back_everything(db):
    tx, user, _, _ = purchase(db)
    consume_available(db, user.id, 100)
    with pytest.raises(HTTPException) as error:
        refund(db, tx)
    assert error.value.status_code == 409
    assert db.get(Transaction, tx.id).status == "completed"
    assert db.scalar(select(func.count(RefundRecord.id))) == 0


def test_failed_refund_does_not_leave_restored_points(db):
    _, user, _, _ = purchase(db, amount=1, manual_percent=0)
    seed_points(db, user.id, 20)
    tx, _, _, _ = purchase(db, amount=120, manual_percent=100, redeem_points=20)
    consume_available(db, user.id, 100)
    with pytest.raises(HTTPException):
        refund(db, tx)
    assert db.scalar(select(func.count(BonusGrant.id)).where(BonusGrant.source == "refund_redeem")) == 0
    assert get_balances(db, user.id)["available"] == 0
    assert db.get(Transaction, tx.id).refunded_amount == 0


def test_purchase_failure_does_not_leave_spent_points(db, monkeypatch):
    _, user, _, _ = purchase(db, amount=1, manual_percent=0)
    seed_points(db, user.id, 100)
    def fail(*args, **kwargs):
        raise RuntimeError("simulated reward creation failure")
    monkeypatch.setattr(operations, "grant_purchase_bonus", fail)
    with pytest.raises(RuntimeError):
        purchase(db, redeem_points=100)
    assert get_balances(db, user.id)["available"] == 100
    assert db.scalar(select(func.count(Transaction.id))) == 1


def test_redeem_limits_are_enforced_on_server(db):
    _, user, _, _ = purchase(db, amount=1, manual_percent=0)
    seed_points(db, user.id, 100)
    with pytest.raises(HTTPException) as error:
        purchase(db, amount=1000, redeem_points=101)
    assert error.value.status_code == 409
    settings = db.scalar(select(Settings).where(Settings.tenant_id == 1))
    settings.redeem_max_percent = 10
    db.commit()
    with pytest.raises(HTTPException) as error:
        purchase(db, amount=100, redeem_points=11)
    assert error.value.status_code == 422
    tx, _, _, _ = purchase(db, amount=100, redeem_all=True)
    assert tx.redeem_points == 10


def test_analytics_revenue_deducts_refunds(db):
    from app.services.analytics import _window_stats
    tx, _, _, _ = purchase(db)
    refund(db, tx, full_refund=False, amount=400)
    stats = _window_stats(db, _now() - timedelta(days=1), _now() + timedelta(days=1), [1])
    assert stats["revenue"] == 600


def test_migrations_upgrade_legacy_schema_and_are_repeatable():
    from sqlalchemy import inspect, text
    from app.core.migrations import run_startup_migrations
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for ddl in [
            "CREATE TABLE users (id INTEGER PRIMARY KEY, tenant_id INTEGER)",
            "CREATE TABLE settings (id INTEGER PRIMARY KEY)",
            "CREATE TABLE transactions (id INTEGER PRIMARY KEY, tenant_id INTEGER, paid_amount INTEGER, "
            "earned_points INTEGER, redeem_points INTEGER, refunded_amount INTEGER)",
            "CREATE TABLE bonus_grants (id INTEGER PRIMARY KEY, user_id INTEGER, transaction_id INTEGER)",
            "CREATE TABLE wa_messages (id INTEGER PRIMARY KEY)",
            "CREATE TABLE broadcasts (id INTEGER PRIMARY KEY)",
            "INSERT INTO transactions VALUES (1, 1, 101, 3, 100, 33)",
        ]:
            conn.execute(text(ddl))
    run_startup_migrations(engine)
    run_startup_migrations(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT refunded_earned_points, refunded_redeem_points FROM transactions")).one()
        assert tuple(row) == (0, 32)
    assert "earning_mode" in {c["name"] for c in inspect(engine).get_columns("settings")}
    engine.dispose()


def test_spent_bonus_can_be_recovered_from_available_balance(db):
    tx, user, _, _ = purchase(db)
    consume_available(db, user.id, 100)
    seed_points(db, user.id, 150)
    _, _, balances, _ = refund(db, tx)
    assert balances["available"] == 50


def test_pending_purchase_reward_is_cancelled(db):
    settings = db.scalar(select(Settings).where(Settings.tenant_id == 1))
    settings.activation_days = 7
    db.commit()
    tx, _, balances, _ = purchase(db)
    assert balances["pending"] == 100
    _, _, balances, _ = refund(db, tx)
    assert balances["pending"] == 0


def test_expired_reward_does_not_charge_another_purchase(db):
    tx, user, _, _ = purchase(db)
    grant = db.scalar(select(BonusGrant).where(BonusGrant.transaction_id == tx.id))
    grant.expires_at = _now() - timedelta(days=1)
    db.commit()
    seed_points(db, user.id, 500)
    _, _, balances, _ = refund(db, tx)
    assert balances["available"] == 500


def test_refund_failure_before_commit_is_atomic(db, monkeypatch):
    tx, user, _, _ = purchase(db)
    def fail():
        raise RuntimeError("simulated database failure")
    monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(RuntimeError):
        refund(db, tx)
    assert db.get(Transaction, tx.id).refunded_amount == 0
    assert db.scalar(select(func.count(RefundRecord.id))) == 0
    assert db.scalar(select(BonusGrant.remaining)) == 100


def test_tenant_isolation_and_shared_network_settings(db):
    payload = TransactionCreate(user_phone="77001234567", amount=1000, manual_percent=5)
    tx, _, _, _ = operations.create_purchase(db, payload, 3, 1, 1, payload.user_phone)
    assert tx.tenant_id == 3 and tx.earning_mode == "manual"
    with pytest.raises(HTTPException) as error:
        operations.refund_purchase(db, tx.id, TransactionRefund(full_refund=True), [2], 2, None)
    assert error.value.status_code == 404
    refund(db, tx)


def test_tier_is_recalculated_after_refund(db):
    settings = db.scalar(select(Settings).where(Settings.tenant_id == 1))
    settings.tiers_json = [{"name": "Gold", "spend_from": 500, "bonus_percent": 7}]
    db.commit()
    tx, user, _, _ = purchase(db)
    assert user.tier == "Gold"
    refund(db, tx)
    assert user.tier == "Bronze"


def test_api_roles_and_earning_options(db, monkeypatch):
    from app.api import transactions
    state = {"id": 1, "role": "cashier", "tenant_id": 1, "network_id": 1}
    app = FastAPI()
    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user = state
        return await call_next(request)
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(transactions.router, prefix="/api")
    monkeypatch.setattr(transactions, "_notify", lambda *args: None)
    with TestClient(app) as client:
        assert client.get("/api/transactions/earning-options").json()["earning_mode"] == "manual"
        response = client.post("/api/transactions/", json={
            "user_phone": "77001234567", "amount": 1000, "manual_percent": "5",
        })
        assert response.status_code == 200, response.text
        tx_id = response.json()["id"]
        assert client.post(f"/api/transactions/{tx_id}/refund", json={"full_refund": True}).status_code == 403
        state["role"] = "manager"
        assert client.post(f"/api/transactions/{tx_id}/refund", json={"full_refund": True}).status_code == 200
        history = client.get(f"/api/transactions/{tx_id}/refunds")
        assert history.status_code == 200
        assert history.json()[0]["earned_reversed"] == 50
        state["role"] = "staff"
        assert client.get("/api/transactions/earning-options").status_code == 403


@pytest.fixture
def postgres_engine():
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    url = os.environ.get("LTV_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("LTV_TEST_POSTGRES_URL is needed to test PostgreSQL row locks")
    parsed = make_url(url)
    if not (parsed.database or "").endswith("_test"):
        pytest.fail("Concurrency checks must use a disposable database ending in _test")
    schema = "refund_test_" + uuid4().hex
    root_engine = create_engine(url)
    with root_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = root_engine.execution_options(schema_translate_map={None: schema})
    tables = [Tenant.__table__, AuthUser.__table__, IntegrationKey.__table__, User.__table__, Transaction.__table__,
              Settings.__table__, BonusGrant.__table__, RefundRecord.__table__]
    try:
        Base.metadata.create_all(engine, tables=tables)
        with Session(engine) as session:
            session.add(Tenant(id=1, name="Concurrency"))
            session.add(Settings(tenant_id=1, earning_mode="manual", activation_days=0))
            session.add(AuthUser(id=1, tenant_id=1, name="Test", phone="77000000000",
                                 password_salt="test", password_hash="test"))
            session.commit()
        yield engine
    finally:
        with root_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root_engine.dispose()


@pytest.mark.parametrize("same_request", [True, False])
def test_postgres_parallel_full_refunds(postgres_engine, same_request):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    with Session(postgres_engine, autoflush=False) as session:
        tx, _, _, _ = purchase(session)
        tx_id = tx.id
    barrier = Barrier(2)
    shared_key = uuid4()
    def attempt(index):
        with Session(postgres_engine, autoflush=False) as session:
            payload = TransactionRefund(full_refund=True,
                                        request_id=shared_key if same_request else uuid4())
            barrier.wait(timeout=10)
            try:
                operations.refund_purchase(session, tx_id, payload, [1], 1, 1)
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(attempt, [0, 1]))
    assert statuses == ([200, 200] if same_request else [200, 409])
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count(RefundRecord.id))) == 1
        assert session.get(Transaction, tx_id).refunded_amount == 1000
