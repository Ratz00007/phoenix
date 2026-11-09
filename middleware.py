"""``tool_execution`` middleware: journal intent before, outcome after.

This is the crash-detection and idempotency mechanism. Because the intent row
is committed to SQLite *before* ``next_call`` runs and the outcome is committed
*after* it returns, a row stuck in ``intent`` is exactly the signature of "the
process died during or immediately after this call" — the ambiguous write.

Fail-open by construction: if journaling raises, the tool still executes and
the exception is swallowed, so Phoenix can never break the agent.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from .core import get_app
from .keys import has_target_changed, is_hermes_error_result, op_id, target_fingerprint


def make_middleware(
    app_getter: Callable[[], Any] = get_app,
    state_probe: Callable[[str, Any], Any] | None = None,
):
    """Create a tool execution middleware function with optional app getter and state probe."""

    def _middleware(**kwargs):
        tool = kwargs.get("tool_name", "unknown")
        if tool in {"phoenix_ledger", "phoenix_windtunnel"}:
            return kwargs["next_call"](kwargs.get("args"))

        app = app_getter() if callable(app_getter) else app_getter
        args = kwargs.get("args") or {}
        key = op_id(tool, args)
        attempt = uuid.uuid4().hex

        session_id = kwargs.get("session_id")
        turn_id = kwargs.get("turn_id")
        tool_call_id = kwargs.get("tool_call_id")

        # Idempotency deduplication guard
        if getattr(app, "guard_enabled", False):
            # 1. Prior successful execution
            cached = None
            try:
                cached = app._journal().latest_success(key)
            except Exception:
                cached = None
            if cached is not None:
                _, cached_json = cached
                try:
                    cached_val = json.loads(cached_json) if cached_json is not None else None
                except Exception:
                    cached_val = cached_json
                try:
                    app._journal().record_intent(
                        attempt, key, tool, args, session_id, turn_id, tool_call_id
                    )
                    app._journal().record_outcome(attempt, key, "deduped", result=cached_val)
                except Exception:
                    pass
                return cached_val

            # 2. Prior attempt already mutated target
            prev_fp = None
            try:
                prev_fp = app._journal().latest_pre_fp(key)
            except Exception:
                prev_fp = None
            if prev_fp is not None and has_target_changed(prev_fp, state_probe=state_probe):
                dedup_val = {
                    "ok": True,
                    "deduped": True,
                    "op_id": key,
                    "reason": "prior_attempt_already_mutated_target",
                }
                try:
                    app._journal().record_intent(
                        attempt, key, tool, args, session_id, turn_id, tool_call_id
                    )
                    app._journal().record_outcome(attempt, key, "deduped", result=dedup_val)
                except Exception:
                    pass
                return dedup_val

        # 1) Pre-execution state fingerprinting
        pre_fp = None
        try:
            pre_fp = target_fingerprint(tool, args, state_probe=state_probe)
            if isinstance(pre_fp, dict) and state_probe is not None:
                pre_fp["tool"] = tool
                pre_fp["args"] = args
        except Exception:
            pre_fp = None

        # 2) Journal intent BEFORE execution (fail-open)
        try:
            app._journal().record_intent(
                attempt, key, tool, args, session_id, turn_id, tool_call_id, pre_fp=pre_fp
            )
        except Exception:
            pass

        # 3) Execute (preserve Hermes' own result/error semantics).
        try:
            result = kwargs["next_call"](kwargs.get("args"))
        except Exception as exc:
            try:
                app._journal().record_outcome(attempt, key, "error", error=repr(exc))
            except Exception:
                pass
            raise

        # 4) Journal outcome AFTER execution.
        try:
            is_err, err_msg = is_hermes_error_result(result)
            if is_err:
                app._journal().record_outcome(attempt, key, "error", result=result, error=err_msg)
            else:
                app._journal().record_outcome(attempt, key, "ok", result=result)
        except Exception:
            pass

        return result

    return _middleware


tool_execution_middleware = make_middleware()
