"""FastAPI plugin router for Phoenix dashboard and observability."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure parent directory is on sys.path so 'phoenix' is importable
_grandparent_dir = str(Path(__file__).resolve().parent.parent.parent)
if _grandparent_dir not in sys.path:
    sys.path.insert(0, _grandparent_dir)


def _get_app() -> Any:
    """Resolve the active Phoenix App singleton without module-split duplication."""
    core_mod = sys.modules.get("hermes_plugins.phoenix.core") or sys.modules.get("phoenix.core")
    if core_mod is not None and hasattr(core_mod, "get_app"):
        return core_mod.get_app()
    from phoenix.core import get_app

    return get_app()


def _get_windtunnel_runner():
    """Resolve run_windtunnel_suite from the loaded plugin namespace if present."""
    wt_mod = sys.modules.get("hermes_plugins.phoenix.windtunnel") or sys.modules.get("phoenix.windtunnel")
    if wt_mod is not None and hasattr(wt_mod, "run_windtunnel_suite"):
        return wt_mod.run_windtunnel_suite
    from phoenix.windtunnel import run_windtunnel_suite

    return run_windtunnel_suite


def _compute_db_bytes(journal: Any) -> int:
    """Return total on-disk bytes for the SQLite WAL database, or 0 for :memory:."""
    db_path = getattr(journal, "db_path", None)
    if not db_path or db_path == ":memory:":
        return 0
    total = 0
    for suffix in ("", "-wal", "-shm"):
        candidate = f"{db_path}{suffix}"
        try:
            if os.path.exists(candidate):
                total += os.path.getsize(candidate)
        except OSError:
            pass
    return total


def _matches_query(item: dict[str, Any], query: str) -> bool:
    """Case-insensitive substring match across timeline item fields."""
    needle = query.lower()
    for field in ("attempt_id", "op_id", "tool", "status", "error", "session_id", "turn_id"):
        val = item.get(field)
        if val is not None and needle in str(val).lower():
            return True
    for json_field in ("args", "result"):
        val = item.get(json_field)
        if val is not None:
            try:
                text = val if isinstance(val, str) else json.dumps(val, default=str)
            except Exception:
                text = str(val)
            if needle in text.lower():
                return True
    return False


def get_status() -> dict[str, Any]:
    """Sub-10ms read-only WAL status query. Never executes the windtunnel suite."""
    app = _get_app()
    j = app._journal()
    stats = j.stats()

    verdict = (j.get_meta("windtunnel_verdict", "UNKNOWN") if hasattr(j, "get_meta") else "UNKNOWN") or "UNKNOWN"
    last_wt_at = (j.get_meta("last_windtunnel_at", "") if hasattr(j, "get_meta") else "") or None

    return {
        "status": "ok",
        "stats": stats,
        "guard_enabled": app.guard_enabled,
        "committed": stats.get("committed", 0),
        "deduped": stats.get("deduped", 0),
        "in_flight": stats.get("in_flight", 0),
        "errors": stats.get("errors", 0),
        "total": stats.get("total", 0),
        "db_bytes": _compute_db_bytes(j),
        "windtunnel_verdict": verdict,
        "last_windtunnel_at": last_wt_at,
    }


def get_timeline(
    limit: int = 50,
    status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Query recent journal operations with optional status and text filtering."""
    app = _get_app()
    j = app._journal()

    if hasattr(j, "timeline"):
        items = j.timeline(limit=limit, status=status, query=q)
    else:
        items = j.recent(limit=limit)
        if status:
            items = [item for item in items if item.get("status") == status]
        if q:
            items = [item for item in items if _matches_query(item, q)]

    return {
        "status": "ok",
        "items": items,
        "count": len(items),
    }


def post_windtunnel() -> dict[str, Any]:
    """Run the ReplayLab windtunnel suite on demand and persist its verdict."""
    app = _get_app()
    j = app._journal()
    run_windtunnel_suite = _get_windtunnel_runner()

    report = run_windtunnel_suite(runs=3, journal=j)
    passed_count = sum(1 for c in report.get("checks", []) if c.get("passed"))
    total_checks = len(report.get("checks", [])) or 6
    verdict = f"{passed_count}/{total_checks} {'PASS' if report.get('passed') else 'FAIL'}"
    last_wt_at = datetime.now(timezone.utc).isoformat()

    if hasattr(j, "set_meta"):
        j.set_meta("windtunnel_verdict", verdict)
        j.set_meta("last_windtunnel_at", last_wt_at)

    return {
        "status": "ok",
        "verdict": verdict,
        "report": report,
    }


def _register_routes(target_router: Any) -> None:
    target_router.get("/status")(get_status)
    target_router.get("/timeline")(get_timeline)
    target_router.post("/windtunnel")(post_windtunnel)


try:
    from fastapi import APIRouter

    router = APIRouter()
    _register_routes(router)

except ImportError:
    class _StubRouter:
        """Lightweight stub router when FastAPI is not installed."""

        def __init__(self) -> None:
            self.routes = []

        def get(self, path: str, *args, **kwargs):
            def decorator(fn):
                self.routes.append(("GET", path, fn))
                return fn
            return decorator

        def post(self, path: str, *args, **kwargs):
            def decorator(fn):
                self.routes.append(("POST", path, fn))
                return fn
            return decorator

    router = _StubRouter()
    _register_routes(router)
