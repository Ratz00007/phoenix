"""FastAPI plugin router for Phoenix dashboard and observability."""

from __future__ import annotations

try:
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/status")
    def get_status():
        import sys
        from pathlib import Path

        # Add phoenix parent dir to sys.path so 'phoenix' is importable
        grandparent_dir = str(Path(__file__).resolve().parent.parent.parent)
        if grandparent_dir not in sys.path:
            sys.path.insert(0, grandparent_dir)

        from phoenix.core import get_app
        from phoenix.windtunnel import run_windtunnel_suite

        app = get_app()
        j = app._journal()
        stats = j.stats()

        verdict = j.get_meta("windtunnel_verdict") if hasattr(j, "get_meta") else ""
        if not verdict:
            try:
                report = run_windtunnel_suite(runs=1, journal=j)
                passed_count = sum(1 for c in report.get("checks", []) if c.get("passed"))
                total_checks = len(report.get("checks", [])) or 6
                verdict = f"{passed_count}/{total_checks} {'PASS' if report.get('passed') else 'FAIL'}"
                if hasattr(j, "set_meta"):
                    j.set_meta("windtunnel_verdict", verdict)
            except Exception:
                verdict = "UNKNOWN"

        return {
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
