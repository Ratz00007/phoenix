"""Unit tests for Phoenix SQLite WAL Ledger."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from phoenix.ledger import Ledger
from phoenix.models import CallStatus, SideEffect


def test_wal_and_full_sync(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        assert led._pragma("journal_mode") == "wal"
        assert led._pragma("synchronous") == 2  # FULL
    finally:
        led.close()


def test_commit_is_fsynced_before_status(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        rec = led.begin(
            session_id="sess_1",
            turn_id="turn_1",
            tool_name="write_file",
            args={"path": "test.txt", "content": "hello"},
            side_effect_class=SideEffect.WRITE,
            idempotency_key="key_1",
            pre_fingerprint="pre_hash_123",
            cost_cents=10,
        )
        assert rec.status == CallStatus.PENDING

        led.commit(rec.id, post_fingerprint="post_hash_456", result={"bytes": 5}, duration_ms=15)

        evs = led.events(rec.id)
        assert [e["event_type"] for e in evs][-1] == "commit"
        assert all(e["fsynced"] for e in evs)

        committed_rec = led.get(rec.id)
        assert committed_rec is not None
        assert committed_rec.status == CallStatus.COMMITTED
        assert committed_rec.post_fingerprint == "post_hash_456"
        assert committed_rec.duration_ms == 15
    finally:
        led.close()


def test_db_file_mode_0600(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    led.close()
    if os.name == "posix":
        assert (db_path.stat().st_mode & 0o777) == 0o600
    else:
        assert db_path.exists()


def test_readonly(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        led.begin(
            session_id="sess_2",
            turn_id=None,
            tool_name="read_file",
            args={"path": "a.txt"},
            side_effect_class=SideEffect.READ,
            idempotency_key=None,
            pre_fingerprint=None,
        )
        # Read queries work cleanly without write locks
        calls = led.query(session_id="sess_2")
        assert len(calls) == 1
        assert calls[0].tool_name == "read_file"
        stats = led.counters()
        assert isinstance(stats, dict)
    finally:
        led.close()


def test_pending_and_fail(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        rec = led.begin(
            session_id="sess_fail",
            turn_id=None,
            tool_name="charge",
            args={"amt": 100},
            side_effect_class=SideEffect.EXTERNAL,
            idempotency_key="key_fail",
            pre_fingerprint=None,
        )
        pending = led.pending_calls("sess_fail")
        assert len(pending) == 1
        assert pending[0].id == rec.id

        led.fail(rec.id, error="Network socket dropped")
        assert len(led.pending_calls("sess_fail")) == 0
        failed_rec = led.get(rec.id)
        assert failed_rec is not None
        assert failed_rec.status == CallStatus.FAILED
        assert failed_rec.error == "Network socket dropped"
    finally:
        led.close()
