"""Unit tests for Phoenix Flight Recorder Desktop Surface and Read-Only Routes."""

from __future__ import annotations

import re
from pathlib import Path

from dashboard.routes import handle_get_calls, handle_get_events, handle_get_stats
from phoenix.ledger import Ledger
from phoenix.models import SideEffect


def test_routes_readonly(tmp_path: Path):
    """Verify that dashboard routes return strictly sanitized, read-only data with pagination."""
    db_path = tmp_path / "phoenix.db"
    led = Ledger(db_path, base_dir=tmp_path)
    try:
        # Seed two calls
        rec1 = led.begin(
            session_id="sess_ui",
            turn_id="t1",
            tool_name="charge_card",
            args={"amount": 240, "api_key": "mock_secret_key_123"},
            side_effect_class=SideEffect.EXTERNAL,
            idempotency_key="key_ui_1",
            pre_fingerprint="fp1",
            cost_cents=240,
        )
        led.commit(rec1.id, post_fingerprint="fp2", result={"ok": True}, duration_ms=12)

        # 1. Test /phoenix/calls
        calls_resp = handle_get_calls(ledger=led, session_id="sess_ui", limit=10, offset=0)
        assert calls_resp["status"] == "ok"
        assert len(calls_resp["calls"]) == 1
        call_item = calls_resp["calls"][0]
        assert call_item["tool_name"] == "charge_card"
        assert call_item["cost_cents"] == 240

        # 2. Test /phoenix/events/{id}
        evs_resp = handle_get_events(rec1.id, ledger=led)
        assert evs_resp["status"] == "ok"
        assert len(evs_resp["events"]) >= 2
        # Verify secret redaction in events
        for ev in evs_resp["events"]:
            raw_payload = str(ev["payload"])
            assert "mock_secret_key_123" not in raw_payload

        # 3. Test /phoenix/stats
        stats_resp = handle_get_stats(ledger=led)
        assert stats_resp["status"] == "ok"
        assert "dupes_prevented" in stats_resp["stats"]
        assert "cost_saved_cents" in stats_resp["stats"]
    finally:
        led.close()


def test_desktop_sdk_compliance():
    """Verify Desktop entry strictly adheres to Hermes SDK constraints."""
    plugin_js = Path(__file__).resolve().parent.parent / "desktop" / "plugin.js"
    assert plugin_js.exists(), "desktop/plugin.js must exist"

    content = plugin_js.read_text(encoding="utf-8")

    # Invariant: No eval or Function constructors
    assert not re.search(r"\beval\s*\(", content), "desktop/plugin.js must not contain eval()"
    assert not re.search(r"new\s+Function\s*\(", content), "desktop/plugin.js must not contain new Function()"

    # Invariant: No DOM monkey-patching or MutationObserver on document
    assert "document.body" not in content, "desktop/plugin.js must not access document.body"
    assert "MutationObserver" not in content, "desktop/plugin.js must not attach MutationObservers"

    # Invariant: Only permitted imports
    import_matches = re.findall(r'from\s+["\']([^"\']+)["\']', content)
    for imp in import_matches:
        assert imp in ("react", "@hermes/plugin-sdk"), f"Disallowed desktop import: {imp}"
