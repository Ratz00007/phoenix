"""Phoenix external service idempotency adapters.

Guarantee: Enforce exactly-once semantics for payment, messaging, and database operations.
"""

from __future__ import annotations

from .email import EmailAdapter
from .sql import SQLAdapter
from .stripe import StripeAdapter

__all__ = ["StripeAdapter", "EmailAdapter", "SQLAdapter"]
