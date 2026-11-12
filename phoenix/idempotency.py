"""Phoenix exactly-once execution and idempotency engine.

Guarantee: At-most-once execution + at-least-once recording, and exactly-once
observable effect when the adapter can verify post-state or the external system
honors an idempotency key.
Limits: Does not claim exactly-once for arbitrary unverifiable side effects.
Idempotency guard is strictly OFF by default and requires opt-in per tool/call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .fingerprint import args_hash
from .ledger import Ledger
from .models import CallRecord, SideEffect


@dataclass
class Decision:
    """Interception decision made by the ExactlyOnce engine."""
    action: Literal["execute", "return_stored", "reconcile"]
    stored: CallRecord | None
    reason: str


class ExactlyOnce:
    """Idempotency controller determining whether a tool invocation should execute or replay."""

    def __init__(self, ledger: Ledger, enabled: bool = False) -> None:
        self.ledger = ledger
        self.enabled = enabled

    def decide(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        session_id: str,
        pre_fp: str | None,
        opt_in: bool = False,
        side_effect_class: SideEffect = SideEffect.WRITE,
        idempotency_key: str | None = None,
    ) -> Decision:
        """Decide whether to execute, return stored result, or reconcile in-flight state.

        Non-negotiable invariants:
        1. If self.enabled is False or opt_in is False -> always 'execute'.
        2. READ tool results are NEVER cached or replayed across sessions.
        3. Only matching idempotency_key AND matching pre_fp produces 'return_stored'.
        4. Pending call with matching key triggers 'reconcile'.
        """
        if not self.enabled or not opt_in:
            return Decision(
                action="execute",
                stored=None,
                reason="Idempotency guard disabled or call did not opt-in",
            )

        # Invariant 2: Never cache or replay READ tools across sessions
        if side_effect_class == SideEffect.READ or side_effect_class == "read":
            return Decision(
                action="execute",
                stored=None,
                reason="Read-only tools are never cached across sessions",
            )

        # Derive effective idempotency key if not explicitly given
        effective_key = idempotency_key
        if not effective_key:
            effective_key = f"{session_id}:{tool_name}:{args_hash(tool_name, args)}"

        # Check for committed/recovered calls with identical idempotency key
        committed = self.ledger.find_committed_by_key(effective_key)
        if committed:
            # Check pre-state fingerprint compatibility
            if committed.pre_fingerprint and pre_fp and committed.pre_fingerprint != pre_fp:
                # State drifted since original commit; must execute anew
                return Decision(
                    action="execute",
                    stored=None,
                    reason="State drift detected: pre-fingerprint does not match original call",
                )
            return Decision(
                action="return_stored",
                stored=committed,
                reason=f"Idempotent replay: matching committed call {committed.id}",
            )

        # Check for in-flight pending calls with matching key (crash window)
        pending = self.ledger.find_pending_by_key(effective_key)
        if pending:
            return Decision(
                action="reconcile",
                stored=pending,
                reason=f"In-flight pending call {pending.id} detected; requires post-state reconciliation",
            )

        return Decision(
            action="execute",
            stored=None,
            reason="No existing committed or pending call found for idempotency key",
        )
