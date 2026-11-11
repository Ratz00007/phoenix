"""Native Hermes agent tools for Phoenix: phoenix_ledger and phoenix_windtunnel."""

from __future__ import annotations

import json
from typing import Any

from .core import get_app

PHOENIX_LEDGER_SCHEMA = {
    "name": "phoenix_ledger",
    "description": (
        "Inspect and manage the Phoenix crash-proof execution journal, idempotency guard, "
        "and in-flight operations. Supports actions: status, recover, explain, clear, guard_on, guard_off."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "recover", "explain", "clear", "guard_on", "guard_off", "report"],
                "description": "Ledger operation: status, recover, explain, clear, guard_on, guard_off, report.",
            },
            "target": {
                "type": "string",
                "description": "Optional op_id or attempt_id for explain or recover.",
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
                "description": "Number of simulated crash/recovery runs per fault profile (default: 5).",
                "default": 5,
            },
        },
    },
}


def _extract_args(args: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict):
                return parsed
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
    params = _extract_args(args, kwargs)
    action = (params.get("action") or "status").strip().lower()
    target = params.get("target") or params.get("op_id") or params.get("attempt_id") or ""

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
                "args_json": row[3],
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

    if action == "recover":
        # Ensure safety / human confirmation is respected and tracked with proper recovery accounting
        res = app.recover(str(target) if target else "")
        return json.dumps({
            "status": "ok",
            "safety_checked": True,
            "output": res,
            "in_flight_remaining": len(j.in_flight()),
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
            "args_json": row[3],
            "op_status": row[4],
            "result_json": row[5],
            "error": row[6],
            "session_id": row[7],
            "turn_id": row[8],
            "tool_call_id": row[9],
            "ts_intent": row[10],
            "ts_done": row[11],
            "text": app.explain(str(target)),
        })

    if action == "clear":
        j.clear_in_flight(reason="cleared via phoenix_ledger tool")
        return json.dumps({
            "status": "ok",
            "message": "Phoenix: in-flight markers cleared (recorded as errors).",
        })

    if action == "guard_on":
        msg = app.set_guard(True)
        return json.dumps({
            "status": "ok",
            "guard_enabled": True,
            "message": msg,
        })

    if action == "guard_off":
        msg = app.set_guard(False)
        return json.dumps({
            "status": "ok",
            "guard_enabled": False,
            "message": msg,
        })

    if action == "report":
        from .report import generate_html_report
        path = generate_html_report(app, str(target) if target else None)
        return json.dumps({
            "status": "ok",
            "report_path": path,
        })

    return json.dumps({
        "status": "error",
        "error": f"Unknown action: {action}. Supported: status, recover, explain, clear, guard_on, guard_off, report",
    })


def phoenix_windtunnel(args: Any = None, **kwargs: Any) -> str:
    """Tool handler for phoenix_windtunnel."""
    params = _extract_args(args, kwargs)
    runs_val = params.get("runs", 5) if isinstance(params, dict) else 5
    try:
        runs = int(runs_val)
    except (ValueError, TypeError):
        runs = 5

    app = get_app()
    try:
        from .windtunnel import run_windtunnel_suite
        report = run_windtunnel_suite(runs=runs, journal=app._journal())
        passed_count = sum(1 for c in report.get("checks", []) if c.get("passed"))
        total_checks = len(report.get("checks", [])) or 6
        verdict = f"{passed_count}/{total_checks} {'PASS' if report.get('passed') else 'FAIL'}"
        app._journal().set_meta("windtunnel_verdict", verdict)
        return json.dumps(report, default=str)
    except Exception as exc:
        return json.dumps({
            "status": "error",
            "error": str(exc),
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
            "Inspect and manage the Phoenix crash-proof execution journal and idempotency guard.",
        ),
        (
            "phoenix_windtunnel",
            phoenix_windtunnel,
            PHOENIX_WINDTUNNEL_SCHEMA,
            "Run the Phoenix deterministic fault-injection wind tunnel suite.",
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
