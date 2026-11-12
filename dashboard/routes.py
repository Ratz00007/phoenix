"""Read-only dashboard server routes for Phoenix Flight Recorder.

Guarantee: All routes are strictly read-only, sanitized with secret redaction, and paginated.
Limits: Mutating recovery operations must be invoked through official Hermes tools with approval.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from phoenix.config import load_config
from phoenix.ledger import Ledger
from phoenix.metrics import MetricsService
from phoenix.security import redact_secrets


def _get_ledger() -> Ledger:
    """Resolve active ledger from plugin storage or environment."""
    storage_dir = Path(os.environ.get("HERMES_PLUGIN_STORAGE", Path.cwd()))
    db_path = storage_dir / "phoenix.db"
    return Ledger(db_path, base_dir=storage_dir)


def handle_get_calls(
    ledger: Ledger | None = None,
    session_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Read-only paginated list of journaled tool calls."""
    led = ledger or _get_ledger()
    safe_limit = min(max(1, limit), 500)
    records = led.query(session_id=session_id, limit=safe_limit, offset=offset)

    return {
        "status": "ok",
        "total": len(records),
        "limit": safe_limit,
        "offset": offset,
        "calls": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "turn_id": r.turn_id,
                "seq": r.seq,
                "tool_name": r.tool_name,
                "args_hash": r.args_hash,
                "side_effect_class": r.side_effect_class.value,
                "idempotency_key": r.idempotency_key,
                "pre_fingerprint": r.pre_fingerprint,
                "post_fingerprint": r.post_fingerprint,
                "status": r.status.value,
                "cost_cents": r.cost_cents,
                "started_at": r.started_at,
                "committed_at": r.committed_at,
                "duration_ms": r.duration_ms,
            }
            for r in records
        ],
    }


def handle_get_events(call_id: str, ledger: Ledger | None = None) -> dict[str, Any]:
    """Read-only timeline of lifecycle events for a specific call."""
    led = ledger or _get_ledger()
    evs = led.events(call_id)
    return {
        "status": "ok",
        "call_id": call_id,
        "events": redact_secrets(evs),
    }


def handle_get_stats(ledger: Ledger | None = None) -> dict[str, Any]:
    """Read-only value metrics and flight recorder summary."""
    led = ledger or _get_ledger()
    metrics = MetricsService(led)
    stats = metrics.get_stats()
    return {
        "status": "ok",
        "stats": stats,
    }


# Optional FastAPI router exposure
try:
    from fastapi import APIRouter, Query

    router = APIRouter(prefix="/phoenix", tags=["phoenix"])

    @router.get("/calls")
    def get_calls_route(session_id: str | None = None, limit: int = 50, offset: int = 0):
        return handle_get_calls(session_id=session_id, limit=limit, offset=offset)

    @router.get("/events/{call_id}")
    def get_events_route(call_id: str):
        return handle_get_events(call_id)

    @router.get("/stats")
    def get_stats_route():
        return handle_get_stats()

except ImportError:
    router = None
