"""Unit tests for Phoenix Exactly-Once engine and external adapters."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from phoenix.adapters.email import EmailAdapter
from phoenix.adapters.sql import SQLAdapter
from phoenix.adapters.stripe import StripeAdapter
from phoenix.idempotency import ExactlyOnce
from phoenix.ledger import Ledger
from phoenix.models import SideEffect


def test_off_by_default_executes_normally(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        eo = ExactlyOnce(led, enabled=False)
        d = eo.decide(
            tool_name="charge",
            args={"amt": 100},
            session_id="s",
            pre_fp="p",
            opt_in=False,
        )
        assert d.action == "execute"
    finally:
        led.close()


def test_committed_same_key_returns_stored(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        eo = ExactlyOnce(led, enabled=True)
        rec = led.begin(
            session_id="s",
            turn_id=None,
            tool_name="charge",
            args={"amt": 100},
            side_effect_class=SideEffect.EXTERNAL,
            idempotency_key="k1",
            pre_fingerprint="p",
        )
        led.commit(rec.id, post_fingerprint="q", result={"charge_id": "ch_1"}, duration_ms=5)

        d = eo.decide(
            tool_name="charge",
            args={"amt": 100},
            session_id="s",
            pre_fp="p",
            opt_in=True,
            idempotency_key="k1",
        )
        assert d.action == "return_stored"
        assert d.stored is not None
        assert d.stored.id == rec.id
    finally:
        led.close()


def test_stripe_exactly_once():
    """Verify StripeAdapter guarantees exactly-once charge with Idempotency-Key."""
    adapter = StripeAdapter()
    key = "idem_card_charge_99"

    # First attempt: succeeds
    res1 = adapter.charge(amount_cents=5000, customer_id="cust_1", idempotency_key=key)
    assert res1["status"] == "succeeded"
    assert res1["idempotent_replay"] is False
    charge_id = res1["id"]

    # Second attempt with same key: returns existing charge, no duplicate charge created
    res2 = adapter.charge(amount_cents=5000, customer_id="cust_1", idempotency_key=key)
    assert res2["status"] == "succeeded"
    assert res2["id"] == charge_id
    assert res2["idempotent_replay"] is True

    landed, cid = adapter.verify_charge(key)
    assert landed is True
    assert cid == charge_id


def test_email_dedup():
    """Verify EmailAdapter prevents duplicate dispatch via Message-ID."""
    adapter = EmailAdapter()
    to = "user@example.com"
    subject = "Invoice #101"
    body = "Amount due: $240"

    mid = adapter.compute_message_id(to, subject, body)
    res1 = adapter.send_email(to=to, subject=subject, body=body, message_id=mid)
    assert res1["deduplicated"] is False

    # Second attempt: deduplicated
    res2 = adapter.send_email(to=to, subject=subject, body=body, message_id=mid)
    assert res2["deduplicated"] is True
    assert adapter.verify_sent(mid) is True


def test_sql_upsert(tmp_path: Path):
    """Verify SQLAdapter upserts with unique key and computes row fingerprint."""
    db_file = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, balance INTEGER, tier TEXT);")
    conn.commit()

    adapter = SQLAdapter(conn)

    # Initial upsert
    res1 = adapter.upsert("accounts", "id", "acc_1", {"balance": 1000, "tier": "gold"})
    assert res1["status"] == "upserted"
    fp1 = res1["post_fingerprint"]

    # Idempotent replay with same data
    res2 = adapter.upsert("accounts", "id", "acc_1", {"balance": 1000, "tier": "gold"})
    assert res2["post_fingerprint"] == fp1

    # Verify exactly 1 row exists
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM accounts WHERE id = 'acc_1'")
    assert cur.fetchone()[0] == 1
    conn.close()
