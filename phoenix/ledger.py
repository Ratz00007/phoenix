"""Phoenix SQLite WAL flight recorder ledger.

Guarantee: All transitions are journaled to SQLite WAL with synchronous=FULL and fsync
before a call is marked committed. Single writer process; read-only query support.
Limits: Concurrency managed through SQLite WAL mode.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .fingerprint import args_hash, canonical_json
from .models import CallRecord, CallStatus, RecoveryReport, SideEffect
from .security import SecurityError, confine_storage_path, ensure_mode_0600, redact_secrets


class Ledger:
    """The authoritative, single-writer flight recorder for autonomous agent tool invocations."""

    def __init__(self, db_path: Path | str, base_dir: Path | str | None = None) -> None:
        raw_path = Path(db_path)
        # Check path confinement and traversal prevention
        if ".." in str(raw_path).replace("\\", "/").split("/"):
            raise SecurityError(f"Directory traversal detected in ledger path: {db_path}")

        if base_dir is not None:
            self.db_path = confine_storage_path(raw_path, base_dir)
        else:
            self.db_path = raw_path.resolve()

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None enables autocommit so PRAGMA statements can execute outside transactions
        self._conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row

        # Enforce WAL mode and FULL synchronous durability
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=FULL;")

        ensure_mode_0600(self.db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema tables, indexes, and version metadata."""
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS calls(
              id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              turn_id TEXT,
              seq INTEGER NOT NULL,
              tool_name TEXT NOT NULL,
              args_hash TEXT NOT NULL,
              args_redacted TEXT NOT NULL,
              side_effect_class TEXT NOT NULL,
              idempotency_key TEXT,
              pre_fingerprint TEXT,
              post_fingerprint TEXT,
              status TEXT NOT NULL,
              result_redacted TEXT,
              cost_cents INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              started_at TEXT NOT NULL,
              committed_at TEXT,
              duration_ms INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_calls_session ON calls(session_id, seq);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_calls_idem
              ON calls(idempotency_key) WHERE idempotency_key IS NOT NULL AND status='committed';

            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              call_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              payload_redacted TEXT NOT NULL,
              ts TEXT NOT NULL,
              fsynced INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_events_call ON events(call_id, id);

            CREATE TABLE IF NOT EXISTS recoveries(
              id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              ops_recovered INTEGER NOT NULL DEFAULT 0,
              dupes_prevented INTEGER NOT NULL DEFAULT 0,
              llm_calls_avoided INTEGER NOT NULL DEFAULT 0,
              cost_saved_cents INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL
            );
            """
        )
        cur.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1');")
        self._conn.commit()

    def _pragma(self, name: str) -> Any:
        """Query pragma value for verification."""
        cur = self._conn.cursor()
        cur.execute(f"PRAGMA {name};")
        row = cur.fetchone()
        return row[0] if row else None

    def _now(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def _next_seq(self, session_id: str) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM calls WHERE session_id = ?", (session_id,))
        return int(cur.fetchone()[0])

    def begin(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        tool_name: str,
        args: dict[str, Any],
        side_effect_class: SideEffect,
        idempotency_key: str | None,
        pre_fingerprint: str | None,
        cost_cents: int = 0,
    ) -> CallRecord:
        """Begin journaling a tool invocation.

        Persists a PENDING record and journals begin + pre_state events with fsync.
        """
        call_id = str(uuid.uuid4())
        seq = self._next_seq(session_id)
        started_at = self._now()
        a_hash = args_hash(tool_name, args)
        a_redacted = redact_secrets(args)
        a_redacted_json = canonical_json(a_redacted)

        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO calls (
              id, session_id, turn_id, seq, tool_name, args_hash, args_redacted,
              side_effect_class, idempotency_key, pre_fingerprint, status,
              cost_cents, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call_id,
                session_id,
                turn_id,
                seq,
                tool_name,
                a_hash,
                a_redacted_json,
                side_effect_class.value if isinstance(side_effect_class, SideEffect) else str(side_effect_class),
                idempotency_key,
                pre_fingerprint,
                CallStatus.PENDING.value,
                cost_cents,
                started_at,
            ),
        )

        # Journal begin event
        cur.execute(
            """
            INSERT INTO events (call_id, event_type, payload_redacted, ts, fsynced)
            VALUES (?, 'begin', ?, ?, 1)
            """,
            (call_id, a_redacted_json, started_at),
        )

        # Journal pre_state event if fingerprint provided
        if pre_fingerprint:
            cur.execute(
                """
                INSERT INTO events (call_id, event_type, payload_redacted, ts, fsynced)
                VALUES (?, 'pre_state', ?, ?, 1)
                """,
                (call_id, canonical_json({"pre_fingerprint": pre_fingerprint}), started_at),
            )

        self._conn.commit()

        return CallRecord(
            id=call_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            tool_name=tool_name,
            args_hash=a_hash,
            args_redacted=a_redacted,
            side_effect_class=side_effect_class,
            idempotency_key=idempotency_key,
            pre_fingerprint=pre_fingerprint,
            post_fingerprint=None,
            status=CallStatus.PENDING,
            result_redacted=None,
            cost_cents=cost_cents,
            error=None,
            started_at=started_at,
            committed_at=None,
            duration_ms=None,
        )

    def commit(
        self,
        call_id: str,
        *,
        post_fingerprint: str,
        result: dict[str, Any] | None,
        duration_ms: int,
    ) -> None:
        """Commit an executed tool call with post-state fingerprint and fsynced event journal."""
        committed_at = self._now()
        res_redacted = redact_secrets(result) if result is not None else None
        res_json = canonical_json(res_redacted) if res_redacted is not None else None

        cur = self._conn.cursor()

        # Append post_state event
        cur.execute(
            """
            INSERT INTO events (call_id, event_type, payload_redacted, ts, fsynced)
            VALUES (?, 'post_state', ?, ?, 1)
            """,
            (call_id, canonical_json({"post_fingerprint": post_fingerprint}), committed_at),
        )

        # Update calls table
        cur.execute(
            """
            UPDATE calls SET
              post_fingerprint = ?,
              status = ?,
              result_redacted = ?,
              committed_at = ?,
              duration_ms = ?
            WHERE id = ?
            """,
            (post_fingerprint, CallStatus.COMMITTED.value, res_json, committed_at, duration_ms, call_id),
        )

        # Append final commit event
        cur.execute(
            """
            INSERT INTO events (call_id, event_type, payload_redacted, ts, fsynced)
            VALUES (?, 'commit', ?, ?, 1)
            """,
            (call_id, canonical_json({"duration_ms": duration_ms}), committed_at),
        )

        self._conn.commit()

    def fail(self, call_id: str, *, error: str) -> None:
        """Mark a call as failed and journal failure event."""
        failed_at = self._now()
        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE calls SET
              status = ?,
              error = ?
            WHERE id = ?
            """,
            (CallStatus.FAILED.value, error, call_id),
        )
        cur.execute(
            """
            INSERT INTO events (call_id, event_type, payload_redacted, ts, fsynced)
            VALUES (?, 'failed', ?, ?, 1)
            """,
            (call_id, canonical_json({"error": error}), failed_at),
        )
        self._conn.commit()

    def mark_recovered(self, call_id: str, *, post_fingerprint: str, result: dict[str, Any] | None = None) -> None:
        """Mark a previously pending call as RECOVERED after post-state verification."""
        recovered_at = self._now()
        res_json = canonical_json(redact_secrets(result)) if result is not None else None
        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE calls SET
              status = ?,
              post_fingerprint = ?,
              result_redacted = COALESCE(?, result_redacted),
              committed_at = ?
            WHERE id = ?
            """,
            (CallStatus.RECOVERED.value, post_fingerprint, res_json, recovered_at, call_id),
        )
        cur.execute(
            """
            INSERT INTO events (call_id, event_type, payload_redacted, ts, fsynced)
            VALUES (?, 'recover_end', ?, ?, 1)
            """,
            (call_id, canonical_json({"action": "recovered", "post_fingerprint": post_fingerprint}), recovered_at),
        )
        self._conn.commit()

    def append_event(self, call_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Append an arbitrary lifecycle or crash marker event to the journal."""
        ts = self._now()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO events (call_id, event_type, payload_redacted, ts, fsynced)
            VALUES (?, ?, ?, ?, 1)
            """,
            (call_id, event_type, canonical_json(payload), ts),
        )
        self._conn.commit()

    def find_committed_by_key(self, key: str) -> CallRecord | None:
        """Look up a committed or recovered call record by its idempotency key."""
        if not key:
            return None
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM calls
            WHERE idempotency_key = ? AND status IN ('committed', 'recovered')
            ORDER BY seq DESC LIMIT 1
            """,
            (key,),
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def find_pending_by_key(self, key: str) -> CallRecord | None:
        """Look up a pending call record by its idempotency key."""
        if not key:
            return None
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT * FROM calls
            WHERE idempotency_key = ? AND status = 'pending'
            ORDER BY seq DESC LIMIT 1
            """,
            (key,),
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def get(self, call_id: str) -> CallRecord | None:
        """Fetch a single call record by UUID."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM calls WHERE id = ?", (call_id,))
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def pending_calls(self, session_id: str | None = None) -> list[CallRecord]:
        """Return all calls currently in PENDING state."""
        cur = self._conn.cursor()
        if session_id:
            cur.execute("SELECT * FROM calls WHERE session_id = ? AND status = 'pending' ORDER BY seq ASC", (session_id,))
        else:
            cur.execute("SELECT * FROM calls WHERE status = 'pending' ORDER BY seq ASC")
        return [self._row_to_record(r) for r in cur.fetchall()]

    def query(
        self,
        *,
        session_id: str | None = None,
        limit: int = 500,
        offset: int = 0,
        status: CallStatus | None = None,
    ) -> list[CallRecord]:
        """Read-only query API for UI and dashboard timelines."""
        cur = self._conn.cursor()
        clauses = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if status:
            clauses.append("status = ?")
            params.append(status.value if isinstance(status, CallStatus) else str(status))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM calls {where} ORDER BY seq DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cur.execute(sql, tuple(params))
        return [self._row_to_record(r) for r in cur.fetchall()]

    def events(self, call_id: str) -> list[dict[str, Any]]:
        """Return full timeline of journaled events for a given call."""
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM events WHERE call_id = ? ORDER BY id ASC", (call_id,))
        out = []
        for row in cur.fetchall():
            out.append({
                "id": row["id"],
                "call_id": row["call_id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_redacted"]),
                "ts": row["ts"],
                "fsynced": bool(row["fsynced"]),
            })
        return out

    def start_recovery(self, session_id: str) -> str:
        """Log initiation of forward recovery session."""
        rec_id = str(uuid.uuid4())
        started_at = self._now()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO recoveries (id, session_id, started_at, status)
            VALUES (?, ?, ?, 'running')
            """,
            (rec_id, session_id, started_at),
        )
        self._conn.commit()
        return rec_id

    def finish_recovery(self, recovery_id: str, report: RecoveryReport) -> None:
        """Mark recovery session completed with recorded metrics."""
        finished_at = self._now()
        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE recoveries SET
              finished_at = ?,
              ops_recovered = ?,
              dupes_prevented = ?,
              llm_calls_avoided = ?,
              cost_saved_cents = ?,
              status = 'done'
            WHERE id = ?
            """,
            (
                finished_at,
                report.ops_recovered,
                report.dupes_prevented,
                report.llm_calls_avoided,
                report.cost_saved_cents,
                recovery_id,
            ),
        )
        self._conn.commit()

    def counters(self) -> dict[str, int]:
        """Aggregate value metrics across all sessions."""
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT
              COALESCE(SUM(dupes_prevented), 0) AS total_dupes_prevented,
              COALESCE(SUM(ops_recovered), 0) AS total_ops_recovered,
              COALESCE(SUM(llm_calls_avoided), 0) AS total_llm_calls_avoided,
              COALESCE(SUM(cost_saved_cents), 0) AS total_cost_saved_cents
            FROM recoveries
            """
        )
        rec_row = cur.fetchone()

        # Calculate cost saved: sum from recoveries or recovered calls
        cur.execute("SELECT COALESCE(SUM(cost_cents), 0) FROM calls WHERE status = 'recovered'")
        rec_cost_row = cur.fetchone()

        dupes_prev = int(rec_row["total_dupes_prevented"]) if rec_row else 0
        ops_rec = int(rec_row["total_ops_recovered"]) if rec_row else 0
        llm_avoided = int(rec_row["total_llm_calls_avoided"]) if rec_row else 0
        recovery_cost_saved = int(rec_row["total_cost_saved_cents"]) if rec_row else 0
        call_cost_saved = int(rec_cost_row[0]) if rec_cost_row else 0

        cost_saved = max(recovery_cost_saved, call_cost_saved)

        return {
            "dupes_prevented": dupes_prev,
            "ops_recovered": ops_rec,
            "llm_calls_avoided": llm_avoided,
            "cost_saved_cents": cost_saved,
        }

    def _row_to_record(self, row: sqlite3.Row) -> CallRecord:
        res_json = row["result_redacted"]
        res = json.loads(res_json) if res_json else None
        args_json = row["args_redacted"]
        args = json.loads(args_json) if args_json else {}

        return CallRecord(
            id=row["id"],
            session_id=row["session_id"],
            turn_id=row["turn_id"],
            seq=int(row["seq"]),
            tool_name=row["tool_name"],
            args_hash=row["args_hash"],
            args_redacted=args,
            side_effect_class=SideEffect(row["side_effect_class"]),
            idempotency_key=row["idempotency_key"],
            pre_fingerprint=row["pre_fingerprint"],
            post_fingerprint=row["post_fingerprint"],
            status=CallStatus(row["status"]),
            result_redacted=res,
            cost_cents=int(row["cost_cents"]),
            error=row["error"],
            started_at=row["started_at"],
            committed_at=row["committed_at"],
            duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
        )

    def close(self) -> None:
        """Close SQLite database connection safely."""
        try:
            self._conn.close()
        except Exception:
            pass
