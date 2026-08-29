"""
Tests for the money-request flow (POST /requests, approve, decline, list).

Verifies:
1. Creating a money request returns status=pending.
2. Approving triggers a transfer via the shared execute_transfer logic.
3. Double-approve returns 409 (no double-processing).
4. Declining sets status=declined with no transfer.
5. Wrong user gets 403 on approve/decline.
6. Non-existent request returns 404.
7. Listing filters by user_id and only returns pending requests.
8. Insufficient funds on approve returns 400 and leaves request pending.

Requires a running PostgreSQL instance with the schema applied.

    pytest tests/test_money_requests.py -v -s
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


def _get_balance(user_id: uuid.UUID) -> Decimal:
    """Compute a user's balance directly from the DB."""
    db = SessionLocal()
    try:
        result = db.execute(
            text("""
                SELECT COALESCE(
                    SUM(CASE WHEN entry_type = 'credit' THEN amount ELSE -amount END),
                    0
                )
                FROM ledger_entries
                WHERE user_id = :uid
            """),
            {"uid": str(user_id)},
        ).scalar()
        return Decimal(result)
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
def alice_and_bob():
    """Alice (100.00) and Bob (50.00)."""
    alice_id = _seed_user(
        "Alice Req", f"alice-req-{uuid.uuid4()}@test.com", Decimal("100.00")
    )
    bob_id = _seed_user(
        "Bob Req", f"bob-req-{uuid.uuid4()}@test.com", Decimal("50.00")
    )
    yield alice_id, bob_id
    _cleanup_users(alice_id, bob_id)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestMoneyRequests:

    def test_create_request(self, client, alice_and_bob):
        """POST /requests creates a pending money request."""
        alice_id, bob_id = alice_and_bob

        resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "25.00",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["requester_id"] == str(alice_id)
        assert data["target_id"] == str(bob_id)
        assert data["amount"] == "25.00"
        assert data["status"] == "pending"
        print(f"\n[PASS] Created request {data['id']} (pending)")

    def test_create_request_self_rejected(self, client, alice_and_bob):
        """Cannot request money from yourself."""
        alice_id, _ = alice_and_bob

        resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(alice_id),
            "amount": "10.00",
        })
        assert resp.status_code == 400
        print("\n[PASS] Self-request rejected")

    def test_approve_triggers_transfer(self, client, alice_and_bob):
        """
        Approving a request triggers a transfer:
        - target (Bob) pays -> requester (Alice) receives
        - Balances update correctly
        """
        alice_id, bob_id = alice_and_bob

        # Alice requests $20 from Bob
        create_resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "20.00",
        })
        assert create_resp.status_code == 201
        request_id = create_resp.json()["id"]

        # Bob approves
        approve_resp = client.post(f"/requests/{request_id}/approve", json={
            "user_id": str(bob_id),
        })
        assert approve_resp.status_code == 200
        data = approve_resp.json()

        # Request is now approved
        assert data["status"] == "approved"

        # Balances correct: Bob paid $20 to Alice
        alice_balance = _get_balance(alice_id)
        bob_balance = _get_balance(bob_id)
        assert alice_balance == Decimal("120.00")
        assert bob_balance == Decimal("30.00")

        print(
            f"\n[PASS] Approved request {request_id}. "
            f"Alice={alice_balance}, Bob={bob_balance}"
        )

    def test_double_approve_returns_409(self, client, alice_and_bob):
        """Approving an already-approved request returns 409."""
        alice_id, bob_id = alice_and_bob

        create_resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "10.00",
        })
        request_id = create_resp.json()["id"]

        # First approval succeeds
        resp1 = client.post(f"/requests/{request_id}/approve", json={
            "user_id": str(bob_id),
        })
        assert resp1.status_code == 200

        # Second approval -> 409
        resp2 = client.post(f"/requests/{request_id}/approve", json={
            "user_id": str(bob_id),
        })
        assert resp2.status_code == 409
        assert "already" in resp2.json()["detail"].lower()

        # Balance only debited once
        bob_balance = _get_balance(bob_id)
        assert bob_balance == Decimal("40.00")

        print(f"\n[PASS] Double-approve blocked with 409. Bob={bob_balance}")

    def test_decline_sets_status(self, client, alice_and_bob):
        """Declining sets status=declined, no transfer happens."""
        alice_id, bob_id = alice_and_bob

        create_resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "30.00",
        })
        request_id = create_resp.json()["id"]

        # Bob declines
        decline_resp = client.post(f"/requests/{request_id}/decline", json={
            "user_id": str(bob_id),
        })
        assert decline_resp.status_code == 200
        assert decline_resp.json()["status"] == "declined"

        # Balances unchanged
        alice_balance = _get_balance(alice_id)
        bob_balance = _get_balance(bob_id)
        assert alice_balance == Decimal("100.00")
        assert bob_balance == Decimal("50.00")

        print(f"\n[PASS] Declined. Balances unchanged: Alice={alice_balance}, Bob={bob_balance}")

    def test_double_decline_returns_409(self, client, alice_and_bob):
        """Declining an already-declined request returns 409."""
        alice_id, bob_id = alice_and_bob

        create_resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "15.00",
        })
        request_id = create_resp.json()["id"]

        client.post(f"/requests/{request_id}/decline", json={
            "user_id": str(bob_id),
        })

        resp2 = client.post(f"/requests/{request_id}/decline", json={
            "user_id": str(bob_id),
        })
        assert resp2.status_code == 409
        print("\n[PASS] Double-decline blocked with 409")

    def test_wrong_user_approve_returns_403(self, client, alice_and_bob):
        """Only target_id can approve."""
        alice_id, bob_id = alice_and_bob

        create_resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "10.00",
        })
        request_id = create_resp.json()["id"]

        # Alice (requester) tries to approve -> 403
        resp = client.post(f"/requests/{request_id}/approve", json={
            "user_id": str(alice_id),
        })
        assert resp.status_code == 403
        print("\n[PASS] Wrong user blocked with 403 on approve")

    def test_wrong_user_decline_returns_403(self, client, alice_and_bob):
        """Only target_id can decline."""
        alice_id, bob_id = alice_and_bob

        create_resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "10.00",
        })
        request_id = create_resp.json()["id"]

        resp = client.post(f"/requests/{request_id}/decline", json={
            "user_id": str(alice_id),
        })
        assert resp.status_code == 403
        print("\n[PASS] Wrong user blocked with 403 on decline")

    def test_nonexistent_request_returns_404(self, client):
        """Approve/decline on a non-existent request returns 404."""
        fake_id = str(uuid.uuid4())
        fake_user = str(uuid.uuid4())

        resp_approve = client.post(f"/requests/{fake_id}/approve", json={
            "user_id": fake_user,
        })
        assert resp_approve.status_code == 404

        resp_decline = client.post(f"/requests/{fake_id}/decline", json={
            "user_id": fake_user,
        })
        assert resp_decline.status_code == 404

        print("\n[PASS] Non-existent request returns 404")

    def test_list_pending_requests(self, client, alice_and_bob):
        """GET /requests?user_id=... returns only pending requests."""
        alice_id, bob_id = alice_and_bob

        # Create 3 requests: 2 will stay pending, 1 will be declined
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
        r3 = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "30.00",
        }).json()

        # Decline r3
        client.post(f"/requests/{r3['id']}/decline", json={
            "user_id": str(bob_id),
        })

        # List for Bob (target) -- should see 2 pending
        resp_bob = client.get(f"/requests?user_id={bob_id}")
        assert resp_bob.status_code == 200
        bob_requests = resp_bob.json()
        assert len(bob_requests) == 2
        assert all(r["status"] == "pending" for r in bob_requests)

        # List for Alice (requester) -- should also see same 2 pending
        resp_alice = client.get(f"/requests?user_id={alice_id}")
        assert resp_alice.status_code == 200
        alice_requests = resp_alice.json()
        assert len(alice_requests) == 2

        print(f"\n[PASS] Listed {len(bob_requests)} pending requests for Bob")

    def test_approve_insufficient_funds_returns_400(self, client, alice_and_bob):
        """
        If the target doesn't have enough funds, approve returns 400
        and the request stays pending.
        """
        alice_id, bob_id = alice_and_bob

        # Alice requests $999 from Bob (Bob only has $50)
        create_resp = client.post("/requests", json={
            "requester_id": str(alice_id),
            "target_id": str(bob_id),
            "amount": "999.00",
        })
        request_id = create_resp.json()["id"]

        resp = client.post(f"/requests/{request_id}/approve", json={
            "user_id": str(bob_id),
        })
        assert resp.status_code == 400
        assert "insufficient funds" in resp.json()["detail"].lower()

        # Request should still be pending (not approved, not failed)
        list_resp = client.get(f"/requests?user_id={bob_id}")
        pending = [r for r in list_resp.json() if r["id"] == request_id]
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"

        # Balances unchanged
        bob_balance = _get_balance(bob_id)
        assert bob_balance == Decimal("50.00")

        print(f"\n[PASS] Insufficient funds on approve -> 400, request still pending")
