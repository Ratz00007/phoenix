"""Unit tests for Phoenix Value Metrics and Trust Reports."""

from __future__ import annotations

import json
from pathlib import Path

from phoenix.ledger import Ledger
from phoenix.metrics import MetricsService
from phoenix.models import RecoveryReport, SideEffect
from phoenix.tools import make_tool_handlers


def test_cost_saved_reconciles(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        # Simulate 3 prevented duplicates with recorded recoveries
        rec_id = led.start_recovery("sess_val")
        report = RecoveryReport(
            ops_recovered=2,
            dupes_prevented=3,
            llm_calls_avoided=3,
            cost_saved_cents=300,
        )
        led.finish_recovery(rec_id, report)

        counters = led.counters()
        assert counters["dupes_prevented"] == 3
        assert counters["ops_recovered"] == 2
        assert counters["llm_calls_avoided"] == 3
        assert counters["cost_saved_cents"] == 300
    finally:
        led.close()


def test_trust_report(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        rec = led.begin(
            session_id="sess_rep",
            turn_id="t1",
            tool_name="charge_card",
            args={"amount": 24000},
            side_effect_class=SideEffect.EXTERNAL,
            idempotency_key="k_rep",
            pre_fingerprint="pre_hash",
            cost_cents=240,
        )
        led.commit(rec.id, post_fingerprint="post_hash", result={"ok": True}, duration_ms=10)

        service = MetricsService(led)
        report_md = service.generate_trust_report(session_id="sess_rep")
        assert "Phoenix Flight Recorder & Trust Report" in report_md
        assert "Financial Capital Saved" in report_md
        assert "charge_card" in report_md
    finally:
        led.close()


def test_phoenix_stats_tool(tmp_path: Path):
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        handlers = make_tool_handlers(led)
        raw_json = handlers["phoenix_stats"]({})
        parsed = json.loads(raw_json)
        assert "dupes_prevented" in parsed
        assert "cost_saved_cents" in parsed
    finally:
        led.close()
