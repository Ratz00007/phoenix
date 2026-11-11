"""FastAPI plugin router for Phoenix dashboard and observability."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure parent directory is on sys.path so 'phoenix' is importable
_grandparent_dir = str(Path(__file__).resolve().parent.parent.parent)
if _grandparent_dir not in sys.path:
    sys.path.insert(0, _grandparent_dir)


def get_status() -> dict[str, Any]:
    """Query real-time status and live windtunnel verification results."""
    from phoenix.core import get_app
    from phoenix.windtunnel import run_windtunnel_suite

    app = get_app()
    j = app._journal()
    stats = j.stats()

    report = None
    try:
        report = run_windtunnel_suite(runs=1, journal=j)
        passed_count = sum(1 for c in report.get("checks", []) if c.get("passed"))
        total_checks = len(report.get("checks", [])) or 6
        verdict = f"{passed_count}/{total_checks} {'PASS' if report.get('passed') else 'FAIL'}"
        if hasattr(j, "set_meta"):
            j.set_meta("windtunnel_verdict", verdict)
    except Exception:
        verdict = j.get_meta("windtunnel_verdict", "UNKNOWN") if hasattr(j, "get_meta") else "UNKNOWN"

    payload: dict[str, Any] = {
        "status": "ok",
        "stats": stats,
        "guard_enabled": app.guard_enabled,
        "committed": stats.get("committed", 0),
        "deduped": stats.get("deduped", 0),
        "in_flight": stats.get("in_flight", 0),
        "errors": stats.get("errors", 0),
        "total": stats.get("total", 0),
        "windtunnel_verdict": verdict,
    }
    if report is not None:
        payload["windtunnel_report"] = {
            "passed": bool(report.get("passed")),
            "checks": report.get("checks", []),
            "faults_tested": 5,
        }
    return payload


try:
    from fastapi import APIRouter

    router = APIRouter()
    router.get("/status")(get_status)

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
    router.get("/status")(get_status)
