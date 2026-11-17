"""FastAPI plugin router for Phoenix dashboard and observability."""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DASHBOARD_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _DASHBOARD_DIR.parent


def _resolve_loaded_package_root() -> str | None:
    """Return an already-loaded Phoenix package prefix (bare or profile-scoped)."""
    if "hermes_plugins.phoenix.core" in sys.modules:
        return "hermes_plugins.phoenix"
    for name in list(sys.modules):
        if name.startswith("hermes_plugins.phoenix__") and name.endswith(".core") and sys.modules[name] is not None:
            return name.rsplit(".", 1)[0]
    if "phoenix.core" in sys.modules:
        return "phoenix"
    return None


def _resolve_loaded_submodule(submodule: str) -> Any | None:
    """Find an already-loaded Phoenix submodule across bare or profile-scoped plugin namespaces."""
    exact = sys.modules.get(f"hermes_plugins.phoenix.{submodule}")
    if exact is not None:
        return exact
    for name, mod in list(sys.modules.items()):
        if (
            mod is not None
            and name.startswith("hermes_plugins.phoenix__")
            and name.endswith(f".{submodule}")
        ):
            return mod
    return sys.modules.get(f"phoenix.{submodule}")


def _import_relative_submodule(submodule: str) -> Any:
    """Resolve an already-loaded submodule or import it via package-relative imports."""
    loaded = _resolve_loaded_submodule(submodule)
    if loaded is not None:
        return loaded

    if __package__:
        return importlib.import_module(f"..{submodule}", __package__)

    # If core was already loaded under a hermes_plugins package namespace, import
    # sibling submodules from that same package to avoid splitting _APP.
    loaded_root = _resolve_loaded_package_root()
    if loaded_root and loaded_root != "phoenix":
        try:
            return importlib.import_module(f".{submodule}", loaded_root)
        except Exception:
            pass

    # Standalone single-file load (e.g. import_user_code without parent package):
    # register local package shells in sys.modules instead of mutating sys.path.
    pkg = sys.modules.get("phoenix")
    if pkg is None or not hasattr(pkg, "__path__"):
        pkg = types.ModuleType("phoenix")
        pkg.__path__ = [str(_PLUGIN_ROOT)]
        pkg.__package__ = "phoenix"
        sys.modules["phoenix"] = pkg

    subpkg = sys.modules.get("phoenix.dashboard")
    if subpkg is None or not hasattr(subpkg, "__path__"):
        subpkg = types.ModuleType("phoenix.dashboard")
        subpkg.__path__ = [str(_DASHBOARD_DIR)]
        subpkg.__package__ = "phoenix.dashboard"
        sys.modules["phoenix.dashboard"] = subpkg

    return importlib.import_module(f"..{submodule}", "phoenix.dashboard")


def _get_app() -> Any:
    """Resolve the active Phoenix App singleton without module-split duplication."""
    core_mod = _import_relative_submodule("core")
    return core_mod.get_app()


def _get_windtunnel_runner():
    """Resolve run_windtunnel_suite from the loaded plugin namespace if present."""
    wt_mod = _import_relative_submodule("windtunnel")
    return wt_mod.run_windtunnel_suite


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
    wt_report_raw = j.get_meta("windtunnel_report", "") if hasattr(j, "get_meta") else ""
    wt_report = None
    if wt_report_raw:
        try:
            parsed = json.loads(wt_report_raw)
            if isinstance(parsed, dict):
                wt_report = parsed
        except Exception:
            wt_report = None

    return {
        "status": "ok",
        "stats": stats,
        "guard_enabled": app.guard_enabled,
        "committed": stats.get("committed", 0),
        "deduped": stats.get("deduped", 0),
        "in_flight": stats.get("in_flight", 0),
        "recovered_landed": stats.get("recovered_landed", 0),
        "errors": stats.get("errors", 0),
        "total": stats.get("total", 0),
        "db_bytes": _compute_db_bytes(j),
        "windtunnel_verdict": verdict,
        "last_windtunnel_at": last_wt_at,
        "windtunnel_report": wt_report,
    }


def get_timeline(
    limit: int = 50,
    status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Query recent journal operations with optional status and text filtering."""
    try:
        safe_limit = max(0, min(int(limit), 500))
    except (TypeError, ValueError):
        safe_limit = 50

    app = _get_app()
    j = app._journal()

    if hasattr(j, "timeline"):
        items = j.timeline(limit=safe_limit, status=status, query=q)
    else:
        items = j.recent(limit=safe_limit)
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
        try:
            j.set_meta("windtunnel_report", json.dumps(report, default=str))
        except Exception:
            pass

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
