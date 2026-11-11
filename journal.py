"""Durable WAL ledger of agent side effects.

One row per tool *attempt*. An operation is identified by its idempotency key
(``op_id``); ``attempt_id`` distinguishes repeated executions of the same op.

Lifecycle of a row:
    intent  ->  ok | error          (normal completion)
    intent  ->  (process dies)      (crash: row stays "intent" = in-flight)
    intent  ->  resumed             (a later /resume replayed it exactly once)
    intent  ->  recovered_landed    (target was already modified before crash)
    intent  ->  deduped             (skipped execution due to idempotency guard)
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_REDACT_KV_RE = re.compile(
    r'("(?:api[_-]?key|token|secret|password|passwd|auth|authorization|access[_-]?token|refresh[_-]?token|bearer)"\s*:\s*)"(?:[^"\\]|\\.)*"',
    re.IGNORECASE,
)
_REDACT_KV_NONSTR_RE = re.compile(
    r'("(?:api[_-]?key|token|secret|password|passwd|auth|authorization|access[_-]?token|refresh[_-]?token|bearer)"\s*:\s*)[^\s,}\]]+',
    re.IGNORECASE,
)
_REDACT_SK_RE = re.compile(r'\bsk-[a-zA-Z0-9_\-]{8,}\b')
_REDACT_GHP_RE = re.compile(r'\bghp[_-][a-zA-Z0-9]{8,}\b')
_REDACT_BEARER_RE = re.compile(r'\b(Bearer\s+)[a-zA-Z0-9_\-\.]{8,}\b', re.IGNORECASE)


def redact_secrets(val: Any) -> str | None:
    """Redact sensitive credentials, auth headers, API keys, and tokens."""
    if val is None:
        return None
    if isinstance(val, str):
        s = val
    else:
        try:
            s = json.dumps(val, default=str)
        except Exception:
            s = str(val)

    s = _REDACT_KV_RE.sub(r'\1"[REDACTED]"', s)
    s = _REDACT_KV_NONSTR_RE.sub(r'\1"[REDACTED]"', s)
    s = _REDACT_SK_RE.sub('[REDACTED]', s)
    s = _REDACT_GHP_RE.sub('[REDACTED]', s)
    s = _REDACT_BEARER_RE.sub(r'\1[REDACTED]', s)
    return s


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ops (
    attempt_id  TEXT PRIMARY KEY,
    op_id       TEXT NOT NULL,
    tool        TEXT NOT NULL,
    args_json   TEXT NOT NULL,
    status      TEXT NOT NULL,             -- intent | ok | error | resumed | deduped | recovered_landed
    result_json TEXT,
    error       TEXT,
    session_id  TEXT,
    turn_id     TEXT,
    tool_call_id TEXT,
    pre_fp_json TEXT,
    ts_intent   REAL NOT NULL,
    ts_done     REAL
);
CREATE INDEX IF NOT EXISTS idx_ops_op_id ON ops(op_id);
CREATE INDEX IF NOT EXISTS idx_ops_status ON ops(status);
CREATE INDEX IF NOT EXISTS idx_ops_ts_intent ON ops(ts_intent);
CREATE INDEX IF NOT EXISTS idx_ops_session_id ON ops(session_id);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    val TEXT NOT NULL
);
"""


