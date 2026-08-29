"""
Tests for transaction history and balance endpoints.

Verifies:
1. GET /users/{user_id}/balance returns correct computed balance.
2. GET /users/{user_id}/transactions returns joined, shaped items.
3. type=sent filters to debits only.
4. type=received filters to credits only.
5. Pagination (limit/offset) works correctly.
6. Counterparty name is resolved server-side.
7. 404 for non-existent user.
8. GET /requests?user_id=...&status=... filter works.

    pytest tests/test_transactions.py -v -s
"""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.models import EntryType, LedgerEntry, User
from main import app


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _seed_user(name: str, email: str, initial_balance: Decimal) -> uuid.UUID:
    """Create a user with an initial balance."""
    db = SessionLocal()
    try:
        user = User(name=name, email=email)
        db.add(user)
        db.flush()

        if initial_balance > 0:
            from app.models import Transfer, TransferStatus
            seed_transfer = Transfer(
                sender_id=user.id,
                receiver_id=user.id,
                amount=initial_balance,
                status=TransferStatus.completed,
                idempotency_key=f"seed-{user.id}",
            )
            db.add(seed_transfer)
            db.flush()

            seed_entry = LedgerEntry(
                user_id=user.id,
                transfer_id=seed_transfer.id,
                entry_type=EntryType.credit,
                amount=initial_balance,
            )
            db.add(seed_entry)

        db.commit()
        return user.id
    finally:
        db.close()


