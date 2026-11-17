# Phoenix v2.0.0 — Crash-Proof Execution Journal & Recovery for Hermes

> **Transactional SQLite WAL Flight Recorder + SHA-256 State Fingerprinting + Zeller `ddmin` Wind Tunnel**  
> *Detect interrupted writes after a crash, reconcile what already landed on disk, and verify tool retry safety before deployment—with zero external runtime dependencies and zero LLM tokens spent during recovery.*

![Phoenix — Crash-Proof Execution Journal and Recovery for Hermes](docs/thumbnail.png)

[![Catalog PR #154408](https://img.shields.io/badge/Catalog%20PR-%23154408-orange.svg)](https://github.com/NousResearch/hermes-agent/pull/154408)
[![Hermes Validate](https://img.shields.io/badge/hermes%20validate-passed-brightgreen.svg)](#3-quickstart--verification)
[![Tests](https://img.shields.io/badge/tests-126%2F126%20passed-brightgreen.svg)](#3-quickstart--verification)
[![Dependencies](https://img.shields.io/badge/dependencies-0%20(stdlib%20only)-blue.svg)](#5-security--disclosure)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

```bash
# Single-command verification suite (0 external dependencies, 0 API keys):
python judge_eval.py
```

---

## 1. The Blind Window: Why Agents Corrupt State

Autonomous agents fail in the worst possible window: *after* a mutating tool side effect lands on disk or an external service, but *before* the host receives or records the outcome.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   THE BLIND WINDOW FAILURE                                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

   Agent Host                          External Service / Target Disk
        │                                           │
        ├─── (1) Dispatch write / update ──────────>│
        │                                           │
        │                                 [Mutation Commits]
        │                                           │
      [💥 SIGKILL / Power Loss / Host OOM]          │
        │                                           │
        x<─── (2) Dropped Socket / Return Dropped ──+

   WHAT HAPPENS NEXT WITHOUT PHOENIX:
   ──────────────────────────────────
   • Blind Retry: Agent reboots, sees no confirmation, re-executes write -> Duplicate mutation / corrupted file.
   • Naive /rollback: Deletes local commits while remote calls already executed -> State desynced.

   WHAT HAPPENS WITH PHOENIX:
   ──────────────────────────
   • Phoenix SQLite WAL records intent & SHA-256 pre-state fingerprint BEFORE dispatch.
   • Upon restart, the Turn-1 system prompt alert flags any interrupted in-flight ops.
   • Owner runs /recover: Phoenix reconciles disk fingerprints -> marks landed ops recovered_landed,
     and safely replays truly unstarted local/explicitly keyed ops once with 0 LLM tokens.
```

---

## 2. Core Architecture

Phoenix is a zero-dependency trust layer built strictly on the Python 3.11+ standard library:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            PHOENIX v2.0.0 RUNTIME ARCHITECTURE                                  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

  Hermes Agent Tool Execution
            │
            ▼
  ┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
  │ tool_execution         │ ───▶ │ Deterministic op_id &  │ ───▶ │ Same-Session Idemp.    │
  │ Middleware (middleware)│      │ SHA-256 Fingerprints   │      │ Guard (Opt-In, OFF def)│
  └────────────────────────┘      └────────────────────────┘      └────────────────────────┘
            │                                                                  │
            ▼                                                                  ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ Hardened SQLite WAL Ledger (journal.py)                                                │
  │ • Confined to plugin_data_dir("phoenix")/phoenix.db (mode 0600, O_EXCL, WAL/SHM 0600)  │
  │ • Auto-retention: 7 days / 10,000 rows; sensitive keys & token regexes redacted        │
  └────────────────────────────────────────────────────────────────────────────────────────┘
            ▲
            │
  ┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
  │ Owner-Only Forward     │      │ Turn-1 System Prompt   │      │ Zeller ddmin Fault     │
  │ Recovery (/recover)    │      │ Alert (phoenix_recovery│      │ Wind Tunnel & Chaos Lab│
  └────────────────────────┘      └────────────────────────┘      └────────────────────────┘
```

---

## 3. Quickstart & Verification

```bash
# 1. Install Phoenix plugin via Hermes CLI
hermes plugins install phoenix

# 2. Validate against the official Hermes plugin checker
hermes plugins validate .

# 3. Run the 4-Act crash-and-recover + Zeller ddmin rehearsal (< 1s)
python demo.py

# 4. Run the complete verification scorecard (126 unit tests, doctor checks, wind tunnel, chaos engine)
python judge_eval.py
```

---

## 4. Tools, Commands & Surfaces

### Native Model Tools (Read-Only / Diagnostic)
- `phoenix_ledger`: Inspect the execution journal (`action: status | explain | report`). Mutating/recovery actions are rejected here and restricted to human owner slash commands. Report output is confined to `plugin_data_dir("phoenix")/reports/<basename>.html`.
- `phoenix_stats`: Read-only JSON telemetry and health metrics (operation counts, idempotency guard state, SQLite WAL size, and windtunnel verdict).
- `phoenix_windtunnel`: Execute the deterministic fault-injection wind tunnel with Zeller `ddmin` trace minimization.

### Hermes Desktop & Web Dashboard Surfaces
- **Desktop SDK (`desktop/plugin.js`)**: Contributes a `/phoenix` Flight Recorder route, sidebar navigation item, right-docked WAL stream pane, live status-bar guard pill, and command-palette entry built with `@hermes/plugin-sdk`.
- **Web Dashboard (`dashboard/`)**: FastAPI `plugin_api.py` endpoints (`/status`, `/timeline`, `/windtunnel`) + React panel registered via `window.__HERMES_PLUGINS__`.

### Owner-Typed Slash Commands
- `/phoenix status`: Active ledger state and in-flight operations.
- `/phoenix explain <op_id>`: Detailed inspection of a single operation.
- `/phoenix guard on|off`: Toggle the opt-in same-session idempotency guard.
- `/phoenix windtunnel`: Run the 6-check fault-injection suite.
- `/phoenix report [path]`: Export a standalone dark-mode HTML forensic report (zero `<script>` tags).
- `/phoenix prune`: Prune expired ledger rows manually.
- `/recover`: Reconciles interrupted operations post-crash using SHA-256 pre/post target fingerprinting with 0 redundant local writes and 0 LLM calls.

---

## 5. Security & Disclosure

1. **No Model-Controlled Filesystem Paths:** The ledger lives strictly inside `plugin_data_dir("phoenix")` with `0600` file permissions on `phoenix.db`, `-wal`, and `-shm` sidecars (`O_EXCL`). Model-requested reports are confined to `plugin_data_dir("phoenix")/reports/<basename>.html`.
2. **Owner-Only Recovery:** `/recover`, `/phoenix clear`, and `/phoenix guard` are strictly restricted to human owner slash commands—never model-callable.
3. **Opt-In Same-Session Idempotency Guard:** Disabled (`OFF`) by default. When enabled, deduplication is scoped strictly to the active `session_id` and either declared file-mutating tools (verified against target state on disk) or calls providing an explicit `idempotency_key`. Read-only tools are never cached.
4. **Secret Redaction:** Values under sensitive keys (`api_key`, `token`, `secret`, `password`, `authorization`, etc.) as well as `sk-...`, `ghp_...`, `Bearer`, and `key=value` token patterns are scrubbed before persistence and readback.
5. **Ledger Disclosure:** Phoenix journals tool call arguments and results (redacted) to a local SQLite WAL ledger under `plugin_data_dir("phoenix")`, retained for 7 days / 10,000 rows (with orphan fingerprint cleanup on prune). Owner-typed `/recover` re-runs unlanded interrupted tool calls through the tool registry.
6. **Zero External Runtime Dependencies:** Pure Python 3.11+ standard library.

---

## 6. Documentation Suite

- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture, WAL protocol, and zero-LLM recovery.
- [QUICKSTART.md](QUICKSTART.md) — Quickstart guide for Hermes users and plugin developers.
- [COMPARISON.md](COMPARISON.md) — Architectural comparison vs blind retry, `/rollback`, and external orchestrators.
- [THREAT_MODEL.md](THREAT_MODEL.md) — Threat model, trust boundaries, and security invariants.

---

## License

MIT License.
