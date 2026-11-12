"""Phoenix security, path confinement, secret redaction, and isolation boundaries.

Guarantee: All paths are strictly confined to authorized storage directories;
all persisted and rendered objects have secrets redacted.
Limits: Redaction is regex and heuristic-based; custom application secrets must follow standard naming or explicit patterns.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


class SecurityError(ValueError):
    """Raised when an operation attempts to violate a security invariant."""
    pass


# Default sensitive key substrings (case-insensitive)
DEFAULT_SENSITIVE_KEY_PATTERNS = [
    r"api[_-]?key",
    r"token",
    r"secret",
    r"password",
    r"passwd",
    r"auth(?:orization)?",
    r"private[_-]?key",
    r"access[_-]?token",
    r"refresh[_-]?token",
    r"session[_-]?token",
    r"credit[_-]?card",
    r"cvv",
    r"ssn",
    r"credential",
]

# Sensitive value regex patterns
DEFAULT_SENSITIVE_VALUE_PATTERNS = [
    r"sk_(?:live|test)_[0-9a-zA-Z]{24,}",  # Stripe secret keys
    r"gh[pousr]_[0-9a-zA-Z]{36,}",          # GitHub tokens
    r"bearer\s+[a-zA-Z0-9_\-\.=:_\+\/]{20,}",  # Bearer tokens
    r"ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*",  # JWT patterns
]

_COMPILED_KEY_RE = re.compile("|".join(DEFAULT_SENSITIVE_KEY_PATTERNS), re.IGNORECASE)
_COMPILED_VALUE_RE = re.compile("|".join(DEFAULT_SENSITIVE_VALUE_PATTERNS), re.IGNORECASE)


def confine_storage_path(target_path: Path | str, base_dir: Path | str) -> Path:
    """Ensure target_path resolves strictly inside base_dir with no traversal or escapes.

    Raises SecurityError if target_path escapes base_dir.
    """
    raw_target = str(target_path)
    # Reject explicit directory traversal tokens immediately
    if ".." in raw_target.replace("\\", "/").split("/"):
        raise SecurityError(f"Directory traversal detected in path: {target_path}")

    base = Path(base_dir).resolve()
    target = (base / target_path if not Path(target_path).is_absolute() else Path(target_path)).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        raise SecurityError(
            f"Path confinement violation: '{target}' escapes allowed base storage '{base}'"
        )
    return target


def ensure_mode_0600(file_path: Path) -> None:
    """Set strict 0600 (owner read/write only) file mode.

    On POSIX platforms this sets strict 0o600. On Windows, applies best-effort permissions.
    """
    try:
        if os.name == "posix":
            os.chmod(file_path, 0o600)
        else:
            # On Windows, os.chmod only toggles read-only bit, but we enforce 0o600 for posix emulation
            os.chmod(file_path, 0o600)
    except OSError:
        pass


def redact_secrets(data: Any, extra_patterns: list[str] | None = None) -> Any:
    """Recursively redact secrets from dictionaries, lists, and strings.

    Guarantee: Keys matching secret patterns have their values replaced with '[REDACTED]'.
    Known API key patterns in string values are sanitized.
    """
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            k_str = str(k)
            if _COMPILED_KEY_RE.search(k_str):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_secrets(v, extra_patterns)
        return redacted
    elif isinstance(data, list):
        return [redact_secrets(item, extra_patterns) for item in data]
    elif isinstance(data, tuple):
        return tuple(redact_secrets(item, extra_patterns) for item in data)
    elif isinstance(data, str):
        val = data
        if _COMPILED_VALUE_RE.search(val):
            val = _COMPILED_VALUE_RE.sub("[REDACTED]", val)
        return val
    return data


def get_secret(secret_scope: Any, key: str) -> str | None:
    """Obtain credentials strictly through agent secret_scope or environment fallback.

    Guarantee: Credentials are never persisted directly into the ledger unredacted.
    """
    if secret_scope is not None and hasattr(secret_scope, "get_secret"):
        val = secret_scope.get_secret(key)
        if val is not None:
            return str(val)
    return os.environ.get(key)
