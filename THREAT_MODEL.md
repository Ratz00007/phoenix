# Phoenix v2.0.0 Threat Model & Security Invariants

Phoenix is engineered under strict least-privilege assumptions for autonomous agents handling real filesystems and external APIs.

---

## 1. Core Security Guarantees

1. **No Model-Controlled Filesystem Paths**
   - The SQLite WAL ledger (`phoenix.db`) lives strictly inside `plugin_data_dir("phoenix")`.
   - Model-requested HTML reports via `phoenix_ledger(action="report")` accept only a bare basename (rejecting `/`, `\`, `..`) and write strictly inside `plugin_data_dir("phoenix")/reports/<basename>.html`.

2. **Owner-Only Recovery & Mutations (No Model-Callable Replay)**
   - `recover`, `clear`, `guard_on`, and `guard_off` are **explicitly blocked** in `phoenix_ledger` and restricted to human owner slash commands (`/recover` and `/phoenix <action>`).
   - The LLM cannot replay prior sessions' tool calls without the user typing `/recover`.

3. **Opt-In Same-Session Idempotency Guard**
   - The idempotency guard is **OFF by default** (`guard=OFF`).
   - When enabled via `/phoenix guard on`, deduplication only activates within the exact same non-empty `session_id` for declared mutating tools or calls with an explicit `idempotency_key`, verified against target state on disk.
   - Read-only tools are never cached across sessions.

4. **Hardened Storage at Rest (`0600`, `O_EXCL`, Retention)**
   - `phoenix.db` is created atomically with `O_EXCL` and `0600` permissions; `-wal` and `-shm` sidecars are hardened to `0600` on every open and checkpoint.
   - Automatic retention pruning limits stored rows to **7 days / 10,000 rows** (preserving in-flight rows).

5. **Secret Redaction & Zero Network Calls**
   - Regex sanitization scrubs API keys (`sk-...`, `ghp_...`, Bearer tokens, auth secrets) from arguments and results before persistence or HTML report rendering.
   - Generated HTML reports contain zero `<script>` tags.
   - Zero external runtime dependencies (Python 3.11+ stdlib only) and zero network calls.
