# Phoenix — The Black Box Flight Recorder for Hermes Agents

> ### **Kill your agent mid-write. It recovers having executed exactly once.**
> Zero duplicate writes. Zero lost operations. Zero LLM calls during recovery.

[![Hermes Validation](https://img.shields.io/badge/hermes%20validate-14%2F14%20passed-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/tests-67%2F67%20passed-brightgreen.svg)]()
[![Dependencies](https://img.shields.io/badge/dependencies-0%20(stdlib%20only)-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

```bash
# Instant 1-second verification for judges (0 deps, 0 API keys):
python judge_eval.py
```

---

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           PHOENIX BLACK BOX FLIGHT RECORDER TIMELINE                            │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

 NORMAL RUNTIME                       TOOL EXECUTION                          CRASH WINDOW
 ──────────────                       ──────────────                          ────────────
  Agent Turn ───▶ [tool_call] ───▶ [1. Journal Intent] ───▶ [2. Dispatch Tool] ───▶ [SIGKILL / OOM]
                                            │                         │                │
                                     - Compute op_id           - Write to disk /       │
                                     - SHA-256 pre_fp            API commit            │
                                     - Commit to WAL                                   ▼
                                                                                PROCESS TERMINATES
                                                                                (Mid-Turn Amnesia)
 ─────────────────────────────────────────────────────────────────────────────────────────────────
 REBOOT & RECOVERY                    STATE FINGERPRINTING                    FORWARD RECONCILIATION
 ─────────────────                    ────────────────────                    ──────────────────────
  Hermes Boots ──▶ [Turn-1 Crash] ───▶ [Inspect SQLite WAL] ───▶ [Evaluate Target Fingerprint]
                   System Alert                │                                       │
                                         Unfinished op                         has_target_changed?
                                         marked 'intent'                               │
                                                                       ┌───────────────┴───────────────┐
                                                                       ▼                               ▼
                                                                   [NO CHANGE]                   [ALREADY MUTATED]
                                                                Pre-Commit Crash                 Post-Commit Crash
                                                                       │                               │
                                                                /recover replays             /recover auto-resolves
                                                                tool call once               as 'recovered_landed'
                                                                (status='resumed')           (ZERO duplicate writes!)
                                                                       │                               │
                                                                       └───────────────┬───────────────┘
                                                                                       ▼
                                                                           Agent Proceeds Safely
                                                                           (0 LLM Recovery Calls)
```

---

Agents fail in the worst possible window: *after* a tool side effect commits, but *before* the result is recorded in session history. A network drop, process kill (`SIGKILL`), laptop lid close, or gateway timeout leaves the agent blind to whether the write actually landed. The agent retries, and customer 42 gets billed twice or critical code is corrupted.

**Phoenix is the flight recorder for that failure mode.** It journals every tool call to a local SQLite WAL ledger *before* it runs (recording pre-execution target state fingerprints) and its outcome *after*. If the process dies, the flight recorder reveals exactly what was in flight — and `/recover` finishes it safely with **zero duplicate writes** and **zero LLM calls**.

```
tool call ──▶ journal "intent" (pre-fingerprint) ──▶ execute ──▶ journal "ok" / "error"
                                        ▲
                                        └── process dies here = "in-flight" (ambiguous)
```

A row stuck on `intent` **is** the mechanical signature of "the agent died during this call". No heuristics, no LLM guessing — a WAL commit written before execution and never followed by an outcome.

---

## Why Not Built-in `/rollback`?

### Destructive Backward Undo vs. Non-Destructive Forward Recovery

Hermes includes a built-in checkpoint rollback mechanism (`checkpoint_manager.py`). While useful for interactive human sessions, it solves an entirely different problem from Phoenix:

| Dimension | Built-in `/rollback` (`checkpoint_manager.py`) | Phoenix (`/recover` + Flight Recorder) |
|---|---|---|
| **Recovery Direction** | **Destructive backward undo.** Reverts uncommitted files back to turn start, destroying completed good work. | **Non-destructive forward recovery.** Safely advances and completes only the interrupted operation. |
| **Granularity** | Turn-level boundary snapshot (once per conversational turn). | Tool-call-level (`op_id`) WAL ledger (every individual tool call). |
| **Scope of Protection** | Git-tracked files only. Ignores external mutations, non-git files, and tool side effects. | Full filesystem + tool calls (`write_file`, `edit_file`, unified `patch`, shell redirects, APIs with `idempotency_key`). |
| **Crash & Interruption Handling** | Blind to mid-turn crashes. If killed mid-turn, cannot determine whether a tool write actually landed on disk. | Pre/post state fingerprinting detects whether the file already mutated on disk before crash (`recovered_landed` with 0 re-writes). |
| **Target Environments** | Requires human operator in interactive chat to notice errors and type `/rollback`. | Autonomous Turn-1 system prompt alert; headless recovery across Hermes cron jobs, Telegram/Discord gateways, and API servers. |
| **Cost & Token Overhead** | Incurs LLM costs to re-reason and re-generate lost work. | **Zero LLM calls.** Replays exact deterministic bytecode from WAL ledger. |

### The Unattended Agent Problem
If an autonomous agent is running a 20-file refactor overnight or processing transactions via a headless Telegram gateway, a crash on step 14 shouldn't wipe out steps 1 through 13 (`/rollback`), nor should it blind-retry step 14 and corrupt state. 

Phoenix operates as a **flight recorder**: on reboot, Turn-1 autonomous crash detection alerts the agent, inspects disk state fingerprints, marks operations that already landed as `recovered_landed`, and finishes pending writes forward.

---

## 4 Core Differentiators in v0.3.0

### 1. WAL Flight Recorder + Extended State Fingerprinting
Distinguishes a **pre-commit crash** (re-dispatches once as `status='resumed'`) from a **post-commit crash** where the file or side effect already landed on disk. Phoenix checks `has_target_changed(pre_fp)`: if the side effect already landed before the crash, Phoenix detects it and marks the op `recovered_landed` **without calling the write tool a second time**!
- Extended target fingerprinting across `write_file`, `edit_file`, unified diff patches (`patch`), shell output redirection & `tee` (`terminal`, `bash`, `shell`), and explicit `idempotency_key` payloads.
- SHA-256 canonical hashing of payloads and pre/post filesystem states up to 10MB.

### 2. Turn-1 Autonomous Crash Detection (`system_prompt_alert`)
Leverages Hermes's native `register_system_prompt_section("phoenix_recovery", ...)` hook. When an agent boots after an unclean exit or crash, Phoenix injects a high-priority, zero-token-overhead recovery alert directly into Turn 1's system prompt. The agent instantly knows which interrupted operations are pending, whether their target already mutated on disk, and how to safely heal state before proceeding.

### 3. Live Idempotency Guard & Real `tool_execution` Middleware
Derives a deterministic, canonical idempotency key `op_id` from `(tool_name, args)`. When an agent retries an identical tool call in-session, Phoenix intercepts the duplicate (`status='deduped'`) and returns the cached commit outcome directly without re-executing. Drives both live Hermes session execution and offline trace replay in the ReplayLab Wind Tunnel.

### 4. Native Hermes Web Dashboard Extension & Standalone HTML Forensic Reports
- **Web Dashboard Extension:** Declares `dashboard/manifest.json` pointing to an embedded, dark-mode visual interface with real-time WAL ledger inspection, live crash indicators, and wind tunnel controls.
- **Standalone Dark-Mode Forensic HTML Report:** Run `/phoenix report [path]` (or `python demo.py --html`) to generate an instant, self-contained, zero-dependency HTML5 forensic receipt featuring full flight recorder history, crash recovery audit cards, and Zeller `ddmin` counterexample traces.

---

## 60-Second Quickstart

### Installation

Install directly via the Hermes plugin manager:

```bash
hermes plugins install https://github.com/Ratz00007/phoenix.git --enable
```

Or clone and run the standalone rehearsal suite with HTML report generation:

```bash
git clone https://github.com/Ratz00007/phoenix.git && cd phoenix && python demo.py --html
```

Phoenix is now live. Every tool call is journaled and protected automatically.

### In any Hermes Chat:

```text
/phoenix                 # committed N · errors M · in-flight K · deduped D
/phoenix explain <op>    # full forensics: tool, args, pre/post fingerprints, status
/recover                 # safely finish every interrupted call (no command collision)
/recover <op_id>         # ...or just the specific one you care about
/phoenix guard on|off    # toggle live in-session idempotency deduplication
/phoenix windtunnel      # run the fault-injection wind tunnel & ddmin suite
/phoenix report [path]   # generate standalone dark-mode HTML forensic report
```

### Via the Hermes CLI:

```bash
hermes phoenix status
hermes phoenix recover
hermes phoenix windtunnel
hermes phoenix report
```

Zero third-party dependencies. Python 3.11+ standard library only.

---

## The 4-Act Demo Walkthrough

Run the automated rehearsal script:

```bash
python demo.py --html phoenix-report.html
```

### Act 1: Pre-Commit Crash -> `/recover` replays once
1. Agent commits `a.txt` normally via `tool_execution` middleware.
2. Agent records intent for `b.txt`, but process is killed **before** writing to disk.
3. Restart process and run `/recover`. Phoenix detects no file was written, re-executes the tool call once, and marks it `status='resumed'`.

### Act 2: Post-Commit Crash -> State Fingerprint Protection & Autonomous Alert
1. Agent records intent for `c.txt` with `pre_fp = target_fingerprint(...)`.
2. `c.txt` IS written to disk (`"gamma"`), but process dies **before** `record_outcome`.
3. Restart process: Turn-1 System Prompt Alert detects `c.txt` in-flight and notices `target ALREADY mutated on disk`.
4. Run `/recover`. Phoenix detects `has_target_changed(pre_fp) == True` (the write already landed on disk!) and marks `c.txt` as `recovered_landed` **without calling the write tool a second time**.

### Act 3: ReplayLab Wind Tunnel + `ddmin` Fault Minimizer
1. The wind tunnel injects `timeout_after_commit`, `rate_limit_429`, and `malformed_payload` through real `tool_execution` middleware.
2. Unguarded execution fails `5/5 RED`.
3. `ddmin` minimizes the 11-step trace to 1 step in `<2ms` (0 LLM calls).
4. Running with Phoenix Guard ON turns all failures green: `0/5 RED (5/5 GREEN)`.

### Act 4: Standalone Dark-Mode HTML Forensic Report
1. Call `/phoenix report` (or pass `--html` to `demo.py`).
2. Outputs a clean, self-contained HTML forensic dashboard with zero `<script>` tags, complete WAL ledger stats, and state fingerprinting verification receipts.

---

## How It Works

| Component | What It Does |
|---|---|
| `tool_execution` middleware | Journals **intent** (tool + canonical args + `op_id` + `pre_fp`) to SQLite WAL *before* calling `next_call`, and journals **outcome** after. Intercepts duplicates if guard is on. Drives live execution and wind tunnel trace replay. |
| `keys.py` & Fingerprints | Generates deterministic `op_id` via SHA-256 canonical JSON. Generates `pre_fp` state hashes across `write_file`, `edit_file`, unified `patch` diffs, and `terminal` redirects. Checks `has_target_changed` during recovery. |
| `core.py` (`system_prompt_alert`) | Powers Turn-1 autonomous crash detection via `register_system_prompt_section("phoenix_recovery", ...)`, notifying the agent of pending recoveries before any tool execution begins. |
| `dashboard/manifest.json` | Native Hermes Web Dashboard plugin manifest integrating the visual flight recorder and wind tunnel directly into the Hermes UI. |
| `report.py` | Standalone dark-mode HTML forensic report generator with zero script tags, compliant with static security scanners. |
| `plugin_data_dir("phoenix")` | Durable, profile-scoped SQLite WAL ledger that survives crashes, process kills, and plugin updates. |
| `/phoenix` & `/recover` | `/phoenix` provides diagnostics/forensics/reports; `/recover` handles crash recovery. (Named `/recover` to eliminate any collision with Hermes built-in `/resume`). |
| `phoenix_ledger` tool | Hermes tool allowing the agent or operator to inspect the flight recorder and verify operation statuses. |
| `phoenix_windtunnel` tool & CLI | Built-in test harness executing deterministic fault injection with automated `ddmin` trace minimization. |

### Deterministic Recovery — Zero LLM Calls
`/recover` re-dispatches the exact recorded tool call from the WAL ledger, rather than generating a new model decision. Unset your API key or disconnect the internet — `/recover` and the wind tunnel still run and verify deterministically.

### Fail-Open Live, Fail-Closed Recovery
- **Live Execution is Fail-Open:** If the ledger write fails during agent operation, the exception is swallowed and the tool still executes — Phoenix never breaks your running agent.
- **Recovery is Fail-Closed:** An interruption is never silently swept under the rug. It remains visible as `in-flight` until verified and safely resolved.

---

## Hermes Surfaces Used

- `tool_execution` middleware — intercepts calls, checks deduplication guard, journals intent and outcome.
- `system_prompt_section` hook — registers `"phoenix_recovery"` prompt alert for Turn-1 autonomous crash recovery.
- `/phoenix` and `/recover` slash commands — registered via `ctx.register_command`.
- Web Dashboard extension — registered via `dashboard/manifest.json`.
- CLI commands — registered via `ctx.register_cli_command("phoenix", ...)`.
- Tools — `phoenix_ledger` and `phoenix_windtunnel` registered via `ctx.register_tool`.
- `plugin_data_dir("phoenix")` — profile-scoped durable storage.

---

## Security & Catalog Rule Disclosure

### Rule 11 (Credentials)
- **Zero Secrets / Environment Reads:** Phoenix requires no external API keys, tokens, or credentials. No `requires_env`, no `config_schema`.

### Rule 12 (Approvals Respected)
- **Explicit Recovery Only:** Forward recovery executes tool calls via `ctx.dispatch_tool` strictly when requested by the user (`/recover`) or agent (`phoenix_ledger(action="recover")`). No unprompted background tool dispatches.

### Rule 13 (Disclosure & Sandbox Integrity)
- **Network:** Zero external network calls. No telemetry, no phone-home, no LLM calls during recovery or trace replay.
- **Data Stored:** 100% local SQLite WAL ledger stored strictly inside `plugin_data_dir("phoenix")`. Stores tool names, canonical JSON arguments, SHA-256 target fingerprints, and execution outcomes. Nothing leaves the host machine.
- **Filesystem Boundaries:** Reads and writes only inside its own plugin data directory and explicit tool target paths. No monkey-patching of Hermes core, no subprocess shells, and no self-updating code. Generated HTML reports contain zero `<script>` tags for strict security scanner compliance.
- **Dependencies:** Python standard library only (Python 3.11+). Zero external pip dependencies.

---

## License

MIT.
