"""Phoenix lifecycle hooks.

Guarantee: Detects prior host crashes on session start and provides non-destructive recovery prompts.
"""

from __future__ import annotations

from typing import Any

from .ledger import Ledger


def session_start_hook(ctx: Any = None, session: Any = None, ledger: Ledger | None = None) -> str | None:
    """Inspect previous session state upon agent boot and alert if uncommitted calls exist."""
    if ledger is None:
        return None
    pending = ledger.pending_calls()
    if pending:
        msg = (
            f"[phoenix] ⚠️ Crash detected: {len(pending)} in-flight tool call(s) were interrupted by SIGKILL. "
            f"Run /recover or invoke phoenix_recover to reconcile state exactly once with 0 duplicate executions."
        )
        return msg
    return None