def _cleanup_users(*user_ids: uuid.UUID):
    """Remove test data in correct FK order."""
    db = SessionLocal()
    try:
        for uid in user_ids:
            db.execute(
                text("DELETE FROM ledger_entries WHERE user_id = :uid"),
                {"uid": str(uid)},
            )
        for uid in user_ids:
            db.execute(
                text(
                    "DELETE FROM transfers "
                    "WHERE sender_id = :uid OR receiver_id = :uid"
                ),
                {"uid": str(uid)},
            )
        for uid in user_ids:
            db.execute(
                text(
                    "DELETE FROM money_requests "
                    "WHERE requester_id = :uid OR target_id = :uid"
                ),
                {"uid": str(uid)},
            )
        for uid in user_ids:
            db.execute(
                text("DELETE FROM users WHERE id = :uid"),
                {"uid": str(uid)},
            )
        db.commit()
    finally:
        db.close()


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def alice_and_bob_with_transfers(client):
    """
    Seed Alice (100) and Bob (50), then execute two transfers:
      - Alice sends 30 to Bob
      - Bob sends 10 to Alice
    Final: Alice=80, Bob=70
    """
    alice_id = _seed_user(
        "Alice Txn", f"alice-txn-{uuid.uuid4()}@test.com", Decimal("100.00")
    )
    bob_id = _seed_user(
        "Bob Txn", f"bob-txn-{uuid.uuid4()}@test.com", Decimal("50.00")
    )

    # Transfer 1: Alice -> Bob $30
    client.post("/transfers", json={
        "sender_id": str(alice_id),
        "receiver_id": str(bob_id),
        "amount": "30.00",
        "idempotency_key": f"txn-test-1-{uuid.uuid4()}",
    })

    # Transfer 2: Bob -> Alice $10
    client.post("/transfers", json={
        "sender_id": str(bob_id),
        "receiver_id": str(alice_id),
        "amount": "10.00",
        "idempotency_key": f"txn-test-2-{uuid.uuid4()}",
    })

    yield alice_id, bob_id
    _cleanup_users(alice_id, bob_id)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestBalance:

    def test_balance_after_transfers(self, client, alice_and_bob_with_transfers):
        """Balance endpoint returns correct computed value."""
        alice_id, bob_id = alice_and_bob_with_transfers

        resp_alice = client.get(f"/users/{alice_id}/balance")
        assert resp_alice.status_code == 200
        assert resp_alice.json()["balance"] == "80.00"

        resp_bob = client.get(f"/users/{bob_id}/balance")
        assert resp_bob.status_code == 200
        assert resp_bob.json()["balance"] == "70.00"

        print(f"\n[PASS] Alice={resp_alice.json()['balance']}, Bob={resp_bob.json()['balance']}")

    def test_balance_nonexistent_user(self, client):
        """404 for non-existent user."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/users/{fake_id}/balance")
        assert resp.status_code == 404
        print("\n[PASS] Balance 404 for non-existent user")


class TestTransactionHistory:

    def test_all_transactions(self, client, alice_and_bob_with_transfers):
        """
        Alice has:
          - seed credit (from seed transfer)
          - debit $30 (sent to Bob)
          - credit $10 (received from Bob)
        = 3 entries total (including the seed)
        """
        alice_id, bob_id = alice_and_bob_with_transfers

        resp = client.get(f"/users/{alice_id}/transactions")
        assert resp.status_code == 200
        data = resp.json()

        # Should have items (seed + 2 transfers)
        assert data["total"] >= 2
        assert len(data["items"]) == data["total"]

        # Most recent first
        timestamps = [item["timestamp"] for item in data["items"]]
        assert timestamps == sorted(timestamps, reverse=True)

        print(f"\n[PASS] All transactions: {data['total']} items, most-recent-first")

    def test_filter_sent(self, client, alice_and_bob_with_transfers):
        """type=sent returns only debit entries."""
        alice_id, bob_id = alice_and_bob_with_transfers

        resp = client.get(f"/users/{alice_id}/transactions?type=sent")
        assert resp.status_code == 200
        data = resp.json()

        # Alice sent one transfer ($30 to Bob)
        assert data["total"] == 1
        item = data["items"][0]
        assert item["direction"] == "sent"
        assert item["amount"] == "30.00"
        assert item["counterparty_id"] == str(bob_id)
        assert item["counterparty_name"] == "Bob Txn"

        print(f"\n[PASS] Sent filter: {data['total']} debit(s)")

    def test_filter_received(self, client, alice_and_bob_with_transfers):
        """type=received returns only credit entries."""
        alice_id, bob_id = alice_and_bob_with_transfers

        resp = client.get(f"/users/{alice_id}/transactions?type=received")
        assert resp.status_code == 200
        data = resp.json()

        # Alice received: seed credit + $10 from Bob = 2 credits
        assert data["total"] == 2
        assert all(item["direction"] == "received" for item in data["items"])

        print(f"\n[PASS] Received filter: {data['total']} credit(s)")

    def test_counterparty_resolved(self, client, alice_and_bob_with_transfers):
        """Counterparty name is resolved server-side."""
        alice_id, bob_id = alice_and_bob_with_transfers

        resp = client.get(f"/users/{alice_id}/transactions?type=sent")
        data = resp.json()
        item = data["items"][0]

        assert item["counterparty_name"] == "Bob Txn"
        assert item["counterparty_id"] == str(bob_id)

        print(f"\n[PASS] Counterparty resolved: {item['counterparty_name']}")

    def test_pagination(self, client, alice_and_bob_with_transfers):
        """Pagination with limit and offset."""
        alice_id, _ = alice_and_bob_with_transfers

        # Get first item only
        resp1 = client.get(f"/users/{alice_id}/transactions?limit=1&offset=0")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["items"]) == 1
        assert data1["limit"] == 1
        assert data1["offset"] == 0
        total = data1["total"]

        # Get second item
        resp2 = client.get(f"/users/{alice_id}/transactions?limit=1&offset=1")
        data2 = resp2.json()
        assert len(data2["items"]) == 1
        assert data2["offset"] == 1

        # Different items
        assert data1["items"][0]["transfer_id"] != data2["items"][0]["transfer_id"]

        print(f"\n[PASS] Pagination: total={total}, page1 != page2")

    def test_transactions_nonexistent_user(self, client):
        """404 for non-existent user."""
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/users/{fake_id}/transactions")
        assert resp.status_code == 404
        print("\n[PASS] Transactions 404 for non-existent user")

    def test_limit_capped_at_100(self, client, alice_and_bob_with_transfers):
        """Limit query param is capped at 100."""
        alice_id, _ = alice_and_bob_with_transfers
        resp = client.get(f"/users/{alice_id}/transactions?limit=200")
        # FastAPI validation rejects limit > 100
        assert resp.status_code == 422
        print("\n[PASS] limit=200 rejected with 422")


class TestRequestStatusFilter:

    def test_filter_requests_by_status(self, client):
        """GET /requests?user_id=...&status=... filters correctly."""
        alice_id = _seed_user(
            "Alice Filt", f"alice-filt-{uuid.uuid4()}@test.com", Decimal("100.00")
        )
        bob_id = _seed_user(
            "Bob Filt", f"bob-filt-{uuid.uuid4()}@test.com", Decimal("50.00")
        )

        try:
            # Create 2 requests, decline one
            r1 = client.post("/requests", json={
                "requester_id": str(alice_id),
                "target_id": str(bob_id),
                "amount": "10.00",
            }).json()
            r2 = client.post("/requests", json={
                "requester_id": str(alice_id),
                "target_id": str(bob_id),
                "amount": "20.00",
            }).json()

            client.post(f"/requests/{r2['id']}/decline", json={
                "user_id": str(bob_id),
            })

            # Default (pending) -- should see 1
            resp_pending = client.get(f"/requests?user_id={bob_id}")
            assert resp_pending.status_code == 200
            assert len(resp_pending.json()) == 1
            assert resp_pending.json()[0]["status"] == "pending"

            # Explicit status=declined -- should see 1
            resp_declined = client.get(f"/requests?user_id={bob_id}&status=declined")
            assert resp_declined.status_code == 200
            assert len(resp_declined.json()) == 1
            assert resp_declined.json()[0]["status"] == "declined"

            print("\n[PASS] Request status filter works: pending=1, declined=1")
        finally:
            _cleanup_users(alice_id, bob_id)
