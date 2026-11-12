"""Phoenix tool execution interception middleware.

Guarantee: Pre-call begin journaled before execution begins; post-call commit journaled
with fsync before control returns. Replays cached result if opt-in idempotency matches.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .config import PhoenixConfig
from .fingerprint import state_fingerprint
from .idempotency import ExactlyOnce
from .ledger import Ledger
from .models import CallRecord, SideEffect


class PhoenixMiddleware:
    """Interception wrapper guaranteeing flight recording and exactly-once execution."""

    def __init__(self, ledger: Ledger, config: PhoenixConfig | None = None) -> None:
        self.ledger = ledger
        self.config = config or PhoenixConfig()
        self.idempotency = ExactlyOnce(self.ledger, enabled=self.config.idempotency_enabled)

    def classify_tool(self, tool_name: str) -> SideEffect:
        """Classify a tool into READ, WRITE, or EXTERNAL."""
        lower = tool_name.lower()
        if any(w in lower for w in ["read", "get", "list", "fetch", "check", "inspect", "search"]):
            return SideEffect.READ
        if any(w in lower for w in ["charge", "pay", "stripe", "email", "sms", "tweet", "webhook", "publish"]):
            return SideEffect.EXTERNAL
        return SideEffect.WRITE

    def intercept(
        self,
        tool_name: str,
        args: dict[str, Any],
        session_id: str,
        execute_fn: Callable[[], Any],
        turn_id: str | None = None,
        opt_in_idempotency: bool = False,
        idempotency_key: str | None = None,
        state_targets: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Intercept a tool execution with journaling and idempotency check."""
        side_effect = self.classify_tool(tool_name)
        pre_fp = state_fingerprint(state_targets or []) if side_effect != SideEffect.READ else None

        # Step 1: Idempotency decision
        decision = self.idempotency.decide(
            tool_name=tool_name,
            args=args,
            session_id=session_id,
            pre_fp=pre_fp,
            opt_in=opt_in_idempotency,
            side_effect_class=side_effect,
            idempotency_key=idempotency_key,
        )

        if decision.action == "return_stored" and decision.stored:
            # Replay stored result without invoking tool
            return decision.stored.result_redacted

        # Step 2: Journal intent to SQLite WAL
        cost_cents = self.config.get_action_cost(tool_name)
        record = self.ledger.begin(
            session_id=session_id,
            turn_id=turn_id,
            tool_name=tool_name,
            args=args,
            side_effect_class=side_effect,
            idempotency_key=idempotency_key,
            pre_fingerprint=pre_fp,
            cost_cents=cost_cents,
        )

        start_time = time.perf_counter()
        try:
            # Step 3: Execute tool
            result = execute_fn()
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Step 4: Compute post-state and commit
            post_fp = state_fingerprint(state_targets or []) if side_effect != SideEffect.READ else "read_complete"
            res_dict = result if isinstance(result, dict) else {"output": str(result)}
            self.ledger.commit(
                record.id,
                post_fingerprint=post_fp,
                result=res_dict,
                duration_ms=duration_ms,
            )
            return result
        except Exception as ex:
            self.ledger.fail(record.id, error=str(ex))
            raise
