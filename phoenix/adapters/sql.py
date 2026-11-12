"""Phoenix SQL database adapter with idempotent upserts and row fingerprinting.

Guarantee: Atomic upsert operations with unique business keys; crashes mid-write
yield exactly one row and deterministic row fingerprints.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..fingerprint import canonical_json, state_fingerprint


class SQLAdapter:
    """Relational SQL adapter providing idempotent upsert and state fingerprint verification."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(
        self,
        table: str,
        key_column: str,
        key_value: Any,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Perform atomic upsert keyed on key_column.

        Guarantee: Duplicate execution overwrites or maintains exactly one record with key_value.
        """
        cols = [key_column] + [k for k in data.keys() if k != key_column]
        placeholders = ", ".join(["?"] * len(cols))
        vals = [key_value] + [data[k] for k in cols[1:]]

        update_assignments = ", ".join([f"{col} = excluded.{col}" for col in cols[1:]])
        if update_assignments:
            sql = f"""
            INSERT INTO {table} ({", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT({key_column}) DO UPDATE SET {update_assignments}
            """
        else:
            sql = f"""
            INSERT OR IGNORE INTO {table} ({", ".join(cols)})
            VALUES ({placeholders})
            """

        self.conn.execute(sql, vals)
        self.conn.commit()

        # Compute post-state row fingerprint
        cur = self.conn.cursor()
        cur.execute(f"SELECT * FROM {table} WHERE {key_column} = ?", (key_value,))
        row = cur.fetchone()
        row_dict = dict(zip([c[0] for c in cur.description], row)) if row else {}
        post_fp = state_fingerprint([{"kind": "db_row", "table": table, "key": str(key_value), "data": row_dict}])

        return {
            "table": table,
            "key": key_value,
            "status": "upserted",
            "post_fingerprint": post_fp,
            "row": row_dict,
        }

    def verify_row(self, table: str, key_column: str, key_value: Any) -> tuple[bool, str | None]:
        """Verify whether a row exists and return its state fingerprint."""
        cur = self.conn.cursor()
        cur.execute(f"SELECT * FROM {table} WHERE {key_column} = ?", (key_value,))
        row = cur.fetchone()
        if not row:
            return False, None
        row_dict = dict(zip([c[0] for c in cur.description], row))
        fp = state_fingerprint([{"kind": "db_row", "table": table, "key": str(key_value), "data": row_dict}])
        return True, fp
