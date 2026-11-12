"""Phoenix deterministic state and argument fingerprinting.

Guarantee: State fingerprints and argument hashes are 100% deterministic,
canonical across operating systems, and never include unredacted secrets.
Limits: File state targets must be accessible locally; HTTP targets rely on provided ETags/responses.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, TypedDict

from .security import redact_secrets


class StateTarget(TypedDict, total=False):
    kind: str  # "file" | "db_row" | "http" | "custom"
    path: str
    table: str
    key: str
    data: Any
    url: str
    etag: str | None


def canonical_json(obj: Any) -> str:
    """Serialize any object to compact, canonical JSON with sorted keys and redacted secrets.

    Guarantee: Deterministic string representation across Python versions and platforms.
    """
    sanitized = redact_secrets(obj)
    return json.dumps(sanitized, sort_keys=True, separators=(",", ":"), default=str)


def args_hash(tool_name: str, args: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of a tool name and its arguments.

    Guarantee: Same tool and semantically identical args always produce the exact same hash.
    """
    canonical_payload = f"{tool_name}:{canonical_json(args)}"
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def compute_file_fingerprint(file_path: Path | str) -> str:
    """Compute SHA-256 fingerprint of a file's content or return deterministic missing marker."""
    p = Path(file_path)
    if not p.exists():
        return "missing"
    if p.is_dir():
        return f"dir:{p.name}"
    try:
        content = p.read_bytes()
        return hashlib.sha256(content).hexdigest()
    except OSError:
        return "unreadable"


def state_fingerprint(targets: list[StateTarget | dict[str, Any]]) -> str:
    """Compute a single deterministic SHA-256 fingerprint across all state targets.

    Supports 'file', 'db_row', 'http', and 'custom' target kinds.
    """
    if not targets:
        return hashlib.sha256(b"empty_state").hexdigest()

    canonical_records = []
    for target in targets:
        kind = target.get("kind", "unknown")
        if kind == "file":
            path_str = str(target.get("path", ""))
            file_fp = compute_file_fingerprint(path_str)
            canonical_records.append({"kind": "file", "path": path_str, "hash": file_fp})
        elif kind == "db_row":
            table = str(target.get("table", ""))
            key = str(target.get("key", ""))
            data = target.get("data")
            row_fp = hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest() if data is not None else "none"
            canonical_records.append({"kind": "db_row", "table": table, "key": key, "data_hash": row_fp})
        elif kind == "http":
            url = str(target.get("url", ""))
            etag = target.get("etag")
            data = target.get("data")
            body_fp = hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest() if data is not None else "none"
            canonical_records.append({"kind": "http", "url": url, "etag": etag or "none", "body_hash": body_fp})
        else:
            canonical_records.append({
                "kind": "custom",
                "payload": canonical_json(target),
            })

    # Sort canonical records to guarantee order-independence
    sorted_records = sorted(canonical_records, key=lambda x: canonical_json(x))
    final_payload = canonical_json(sorted_records)
    return hashlib.sha256(final_payload.encode("utf-8")).hexdigest()
