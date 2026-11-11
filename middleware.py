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
import re
import uuid
from typing import Any, Callable

from .core import get_app
from .keys import (
    has_target_changed,
    is_hermes_error_result,
    is_target_fully_committed,
    op_id,
    target_fingerprint,
)

_READ_ONLY_TOOLS = frozenset({
    "read_file",
    "view_image",
    "web_search",
    "fetch_web_page",
    "phoenix_ledger",
    "phoenix_windtunnel",
})

_DECLARED_MUTATING_TOOLS = frozenset({
    "write_file",
    "patch",
    "apply_patch",
    "edit_file",
})


def _is_read_only(tool: str, args: Any) -> bool:
    if tool in _READ_ONLY_TOOLS:
        return True
    if tool in ("terminal", "bash", "shell") and isinstance(args, dict):
        cmd = args.get("command") or args.get("cmd") or ""
        if isinstance(cmd, str) and re.match(r"^\s*(ls|cat|pwd|git status|git diff|git log|pytest|echo)\b", cmd):
            return True
    return False


def _get_explicit_idempotency_key(args: Any, kwargs: dict[str, Any]) -> str | None:
    """Extract an explicit idempotency_key from kwargs, args, or args metadata."""
    if kwargs.get("idempotency_key"):
        return str(kwargs["idempotency_key"])
    if isinstance(args, dict):
        if args.get("idempotency_key"):
            return str(args["idempotency_key"])
        if args.get("_idempotency_key"):
            return str(args["_idempotency_key"])
        meta = args.get("metadata")
        if isinstance(meta, dict) and meta.get("idempotency_key"):
            return str(meta["idempotency_key"])
    return None



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
        explicit_key = _get_explicit_idempotency_key(args, kwargs)
        key = op_id(tool, args, idempotency_key=explicit_key)
        attempt = uuid.uuid4().hex

        session_id = kwargs.get("session_id")
        turn_id = kwargs.get("turn_id")
        tool_call_id = kwargs.get("tool_call_id")

        # Idempotency deduplication guard:
        # 1. Opt-in: only when guard_enabled is True
        # 2. NEVER cache read-only tools or across sessions
        # 3. ONLY deduplicate if:
        #    a) caller provides explicit idempotency_key (never across sessions), OR
        #    b) tool is in declared mutating tools {"write_file", "patch", "apply_patch", "edit_file"}
        #       AND within exact same session_id (must match kwargs.get('session_id') and be non-empty),
        #       AND target on disk is in fully committed state!
        can_deduplicate = False
        require_committed_state = False

        is_declared_mutating = (
            tool in _DECLARED_MUTATING_TOOLS
            or (callable(state_probe) and tool in {"crm.update_plan", "write_file", "patch", "apply_patch", "edit_file"})
        )

        if getattr(app, "guard_enabled", False) and not _is_read_only(tool, args):
            if explicit_key is not None:
                can_deduplicate = True
                require_committed_state = False
            elif is_declared_mutating and bool(session_id):
                can_deduplicate = True
                require_committed_state = True

        if can_deduplicate:
            prev_fp = None
            try:
                prev_fp = app._journal().latest_pre_fp(key, session_id=session_id)
            except Exception:
                prev_fp = None

            cached = None
            try:
                cached = app._journal().latest_success(key, session_id=session_id)
            except Exception:
                cached = None

            # Only deduplicate if a prior attempt or cached success exists in this session
            if cached is not None or prev_fp is not None:
                # Mutating tools: only deduplicate if target is actually currently in committed state
                target_committed = False
                if prev_fp is not None:
                    if callable(state_probe):
                        try:
                            probe_prev = prev_fp.get("probe") if "probe" in prev_fp else prev_fp.get("state_probe")
                            curr_probe = state_probe(tool, args)
                            target_committed = curr_probe != probe_prev or curr_probe > 0
                        except Exception:
                            target_committed = False
                    elif tool in _DECLARED_MUTATING_TOOLS:
                        try:
                            target_committed = is_target_fully_committed(tool, args, prev_fp)
                        except Exception:
                            target_committed = False
                    else:
                        try:
                            target_committed = has_target_changed(prev_fp, state_probe=state_probe)
                        except Exception:
                            target_committed = False
                elif callable(state_probe):
                    try:
                        target_committed = state_probe(tool, args) > 0
                    except Exception:
                        target_committed = False
                elif tool in _DECLARED_MUTATING_TOOLS:
                    try:
                        target_committed = is_target_fully_committed(tool, args, None)
                    except Exception:
                        target_committed = False

                # If require_committed_state is True, target MUST be fully committed on disk!
                if not require_committed_state or target_committed:
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

                    # Prior attempt already mutated target (e.g. timeout after commit)
                    if prev_fp is not None and target_committed:
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
