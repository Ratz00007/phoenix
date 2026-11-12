"""Phoenix 2.0 — The Exactly-Once Trust Layer for Autonomous Agents.

Guarantee: At-most-once execution + at-least-once recording + zero duplicate writes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Bridge top-level modules into phoenix namespace for 100% backward & forward compatibility
_parent = Path(__file__).resolve().parent.parent
_legacy_mods = (
    "journal",
    "keys",
    "report",
    "selfcheck",
    "core",
    "windtunnel",
    "commands",
    "judge_eval",
)
_specs = {}
for _mod in _legacy_mods:
    _mod_path = _parent / f"{_mod}.py"
    if _mod_path.exists():
        _spec = importlib.util.spec_from_file_location(f"phoenix.{_mod}", _mod_path)
        if _spec and _spec.loader:
            _m = importlib.util.module_from_spec(_spec)
            sys.modules[f"phoenix.{_mod}"] = _m
            _specs[_mod] = (_spec, _m)

for _mod in _legacy_mods:
    if _mod in _specs:
        _spec, _m = _specs[_mod]
        try:
            _spec.loader.exec_module(_m)
            globals()[_mod] = _m
        except Exception:
            pass

from .chaos import CrashBoundary, run_chaos_suite
from .config import PhoenixConfig, load_config
from .fingerprint import args_hash, canonical_json, state_fingerprint
from .hooks import session_start_hook
from .idempotency import Decision, ExactlyOnce
from .ledger import Ledger
from .metrics import MetricsService
from .middleware import PhoenixMiddleware
from .models import CallRecord, CallStatus, RecoveryReport, SideEffect
from .recovery import RecoveryEngine
from .security import SecurityError, confine_storage_path, redact_secrets
from .slash import phoenix_slash_command, recover_slash_command
from .tools import register_tools

__all__ = [
    "CallRecord",
    "CallStatus",
    "RecoveryReport",
    "SideEffect",
    "Ledger",
    "args_hash",
    "canonical_json",
    "state_fingerprint",
    "ExactlyOnce",
    "Decision",
    "RecoveryEngine",
    "MetricsService",
    "SecurityError",
    "confine_storage_path",
    "redact_secrets",
    "PhoenixConfig",
    "load_config",
    "CrashBoundary",
    "run_chaos_suite",
    "PhoenixMiddleware",
    "register_tools",
    "phoenix_slash_command",
    "recover_slash_command",
    "session_start_hook",
]
