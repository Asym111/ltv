import hashlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import integration, integration_keys
from app.core import integration_auth
from app.core.database import get_db
from app.models.auth import AuthUser, Tenant
from app.models.integration_key import IntegrationKey
from app.models.refund import RefundRecord
from app.models.transaction import Transaction
from app.models.user import User
from test.test_transaction_operations import db


PREFIX = "/api/integration/v1"
MANAGE = "/api/accounts/integration-keys"
ALL_SCOPES = ["balance:read", "transactions:read", "transactions:write", "refunds:write"]


@pytest.fixture
def api(db, monkeypatch):
    state = {"id": 1, "role": "owner", "tenant_id": 1, "network_id": 1}
    app = FastAPI()
    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user = state
        return await call_next(request)
    app.dependency_overrides[get_db] = lambda: db
    app.include_router(integration.router)
    app.include_router(integration_keys.router, prefix="/api")
    monkeypatch.setattr(integration, "queue_message", lambda *args: None)
    with TestClient(app) as client:
        yield client, state


def issue(api, **overrides):
    client, _ = api
    payload = dict(name="Lurea Apps Script", scopes=ALL_SCOPES)
    payload.update(overrides)
    response = client.post(MANAGE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def headers(key):
    return {"Authorization": "Bearer " + key["token"]}


def buy(client, key, **overrides):
    payload = dict(external_id="RCP-001", request_id=str(uuid4()), phone="+7 (700) 123-45-67",
                   amount=250000, manual_percent="5", payment_method="CARD")
    payload.update(overrides)
    return client.post(PREFIX + "/transactions", headers=headers(key), json=payload)


def refund(client, key, tx_id, **overrides):
    payload = dict(external_id="REF-001", request_id=str(uuid4()), full_refund=True)
    payload.update(overrides)
    return client.post(f"{PREFIX}/transactions/{tx_id}/refunds", headers=headers(key), json=payload)


def test_only_hash_is_stored_and_secret_is_returned_once(api, db):
    key = issue(api)
    assert integration_auth.TOKEN_PATTERN.fullmatch(key["token"])
    row = db.get(IntegrationKey, key["key"]["id"])
    assert row.token_hash == hashlib.sha256(key["token"].encode()).hexdigest()
    listed = api[0].get(MANAGE)
    assert listed.headers["Cache-Control"] == "no-store"
    assert key["token"] not in listed.text and row.token_hash not in listed.text
    assert "token" not in listed.json()[0]


@pytest.mark.parametrize("role", ["admin", "manager", "cashier", "staff"])
def test_key_management_is_owner_only(api, role):
    api[1]["role"] = role
    assert api[0].get(MANAGE).status_code == 403
    assert api[0].post(MANAGE, json={"name": "bad"}).status_code == 403
    assert api[0].delete(MANAGE + "/1").status_code == 403


def test_owner_cannot_issue_or_revoke_key_for_another_organization(api):
    client, state = api
    key = issue(api)
    assert client.post(MANAGE, json={"name": "Other", "tenant_id": 2}).status_code == 403
    state.update(id=2, tenant_id=2, network_id=2)
    assert client.get(MANAGE).json() == []
    assert client.delete(f"{MANAGE}/{key['key']['id']}").status_code == 404


@pytest.mark.parametrize("authorization", [None, "Basic test", "Bearer invalid", "Bearer default"])
def test_external_endpoints_require_bearer_not_cookie(api, authorization):
    client, _ = api
    h = {"Authorization": authorization} if authorization else {}
    assert client.get(PREFIX + "/me", headers=h).status_code == 401
    assert client.post(PREFIX + "/balance", headers=h, json={"phone": "77001234567"}).status_code == 401


def test_wrong_token_secret_is_rejected(api):
    key = issue(api)
    last = "a" if key["token"][-1] != "a" else "b"
    assert api[0].get(PREFIX + "/me", headers={"Authorization": "Bearer " + key["token"][:-1] + last}).status_code == 401


def test_revoked_and_expired_keys_are_rejected(api, db):
    client, _ = api
    key = issue(api)
    assert client.get(PREFIX + "/me", headers=headers(key)).status_code == 200
    assert client.delete(f"{MANAGE}/{key['key']['id']}").status_code == 200
    assert client.get(PREFIX + "/me", headers=headers(key)).status_code == 401
    key = issue(api)
    db.get(IntegrationKey, key["key"]["id"]).expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get(PREFIX + "/me", headers=headers(key)).status_code == 401


def test_disabled_or_expired_organization_is_rejected(api, db):
    key = issue(api)
    tenant = db.get(Tenant, 1)
    tenant.is_active = False
    db.commit()
    assert api[0].get(PREFIX + "/me", headers=headers(key)).status_code == 403
    tenant.is_active = True
    tenant.access_until = datetime.utcnow() - timedelta(days=1)
    db.commit()
    assert api[0].get(PREFIX + "/me", headers=headers(key)).status_code == 403


def test_read_only_key_cannot_buy_or_refund(api, db):
    client, _ = api
    key = issue(api, scopes=["balance:read"])
    assert buy(client, key).status_code == 403
    assert refund(client, key, 1).status_code == 403
    assert client.get(PREFIX + "/transactions/1", headers=headers(key)).status_code == 403
    assert db.scalar(select(func.count(Transaction.id))) == 0


def test_purchase_balance_and_retry_are_consistent(api, db):
    client, _ = api
    key = issue(api)
    response = buy(client, key)
    assert response.status_code == 200, response.text
    tx = response.json()
    assert (tx["earned_points"], tx["cash_amount"], tx["replayed"]) == (12500, 250000, False)
    retry = buy(client, key)
    assert retry.status_code == 200 and retry.json()["replayed"] is True
    assert retry.json()["id"] == tx["id"]
    assert db.scalar(select(func.count(Transaction.id))) == 1
    stored = db.get(Transaction, tx["id"])
    assert stored.integration_key_id == key["key"]["id"] and stored.created_by_id is None
    balance = client.post(PREFIX + "/balance", headers=headers(key), json={"phone": "87001234567", "amount": 100000})
    assert balance.json()["available"] == balance.json()["max_redeem"] == 12500
    found = client.get(PREFIX + "/transactions/by-external/RCP-001", headers=headers(key))
    assert found.json()["id"] == tx["id"]
    assert buy(client, key, amount=50000).status_code == 409


def test_api_cannot_override_tenant_or_earned_points(api):
    client, _ = api
    key = issue(api)
    assert buy(client, key, tenant_id=2).status_code == 422
    assert buy(client, key, earned_points=90000).status_code == 422
    assert buy(client, key, paid_amount=100).status_code == 422
    assert client.post(PREFIX + "/balance", headers=headers(key), json={"phone": "77001234567", "tenant_id": 2}).status_code == 422


def test_other_network_cannot_read_balance_or_transaction(api):
    client, state = api
    lurea = issue(api)
    tx = buy(client, lurea).json()
    state.update(id=2, tenant_id=2, network_id=2)
    other = issue(api)
    assert client.get(f"{PREFIX}/transactions/{tx['id']}", headers=headers(other)).status_code == 404
    assert refund(client, other, tx["id"]).status_code == 404
    balance = client.post(PREFIX + "/balance", headers=headers(other), json={"phone": "77001234567"})
    assert balance.json()["found"] is False and balance.json()["total"] == 0


def test_branch_key_is_pinned_to_branch(api):
    client, _ = api
    root = issue(api)
    branch = issue(api, tenant_id=3)
    tx = buy(client, branch).json()
    assert client.get(f"{PREFIX}/transactions/{tx['id']}", headers=headers(root)).status_code == 404
    assert client.get(f"{PREFIX}/transactions/{tx['id']}", headers=headers(branch)).status_code == 200
    assert refund(client, root, tx["id"]).status_code == 404


def test_refund_is_idempotent_and_external_id_is_unique(api, db):
    client, _ = api
    key = issue(api)
    tx = buy(client, key).json()
    response = refund(client, key, tx["id"])
    assert response.status_code == 200, response.text
    assert response.json()["refund"]["earned_reversed"] == 12500
    assert response.json()["transaction"]["status"] == "refunded"
    retry = refund(client, key, tx["id"])
    assert retry.status_code == 200 and retry.json()["replayed"] is True
    assert db.scalar(select(func.count(RefundRecord.id))) == 1
    tx2 = buy(client, key, external_id="RCP-002").json()
    assert refund(client, key, tx2["id"]).status_code == 409
    assert refund(client, key, tx["id"], external_id="REF-002").status_code == 409


def test_partial_refund_and_reused_request_with_different_payload(api):
    client, _ = api
    key = issue(api)
    tx = buy(client, key).json()
    request_id = str(uuid4())
    partial = refund(client, key, tx["id"], request_id=request_id, amount=50000, full_refund=False)
    assert partial.status_code == 200 and partial.json()["transaction"]["refunded_amount"] == 50000
    assert refund(client, key, tx["id"], request_id=request_id, amount=60000, full_refund=False).status_code == 409
    full = refund(client, key, tx["id"], external_id="REF-002")
    assert full.status_code == 200 and full.json()["transaction"]["refunded_earned_points"] == 12500


def test_required_ids_manual_rate_and_invalid_phones(api):
    client, _ = api
    key = issue(api)
    assert buy(client, key, request_id=None).status_code == 422
    assert buy(client, key, external_id="").status_code == 422
    assert buy(client, key, manual_percent=None).status_code == 422
    assert buy(client, key, manual_percent=101).status_code == 422
    assert buy(client, key, phone="1234567890123").status_code == 422
    assert buy(client, key, manual_percent="0").json()["earned_points"] == 0


def test_rate_limit_is_per_key_and_database_backed(api, db, monkeypatch):
    client, _ = api
    key = issue(api)
    now = datetime.utcnow()
    monkeypatch.setattr(integration_auth, "datetime", SimpleNamespace(utcnow=lambda: now))
    stored = db.get(IntegrationKey, key["key"]["id"])
    stored.usage_window = now.replace(second=0, microsecond=0)
    stored.usage_count = integration_auth.RATE_LIMIT
    db.commit()
    response = client.get(PREFIX + "/me", headers=headers(key))
    assert response.status_code == 429 and "Retry-After" in response.headers
    key2 = issue(api)
    assert client.get(PREFIX + "/me", headers=headers(key2)).status_code == 200


def test_only_exact_integration_namespace_bypasses_cookie_guard():
    assert integration_auth.is_integration_path(PREFIX + "/balance")
    assert not integration_auth.is_integration_path(PREFIX + "0/balance")
    assert not integration_auth.is_integration_path("/api/accounts/integration-keys")
    assert not integration_auth.is_integration_path("/api/settings/")


def test_stale_owner_session_cannot_issue_keys(api, db):
    db.get(AuthUser, 1).role = "cashier"
    db.commit()
    assert api[0].post(MANAGE, json={"name": "bad"}).status_code == 403


def test_key_expiry_and_scope_validation(api):
    client, _ = api
    assert client.post(MANAGE, json={"name": "bad", "expires_in_days": 0}).status_code == 422
    assert client.post(MANAGE, json={"name": "bad", "scopes": ["settings:write"]}).status_code == 422
    assert client.post(MANAGE, json={"name": "  "}).status_code == 422


def test_bearer_identity_is_independent_of_browser_account(api):
    key = issue(api)
    api[1].update(id=2, role="owner", tenant_id=2, network_id=2)
    response = api[0].get(PREFIX + "/me", headers=headers(key))
    assert response.status_code == 200 and response.json()["tenant_id"] == 1


def test_branch_key_stops_working_when_branch_moves_to_another_network(api, db):
    key = issue(api, tenant_id=3)
    assert api[0].get(PREFIX + "/me", headers=headers(key)).status_code == 200
    db.get(Tenant, 3).parent_tenant_id = 2
    db.commit()
    assert api[0].get(PREFIX + "/me", headers=headers(key)).status_code == 403
