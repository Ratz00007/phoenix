"""Unit tests for Phoenix Forward Recovery Engine (zero-LLM)."""

from __future__ import annotations

from pathlib import Path

from phoenix.hooks import session_start_hook
from phoenix.ledger import Ledger
from phoenix.models import CallStatus, SideEffect
from phoenix.recovery import RecoveryEngine
from phoenix.tools import make_tool_handlers


def test_recovery_reconciles_when_effect_landed(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        rec = led.begin(
            session_id="sess_crash",
            turn_id="t1",
            tool_name="charge_card",
            args={"amount": 240},
            side_effect_class=SideEffect.EXTERNAL,
            idempotency_key="key_charge_1",
            pre_fingerprint="pre_fp",
            cost_cents=240,
        )
        assert len(led.pending_calls("sess_crash")) == 1

        engine = RecoveryEngine(led)

        # Verifier confirms external charge actually landed before SIGKILL
        def verifier(call):
            return True, "stripe_charge:ch_verified"

        report = engine.recover(session_id="sess_crash", state_verifier=verifier)
        assert report.dupes_prevented == 1
        assert report.ops_recovered == 0
        assert report.llm_calls_avoided == 1

        updated = led.get(rec.id)
        assert updated is not None
        assert updated.status == CallStatus.RECOVERED
        assert updated.post_fingerprint == "stripe_charge:ch_verified"
        assert len(led.pending_calls("sess_crash")) == 0
    finally:
        led.close()


def test_recovery_clears_when_effect_did_not_land(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        rec = led.begin(
            session_id="sess_unlanded",
            turn_id="t1",
            tool_name="write_file",
            args={"path": "test.txt", "content": "lost"},
            side_effect_class=SideEffect.WRITE,
            idempotency_key="k_lost",
            pre_fingerprint="pre_fp",
            cost_cents=10,
        )

        engine = RecoveryEngine(led)

        # Verifier confirms effect did NOT land
        def verifier(call):
            return False, "file_missing"

        report = engine.recover(session_id="sess_unlanded", state_verifier=verifier)
        assert report.dupes_prevented == 0
        assert report.ops_recovered == 1

        updated = led.get(rec.id)
        assert updated is not None
        assert updated.status == CallStatus.FAILED
    finally:
        led.close()


def test_session_start_hook_alerts(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        # Clean state: hook returns None
        assert session_start_hook(ledger=led) is None

        # Crash state: pending call exists
        led.begin(
            session_id="crashed_sess",
            turn_id=None,
            tool_name="charge",
            args={},
            side_effect_class=SideEffect.EXTERNAL,
            idempotency_key="k",
            pre_fingerprint=None,
        )
        alert = session_start_hook(ledger=led)
        assert alert is not None
        assert "Crash detected" in alert
        assert "/recover" in alert
    finally:
        led.close()


def test_phoenix_recover_tool(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        led.begin(
            session_id="s1",
            turn_id=None,
            tool_name="tool_a",
            args={},
            side_effect_class=SideEffect.WRITE,
            idempotency_key=None,
            pre_fingerprint=None,
        )
        handlers = make_tool_handlers(led)

        # Dry run: does not commit
        dry_res = handlers["phoenix_recover"]({"dry_run": True})
        assert "dry_run" in dry_res
        assert len(led.pending_calls()) == 1

        # Real run: executes recovery
        real_res = handlers["phoenix_recover"]({"dry_run": False})
        assert "completed" in real_res
        assert len(led.pending_calls()) == 0
    finally:
        led.close()
