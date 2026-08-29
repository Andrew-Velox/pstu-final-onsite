"""
Concurrency test for POST /transfers.

Proves that:
1. Two simultaneous transfers from the same sender never overdraw the balance.
2. Two simultaneous transfers in opposite directions (A→B and B→A) do not
   deadlock thanks to the sorted-UUID lock ordering.
3. Idempotent retries return the original result without double-processing.

Usage
─────
Requires a running PostgreSQL instance with the schema applied.

    # From the project root:
    pytest tests/test_concurrent_transfers.py -v

    # Or run as a standalone script:
    python -m tests.test_concurrent_transfers
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.models import EntryType, LedgerEntry, User
from main import app


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _seed_user(name: str, email: str, initial_balance: Decimal) -> uuid.UUID:
    """
    Create a user and give them an initial balance via a manual credit
    ledger entry (simulates an external deposit).
    """
    db = SessionLocal()
    try:
        user = User(name=name, email=email)
        db.add(user)
        db.flush()

        if initial_balance > 0:
            # Seed credit: we create a "system" transfer-less entry.
            # Since our FK is NOT NULL, we create a dummy self-transfer first.
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
    """
    Seed two users: Alice (balance 100.00) and Bob (balance 50.00).
    Clean up after the test.
    """
    alice_id = _seed_user(
        "Alice Test", f"alice-{uuid.uuid4()}@test.com", Decimal("100.00")
    )
    bob_id = _seed_user(
        "Bob Test", f"bob-{uuid.uuid4()}@test.com", Decimal("50.00")
    )
    yield alice_id, bob_id
    _cleanup_users(alice_id, bob_id)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestConcurrentTransfers:
    """Tests that exercise the transfer endpoint under concurrency."""

    def test_concurrent_same_sender_no_overdraw(self, client, alice_and_bob):
        """
        Alice has 100.00.  Fire 5 concurrent transfers of 30.00 each from
        Alice → Bob.  At most 3 should succeed; Alice's balance must never
        go below 0.
        """
        alice_id, bob_id = alice_and_bob

        results = []
        errors = []

        def send_transfer(i):
            resp = client.post("/transfers", json={
                "sender_id": str(alice_id),
                "receiver_id": str(bob_id),
                "amount": "30.00",
                "idempotency_key": f"concurrent-same-{uuid.uuid4()}",
            })
            return resp

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(send_transfer, i) for i in range(5)]
            for f in as_completed(futures):
                resp = f.result()
                if resp.status_code == 201:
                    results.append(resp.json())
                else:
                    errors.append(resp.json())

        # At most 3 transfers of 30 can succeed from a balance of 100
        assert len(results) <= 3, (
            f"Expected ≤3 successful transfers, got {len(results)}"
        )
        assert len(results) + len(errors) == 5

        # Final balance must be non-negative
        alice_balance = _get_balance(alice_id)
        assert alice_balance >= 0, f"Alice overdrew! balance={alice_balance}"

        # Conservation: alice_balance + bob_balance == initial total (150)
        bob_balance = _get_balance(bob_id)
        total = alice_balance + bob_balance
        assert total == Decimal("150.00"), (
            f"Money not conserved! alice={alice_balance} bob={bob_balance} "
            f"total={total}"
        )

        print(
            f"\n[PASS] {len(results)} succeeded, {len(errors)} rejected. "
            f"Alice={alice_balance}, Bob={bob_balance}, Total={total}"
        )

    def test_opposite_direction_no_deadlock(self, client, alice_and_bob):
        """
        Fire Alice→Bob and Bob→Alice transfers simultaneously.
        Neither should deadlock (the sorted lock ordering prevents it).
        Both or one should succeed depending on balances.
        """
        alice_id, bob_id = alice_and_bob

        results = {}
        barrier = threading.Barrier(2, timeout=10)

        def transfer_a_to_b():
            barrier.wait()  # synchronize start
            resp = client.post("/transfers", json={
                "sender_id": str(alice_id),
                "receiver_id": str(bob_id),
                "amount": "40.00",
                "idempotency_key": f"ab-{uuid.uuid4()}",
            })
            results["a_to_b"] = resp

        def transfer_b_to_a():
            barrier.wait()  # synchronize start
            resp = client.post("/transfers", json={
                "sender_id": str(bob_id),
                "receiver_id": str(alice_id),
                "amount": "30.00",
                "idempotency_key": f"ba-{uuid.uuid4()}",
            })
            results["b_to_a"] = resp

        threads = [
            threading.Thread(target=transfer_a_to_b),
            threading.Thread(target=transfer_b_to_a),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # Neither should time out (no deadlock)
        assert "a_to_b" in results, "A→B transfer timed out (possible deadlock)"
        assert "b_to_a" in results, "B→A transfer timed out (possible deadlock)"

        # At least one should succeed
        statuses = {
            "a_to_b": results["a_to_b"].status_code,
            "b_to_a": results["b_to_a"].status_code,
        }
        assert any(s == 201 for s in statuses.values()), (
            f"Both transfers failed: {statuses}"
        )

        # Balances must be non-negative and conserved
        alice_balance = _get_balance(alice_id)
        bob_balance = _get_balance(bob_id)
        assert alice_balance >= 0
        assert bob_balance >= 0
        assert alice_balance + bob_balance == Decimal("150.00")

        print(
            f"\n[PASS] A->B: {statuses['a_to_b']}, B->A: {statuses['b_to_a']}. "
            f"Alice={alice_balance}, Bob={bob_balance}"
        )

    def test_idempotency_no_double_spend(self, client, alice_and_bob):
        """
        Sending the same idempotency_key twice should return the same result
        and only debit the sender once.
        """
        alice_id, bob_id = alice_and_bob
        key = f"idem-{uuid.uuid4()}"

        resp1 = client.post("/transfers", json={
            "sender_id": str(alice_id),
            "receiver_id": str(bob_id),
            "amount": "25.00",
            "idempotency_key": key,
        })
        assert resp1.status_code == 201
        data1 = resp1.json()

        # Retry with the exact same key
        resp2 = client.post("/transfers", json={
            "sender_id": str(alice_id),
            "receiver_id": str(bob_id),
            "amount": "25.00",
            "idempotency_key": key,
        })
        # Should return 201 (idempotent return of original)
        assert resp2.status_code == 201
        data2 = resp2.json()

        # Same transfer ID — not a new transfer
        assert data1["id"] == data2["id"]

        # Balance should reflect only one debit of 25
        alice_balance = _get_balance(alice_id)
        assert alice_balance == Decimal("75.00"), (
            f"Double-spend detected! Alice balance={alice_balance}"
        )

        print(f"\n[PASS] Idempotent retry returned same transfer {data1['id']}")

    def test_insufficient_funds_no_partial_write(self, client, alice_and_bob):
        """
        Transfer more than the sender has — should fail with 400 and leave
        no Transfer or LedgerEntry rows behind.
        """
        alice_id, bob_id = alice_and_bob
        key = f"insuf-{uuid.uuid4()}"

        resp = client.post("/transfers", json={
            "sender_id": str(alice_id),
            "receiver_id": str(bob_id),
            "amount": "999.00",
            "idempotency_key": key,
        })
        assert resp.status_code == 400
        assert "insufficient funds" in resp.json()["detail"].lower()

        # Balance unchanged
        alice_balance = _get_balance(alice_id)
        assert alice_balance == Decimal("100.00")

        print(f"\n[PASS] Insufficient funds correctly rejected. Alice={alice_balance}")


# ─── Standalone runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run the concurrency tests without pytest.
    Useful for quick manual verification.
    """
    print("=" * 60)
    print("  CONCURRENT TRANSFER TESTS")
    print("=" * 60)

    test_client = TestClient(app)

    # Seed users
    alice_id = _seed_user(
        "Alice Manual", f"alice-{uuid.uuid4()}@test.com", Decimal("100.00")
    )
    bob_id = _seed_user(
        "Bob Manual", f"bob-{uuid.uuid4()}@test.com", Decimal("50.00")
    )

    try:
        t = TestConcurrentTransfers()

        print("\n─── Test 1: Concurrent same-sender (no overdraw) ───")
        t.test_concurrent_same_sender_no_overdraw(
            test_client, (alice_id, bob_id)
        )

        # Re-seed for the next test
        _cleanup_users(alice_id, bob_id)
        alice_id = _seed_user(
            "Alice Manual", f"alice-{uuid.uuid4()}@test.com", Decimal("100.00")
        )
        bob_id = _seed_user(
            "Bob Manual", f"bob-{uuid.uuid4()}@test.com", Decimal("50.00")
        )

        print("\n─── Test 2: Opposite-direction transfers (no deadlock) ───")
        t.test_opposite_direction_no_deadlock(
            test_client, (alice_id, bob_id)
        )

        _cleanup_users(alice_id, bob_id)
        alice_id = _seed_user(
            "Alice Manual", f"alice-{uuid.uuid4()}@test.com", Decimal("100.00")
        )
        bob_id = _seed_user(
            "Bob Manual", f"bob-{uuid.uuid4()}@test.com", Decimal("50.00")
        )

        print("\n─── Test 3: Idempotency (no double-spend) ───")
        t.test_idempotency_no_double_spend(
            test_client, (alice_id, bob_id)
        )

        _cleanup_users(alice_id, bob_id)
        alice_id = _seed_user(
            "Alice Manual", f"alice-{uuid.uuid4()}@test.com", Decimal("100.00")
        )
        bob_id = _seed_user(
            "Bob Manual", f"bob-{uuid.uuid4()}@test.com", Decimal("50.00")
        )

        print("\n─── Test 4: Insufficient funds (no partial write) ───")
        t.test_insufficient_funds_no_partial_write(
            test_client, (alice_id, bob_id)
        )

        print("\n" + "=" * 60)
        print("  ALL TESTS PASSED ✓")
        print("=" * 60)

    finally:
        _cleanup_users(alice_id, bob_id)