class Journal:
    """SQLite (WAL) ledger. Thread-safe; every write is committed immediately."""

    def __init__(self, data_dir, db_path: str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # db_path override is a test/dev affordance ("file" -> ":memory:"); the
        # production path is always the on-disk WAL file under plugin_data_dir.
        self.db_path = db_path or str(self.data_dir / "phoenix.db")
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            if self.db_path != ":memory:":
                try:
                    if os.path.exists(self.db_path):
                        os.chmod(self.db_path, 0o600)
                except Exception:
                    pass
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            try:
                self._conn.execute("ALTER TABLE ops ADD COLUMN pre_fp_json TEXT")
            except sqlite3.OperationalError:
                pass
            if self.db_path != ":memory:":
                try:
                    self.prune(max_age_days=7, max_rows=10000)
                except Exception:
                    pass
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                if self.db_path != ":memory:":
                    try:
                        self.prune(max_age_days=7, max_rows=10000)
                    except Exception:
                        pass
                self._conn.close()
                self._conn = None

    # -- writes -------------------------------------------------------------

    def record_intent(
        self,
        attempt_id,
        op_id,
        tool,
        args,
        session_id=None,
        turn_id=None,
        tool_call_id=None,
        pre_fp=None,
    ) -> None:
        with self._lock:
            c = self._connect()
            pre_fp_json = json.dumps(pre_fp, default=str) if pre_fp is not None else None
            args_json = redact_secrets(args) or "{}"
            c.execute(
                "INSERT OR IGNORE INTO ops (attempt_id, op_id, tool, args_json, status, "
                "session_id, turn_id, tool_call_id, pre_fp_json, ts_intent) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    op_id,
                    tool,
                    args_json,
                    "intent",
                    session_id,
                    turn_id,
                    tool_call_id,
                    pre_fp_json,
                    time.time(),
                ),
            )
            c.commit()

    def record_outcome(self, attempt_id, op_id, status, result=None, error=None) -> None:
        with self._lock:
            c = self._connect()
            result_json = redact_secrets(result)
            error_clean = redact_secrets(error) if error else None
            c.execute(
                "UPDATE ops SET status=?, result_json=?, error=?, ts_done=? "
                "WHERE attempt_id=? AND op_id=?",
                (
                    status,
                    result_json,
                    error_clean,
                    time.time(),
                    attempt_id,
                    op_id,
                ),
            )
            c.commit()

    def mark_resumed(self, attempt_id, result=None, error=None, status: str = "resumed") -> None:
        with self._lock:
            c = self._connect()
            result_json = redact_secrets(result)
            error_clean = redact_secrets(error) if error else None
            c.execute(
                "UPDATE ops SET status=?, result_json=?, error=?, ts_done=? "
                "WHERE attempt_id=?",
                (
                    status,
                    result_json,
                    error_clean,
                    time.time(),
                    attempt_id,
                ),
            )
            c.commit()

    def clear_in_flight(self, reason: str = "cleared") -> None:
        """Mark all intent rows as errors (a deliberate, recorded give-up)."""
        with self._lock:
            c = self._connect()
            c.execute(
                "UPDATE ops SET status='error', error=?, ts_done=? WHERE status='intent'",
                (reason, time.time()),
            )
            c.commit()

    def set_meta(self, key: str, val: str) -> None:
        with self._lock:
            c = self._connect()
            c.execute(
                "INSERT OR REPLACE INTO meta (key, val) VALUES (?, ?)",
                (key, str(val)),
            )
            c.commit()

    # -- reads --------------------------------------------------------------

    def get_meta(self, key: str, default: str = "") -> str:
        row = self._connect().execute(
            "SELECT val FROM meta WHERE key=?",
            (key,),
        ).fetchone()
        return row[0] if row else default

    def latest_outcome(self, op_id):
        return self._connect().execute(
            "SELECT status, result_json, error FROM ops "
            "WHERE op_id=? AND status IN ('ok','error','resumed','recovered_landed','deduped') "
            "ORDER BY ts_done DESC LIMIT 1",
            (op_id,),
        ).fetchone()

    def latest_success(self, op_id: str, session_id: str | None = None) -> tuple[str, str | None] | None:
        if session_id:
            return self._connect().execute(
                "SELECT status, result_json FROM ops "
                "WHERE op_id=? AND session_id=? AND status IN ('ok','resumed','recovered_landed') "
                "ORDER BY ts_done DESC LIMIT 1",
                (op_id, session_id),
            ).fetchone()
        return self._connect().execute(
            "SELECT status, result_json FROM ops "
            "WHERE op_id=? AND (session_id IS NULL OR session_id='') AND status IN ('ok','resumed','recovered_landed') "
            "ORDER BY ts_done DESC LIMIT 1",
            (op_id,),
        ).fetchone()

    def in_flight(self):
        return self._connect().execute(
            "SELECT attempt_id, op_id, tool, args_json, session_id, turn_id, ts_intent "
            "FROM ops WHERE status='intent' ORDER BY ts_intent",
        ).fetchall()

    def get(self, attempt_id):
        return self._connect().execute(
            "SELECT attempt_id, op_id, tool, args_json, status, result_json, error, "
            "session_id, turn_id, tool_call_id, ts_intent, ts_done FROM ops WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()

    def find(self, target):
        """Return the full row for an attempt_id or op_id (in-flight rows first)."""
        return self._connect().execute(
            "SELECT attempt_id, op_id, tool, args_json, status, result_json, error, "
            "session_id, turn_id, tool_call_id, ts_intent, ts_done FROM ops "
            "WHERE attempt_id=? OR op_id=? ORDER BY (status='intent') DESC, ts_intent DESC LIMIT 1",
            (target, target),
        ).fetchone()

    def get_pre_fp(self, attempt_id) -> dict | None:
        row = self._connect().execute(
            "SELECT pre_fp_json FROM ops WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, ValueError):
            return None

    def latest_pre_fp(self, op_id: str, session_id: str | None = None) -> dict | None:
        if session_id:
            row = self._connect().execute(
                "SELECT pre_fp_json FROM ops WHERE op_id = ? AND session_id = ? AND pre_fp_json IS NOT NULL ORDER BY ts_intent DESC LIMIT 1",
                (op_id, session_id),
            ).fetchone()
        else:
            row = self._connect().execute(
                "SELECT pre_fp_json FROM ops WHERE op_id = ? AND (session_id IS NULL OR session_id='') AND pre_fp_json IS NOT NULL ORDER BY ts_intent DESC LIMIT 1",
                (op_id,),
            ).fetchone()
        if not row or not row[0]:
            return None
        try:
            val = json.loads(row[0])
            return val if isinstance(val, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    def prune(self, max_age_days: int = 7, max_rows: int = 10000) -> int:
        """Prune ops older than max_age_days or exceeding max_rows (excluding in-flight rows)."""
        with self._lock:
            c = self._connect()
            cutoff_ts = time.time() - (max_age_days * 86400)
            cursor = c.execute(
                "DELETE FROM ops WHERE status != 'intent' AND ("
                "  ts_intent < ? OR attempt_id NOT IN ("
                "    SELECT attempt_id FROM ops ORDER BY ts_intent DESC LIMIT ?"
                "  )"
                ")",
                (cutoff_ts, max(1, max_rows)),
            )
            deleted = cursor.rowcount if cursor.rowcount > 0 else 0
            if deleted > 0:
                c.commit()
            return deleted

    def recent(self, limit: int = 25) -> list[dict]:
        rows = self._connect().execute(
            "SELECT attempt_id, op_id, tool, args_json, status, result_json, error, "
            "session_id, turn_id, ts_intent, ts_done FROM ("
            "  SELECT attempt_id, op_id, tool, args_json, status, result_json, error, "
            "  session_id, turn_id, ts_intent, ts_done, rowid FROM ops "
            "  ORDER BY ts_intent DESC, rowid DESC LIMIT ?"
            ") ORDER BY ts_intent ASC, rowid ASC",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            args = None
            if r[3]:
                try:
                    args = json.loads(r[3])
                except Exception:
                    args = r[3]
            res = None
            if r[5] is not None:
                try:
                    res = json.loads(r[5])
                except Exception:
                    res = r[5]
            out.append({
                "attempt_id": r[0],
                "op_id": r[1],
                "tool": r[2],
                "args": args,
                "status": r[4],
                "result": res,
                "error": r[6],
                "session_id": r[7],
                "turn_id": r[8],
                "ts_intent": r[9],
                "ts_done": r[10],
            })
        return out

    def stats(self) -> dict:
        c = self._connect()
        total = c.execute("SELECT COUNT(*) FROM ops WHERE attempt_id NOT LIKE '%_recov'").fetchone()[0]
        committed = c.execute(
            "SELECT COUNT(*) FROM ops WHERE status IN ('ok','resumed','recovered_landed') AND attempt_id NOT LIKE '%_recov'"
        ).fetchone()[0]
        errors = c.execute("SELECT COUNT(*) FROM ops WHERE status='error' AND attempt_id NOT LIKE '%_recov'").fetchone()[0]
        in_flight = c.execute("SELECT COUNT(*) FROM ops WHERE status='intent'").fetchone()[0]
        deduped = c.execute("SELECT COUNT(*) FROM ops WHERE status='deduped' AND attempt_id NOT LIKE '%_recov'").fetchone()[0]
        recovered_landed = c.execute(
            "SELECT COUNT(*) FROM ops WHERE status='recovered_landed' AND attempt_id NOT LIKE '%_recov'"
        ).fetchone()[0]
        return {
            "total": total,
            "committed": committed,
            "errors": errors,
            "in_flight": in_flight,
            "deduped": deduped,
            "recovered_landed": recovered_landed,
        }
