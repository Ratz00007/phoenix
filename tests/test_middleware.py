"""Unit tests for Phoenix execution interception middleware."""

from __future__ import annotations

from pathlib import Path

import pytest
from phoenix.config import PhoenixConfig
from phoenix.ledger import Ledger
from phoenix.middleware import PhoenixMiddleware
from phoenix.models import CallStatus, SideEffect


def test_middleware_intercepts_and_commits(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        mw = PhoenixMiddleware(led)
        called = False

        def my_tool():
            nonlocal called
            called = True
            return {"status": "ok", "items_processed": 5}

        result = mw.intercept(
            tool_name="process_batch",
            args={"batch_id": 10},
            session_id="sess_mw",
            execute_fn=my_tool,
        )

        assert called is True
        assert result["status"] == "ok"

        calls = led.query(session_id="sess_mw")
        assert len(calls) == 1
        assert calls[0].status == CallStatus.COMMITTED
        assert calls[0].tool_name == "process_batch"
        assert calls[0].duration_ms is not None
    finally:
        led.close()


def test_middleware_replays_on_idempotency_match(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        config = PhoenixConfig(idempotency_enabled=True)
        mw = PhoenixMiddleware(led, config=config)

        execution_count = 0

        def charge_tool():
            nonlocal execution_count
            execution_count += 1
            return {"charge_id": "ch_first", "amount": 240}

        # First run: executes
        res1 = mw.intercept(
            tool_name="charge_card",
            args={"amount": 240},
            session_id="sess_idem",
            execute_fn=charge_tool,
            opt_in_idempotency=True,
            idempotency_key="key_exact_1",
        )
        assert execution_count == 1
        assert res1["charge_id"] == "ch_first"

        # Second run with same key: REPLAYS stored result, execution_count does NOT increase!
        res2 = mw.intercept(
            tool_name="charge_card",
            args={"amount": 240},
            session_id="sess_idem",
            execute_fn=charge_tool,
            opt_in_idempotency=True,
            idempotency_key="key_exact_1",
        )
        assert execution_count == 1  # Exactly once!
        assert res2["charge_id"] == "ch_first"
    finally:
        led.close()


def test_middleware_fails_on_exception(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        mw = PhoenixMiddleware(led)

        def failing_tool():
            raise RuntimeError("Database connection timeout")

        with pytest.raises(RuntimeError):
            mw.intercept(
                tool_name="failing_action",
                args={},
                session_id="sess_fail_mw",
                execute_fn=failing_tool,
            )

        calls = led.query(session_id="sess_fail_mw")
        assert len(calls) == 1
        assert calls[0].status == CallStatus.FAILED
        assert "Database connection timeout" in str(calls[0].error)
    finally:
        led.close()
