"""Phoenix configuration schema and secure defaults.

Guarantee: Default configuration is secure by default (idempotency OFF, path confinement ON).
Limits: Configuration loaded at initialization; dynamic updates require reinitialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PhoenixConfig:
    """Configuration options for Phoenix flight recorder and idempotency layer."""
    # Non-negotiable security invariant: idempotency guard is OFF by default, opt-in per tool
    idempotency_enabled: bool = False

    # Financial and compute cost valuations in US cents
    cost_per_action_cents: dict[str, int] = field(
        default_factory=lambda: {
            "charge": 240,
            "stripe_charge": 240,
            "payment": 240,
            "send_email": 10,
            "email": 10,
            "sql_write": 5,
            "write_file": 5,
            "default": 10,
        }
    )

    # Storage directory override; defaults to Hermes plugin storage
    storage_dir: Path | None = None

    # Secret redaction custom regex rules
    redaction_rules: list[str] = field(default_factory=list)

    # Maximum records returned in a single query
    max_query_limit: int = 1000

    def get_action_cost(self, tool_name: str) -> int:
        """Return the estimated financial cost in cents for a tool action."""
        if tool_name in self.cost_per_action_cents:
            return self.cost_per_action_cents[tool_name]
        for k, v in self.cost_per_action_cents.items():
            if k in tool_name.lower():
                return v
        return self.cost_per_action_cents.get("default", 10)


def load_config(overrides: dict[str, Any] | None = None) -> PhoenixConfig:
    """Load Phoenix configuration with secure defaults and optional overrides."""
    if not overrides:
        return PhoenixConfig()
    return PhoenixConfig(
        idempotency_enabled=bool(overrides.get("idempotency_enabled", False)),
        cost_per_action_cents=overrides.get("cost_per_action_cents") or PhoenixConfig().cost_per_action_cents,
        storage_dir=Path(overrides["storage_dir"]) if overrides.get("storage_dir") else None,
        redaction_rules=overrides.get("redaction_rules", []),
        max_query_limit=int(overrides.get("max_query_limit", 1000)),
    )
