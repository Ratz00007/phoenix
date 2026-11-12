"""Phoenix shared data types and contract models.

Guarantee: Pure data structures with complete immutability where required.
Limits: Enforces schema types; does not perform I/O or database operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class SideEffect(str, Enum):
    """Classification of tool call side effect semantics."""
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"


class CallStatus(str, Enum):
    """Lifecycle state of a tool call in the flight recorder."""
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class CallRecord:
    """Immutable flight recorder record of a single intercepted tool invocation."""
    id: str
    session_id: str
    turn_id: str | None
    seq: int
    tool_name: str
    args_hash: str
    args_redacted: dict[str, Any]
    side_effect_class: SideEffect
    idempotency_key: str | None
    pre_fingerprint: str | None
    post_fingerprint: str | None
    status: CallStatus
    result_redacted: dict[str, Any] | None
    cost_cents: int
    error: str | None
    started_at: str
    committed_at: str | None
    duration_ms: int | None


@dataclass
class RecoveryReport:
    """Summary report produced by zero-LLM forward crash recovery."""
    ops_recovered: int = 0
    dupes_prevented: int = 0
    llm_calls_avoided: int = 0
    cost_saved_cents: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


SideEffectClass = Literal["read", "write", "external"]
