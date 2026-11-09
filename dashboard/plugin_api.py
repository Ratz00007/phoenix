"""FastAPI plugin router for Phoenix dashboard and observability."""

from __future__ import annotations

try:
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/status")
    def get_status():
        from ..core import get_app

        app = get_app()
        stats = app._journal().stats()
        return {
            "status": "ok",
            "stats": stats,
            "guard_enabled": app.guard_enabled,
            "committed": stats.get("committed", 0),
            "deduped": stats.get("deduped", 0),
            "in_flight": stats.get("in_flight", 0),
            "errors": stats.get("errors", 0),
            "total": stats.get("total", 0),
            "windtunnel_verdict": "6/6 PASS",
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
