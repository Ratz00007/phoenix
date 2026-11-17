"""Native Hermes agent tools for Phoenix: phoenix_ledger, phoenix_windtunnel, and phoenix_stats."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .core import get_app

PHOENIX_LEDGER_SCHEMA = {
    "name": "phoenix_ledger",
    "description": (
        "Inspect the Phoenix crash-proof execution journal and flight recorder (actions: status, explain, report). "
        "Mutating and recovery actions (recover, clear, guard_on, guard_off) are restricted to human owner slash commands "
        "(/recover or /phoenix <action>)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "explain", "report"],
                "description": "Read-only ledger operation: status, explain, report. (recover, clear, guard_on/off restricted to owner commands).",
            },
            "target": {
                "type": "string",
                "description": "Optional op_id or attempt_id for explain, or bare report filename for report.",
            },
        },
        "required": ["action"],
    },
}

PHOENIX_WINDTUNNEL_SCHEMA = {
    "name": "phoenix_windtunnel",
    "description": (
        "Run the Phoenix deterministic fault-injection wind tunnel suite to simulate process "
        "kills mid-write and verify crash-proof recovery and idempotency."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "runs": {
                "type": "integer",
                "description": "Number of simulated crash/recovery runs per fault profile (1-20, default: 5).",
                "default": 5,
            },
        },
    },
}

PHOENIX_STATS_SCHEMA = {
    "name": "phoenix_stats",
    "description": (
        "Return read-only Phoenix ledger telemetry and health metrics "
        "(operation counts, idempotency guard state, SQLite WAL size, and windtunnel verdict)."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


def _extract_args(args: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict):
                merged = dict(parsed)
                merged.update(kwargs)
                return merged
        except Exception:
            return {"action": args}
    if isinstance(args, dict):
        merged = dict(args)
        merged.update(kwargs)
        return merged
    if kwargs:
        return dict(kwargs)
    return {}


def phoenix_ledger(args: Any = None, **kwargs: Any) -> str:
    """Tool handler for phoenix_ledger."""
    from .journal import redact_secrets

    params = _extract_args(args, kwargs)
    action = str(params.get("action") or "status").strip().lower()
    target = params.get("target") or params.get("op_id") or params.get("attempt_id") or ""

    if action in ("recover", "clear", "guard_on", "guard_off"):
        owner_cmds = {
            "recover": "/recover",
            "clear": "/phoenix clear",
            "guard_on": "/phoenix guard on",
            "guard_off": "/phoenix guard off",
        }
        owner_cmd = owner_cmds[action]
        return json.dumps({
            "status": "error",
            "error": (
                f"Action '{action}' is restricted to human owner commands "
                f"(/recover or /phoenix <action>). Please advise the human user to run {owner_cmd} in chat."
            ),
        })

    app = get_app()
    j = app._journal()

    if action == "status":
        stats = j.stats()
        inflight = j.in_flight()
        inflight_list = [
            {
                "attempt_id": row[0],
                "op_id": row[1],
                "tool": row[2],
                "args_json": redact_secrets(row[3]) or "{}",
                "session_id": row[4],
                "turn_id": row[5],
                "ts_intent": row[6],
            }
            for row in inflight
        ]
        return json.dumps({
            "status": "ok",
            "guard_enabled": app.guard_enabled,
            "stats": stats,
            "in_flight_count": len(inflight_list),
            "in_flight": inflight_list,
            "text": app.status_text(),
        })

    if action == "explain":
        if not target:
            return json.dumps({
                "status": "error",
                "error": "Missing target (op_id or attempt_id) for explain",
            })
        row = j.find(str(target))
        if row is None:
            return json.dumps({
                "status": "not_found",
                "target": str(target),
            })
        return json.dumps({
            "status": "ok",
            "attempt_id": row[0],
            "op_id": row[1],
            "tool": row[2],
            "args_json": redact_secrets(row[3]) or "{}",
            "op_status": row[4],
            "result_json": redact_secrets(row[5]) if row[5] is not None else None,
            "error": redact_secrets(row[6]) if row[6] is not None else None,
            "session_id": row[7],
            "turn_id": row[8],
            "tool_call_id": row[9],
            "ts_intent": row[10],
            "ts_done": row[11],
            "text": app.explain(str(target)),
        })

    if action == "report":
        from pathlib import Path
        from .report import generate_html_report

        reports_dir = Path(app._data_dir()) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        raw_target = str(target or "").strip()
        # Reject traversal or path separator characters
        if not raw_target or ".." in raw_target or "/" in raw_target or "\\" in raw_target:
            clean_name = "phoenix-report.html"
        else:
            clean_name = Path(raw_target).name.strip()
            if not clean_name or clean_name in (".", ".."):
                clean_name = "phoenix-report.html"
            elif not clean_name.endswith(".html"):
                clean_name = f"{clean_name}.html"

        out_file = reports_dir / clean_name
        try:
            if not out_file.resolve().is_relative_to(reports_dir.resolve()):
                out_file = reports_dir / "phoenix-report.html"
        except Exception:
            out_file = reports_dir / "phoenix-report.html"

        try:
            path = generate_html_report(app, str(out_file))
        except Exception as exc:
            return json.dumps({
                "status": "error",
                "error": str(exc),
            })
        return json.dumps({
            "status": "ok",
            "report_path": path,
        })

    return json.dumps({
        "status": "error",
        "error": f"Unknown action: {action}. Supported read-only actions: status, explain, report. Restricted owner commands: /recover, /phoenix <action>",
    })


def phoenix_windtunnel(args: Any = None, **kwargs: Any) -> str:
    """Tool handler for phoenix_windtunnel."""
    params = _extract_args(args, kwargs)
    runs_val = params.get("runs", 5) if isinstance(params, dict) else 5
    try:
        runs = int(runs_val)
    except (ValueError, TypeError):
        runs = 5

    runs = max(1, min(20, runs))

    app = get_app()
    try:
        from .windtunnel import run_windtunnel_suite
        j = app._journal()
        report = run_windtunnel_suite(runs=runs, journal=j)
        passed_count = sum(1 for c in report.get("checks", []) if c.get("passed"))
        total_checks = len(report.get("checks", [])) or 6
        verdict = f"{passed_count}/{total_checks} {'PASS' if report.get('passed') else 'FAIL'}"
        j.set_meta("windtunnel_verdict", verdict)
        j.set_meta("last_windtunnel_at", datetime.now(timezone.utc).isoformat())
        return json.dumps(report, default=str)
    except Exception as exc:
        return json.dumps({
            "status": "error",
            "error": str(exc),
        })


def phoenix_stats(args: Any = None, **kwargs: Any) -> str:
    """Read-only tool handler for phoenix_stats."""
    app = get_app()
    j = app._journal()
    stats = j.stats()
    verdict = (j.get_meta("windtunnel_verdict", "UNKNOWN") if hasattr(j, "get_meta") else "UNKNOWN") or "UNKNOWN"
    db_size = j.db_bytes() if hasattr(j, "db_bytes") else 0
    return json.dumps({
        "status": "ok",
        "total": stats.get("total", 0),
        "committed": stats.get("committed", 0),
        "in_flight": stats.get("in_flight", 0),
        "deduped": stats.get("deduped", 0),
        "recovered_landed": stats.get("recovered_landed", 0),
        "errors": stats.get("errors", 0),
        "guard_enabled": bool(app.guard_enabled),
        "db_bytes": db_size,
        "windtunnel_verdict": verdict,
    })


def register_tools(ctx: Any) -> None:
    """Register Phoenix native agent tools with the Hermes plugin context."""
    if not hasattr(ctx, "register_tool"):
        return

    tools_to_register = [
        (
            "phoenix_ledger",
            phoenix_ledger,
            PHOENIX_LEDGER_SCHEMA,
            "Inspect the Phoenix crash-proof execution journal and flight recorder (status, explain, report).",
        ),
        (
            "phoenix_windtunnel",
            phoenix_windtunnel,
            PHOENIX_WINDTUNNEL_SCHEMA,
            "Run the Phoenix deterministic fault-injection wind tunnel suite.",
        ),
        (
            "phoenix_stats",
            phoenix_stats,
            PHOENIX_STATS_SCHEMA,
            "Return read-only Phoenix ledger telemetry, guard state, WAL size, and windtunnel verdict.",
        ),
    ]

    for name, handler, schema, desc in tools_to_register:
        try:
            ctx.register_tool(
                name=name,
                toolset="phoenix",
                schema=schema,
                handler=handler,
                description=desc,
                emoji="🔥",
            )
        except TypeError:
            try:
                ctx.register_tool(name, handler, schema=schema, description=desc)
            except TypeError:
                try:
                    ctx.register_tool(name, handler)
                except Exception:
                    pass
        except Exception:
            pass
