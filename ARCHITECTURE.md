# Phoenix v0.3.1 Architecture

> **Core Invariant:** *At-most-once execution + at-least-once recording + zero duplicate writes.*

---

## 1. Module Layout

```
phoenix/
├── __init__.py          # Hermes register(ctx): middleware, tools, commands, system prompt
├── plugin.yaml          # Standalone manifest (v0.3.1, 0 deps)
├── core.py              # Phoenix App lifecycle, Turn-1 crash alert, forward recovery
├── journal.py           # SQLite WAL ledger (0600, O_EXCL, WAL/SHM perms, retention, redaction)
├── keys.py              # Canonical op_id SHA-256 & target state fingerprinting
├── middleware.py        # tool_execution interceptor + opt-in same-session idempotency guard
├── commands.py          # Owner-only /phoenix & /recover slash commands + CLI handler
├── tools.py             # Read-only phoenix_ledger & real phoenix_windtunnel model tools
├── report.py            # Zero-script standalone dark-mode HTML forensic report
├── windtunnel.py        # Deterministic fault-injection wind tunnel + Zeller ddmin minimizer
├── selfcheck.py         # Hermes plugin doctor self-check script
├── demo.py              # 4-act end-to-end crash-and-recover demonstration
├── judge_eval.py        # Official judge scorecard (80 unit tests, doctor, windtunnel)
├── dashboard/           # Hermes Web Dashboard extension (manifest.json, plugin_api.py, dist/index.js)
└── tests/               # 80 unit tests (unittest discover -s tests)
```

---

## 2. Transactional SQLite WAL Protocol (`journal.py`)

Every tool call passes through `middleware.py` before reaching Hermes' underlying tool executor:

1. **Intent Logging (`record_intent`)**: Writes a row into `phoenix.db` (`journal_mode=WAL`, `synchronous=NORMAL`, `0600` permissions on DB and `-wal`/`-shm` sidecars) with `status='in_flight'`, canonical `op_id`, redacted `args_json`, and pre-execution SHA-256 target `pre_fp`.
2. **Tool Execution**: The underlying tool runs normally.
3. **Outcome Commit (`record_outcome`)**: Updates the row to `status='committed'` (or `status='error'`) with post-execution SHA-256 target `post_fp` and redacted `result_json`.

---

## 3. Forward Zero-LLM Crash Recovery (`core.py` & `keys.py`)

If `SIGKILL`, OOM, or power loss kills the process between Step 1 and Step 3:

1. **Turn-1 Detection**: On reboot, `ctx.register_system_prompt_section("phoenix_recovery", ...)` inspects `journal.in_flight()`. If interrupted calls exist, it injects a zero-token alert advising the user to run `/recover`.
2. **Target State Fingerprinting**: When the owner runs `/recover`, `keys.has_target_changed(pre_fp)` inspects the target on disk (`write_file`, `edit_file`, unified `patch` hunks, shell `>` / `tee` redirects):
   - **Post-Commit Crash (Target Already Mutated)**: Marked `recovered_landed` with **0 duplicate writes** and **0 tool re-dispatches**.
   - **Pre-Commit Crash (Target Unchanged)**: Safely re-dispatched once via `ctx.dispatch_tool` and marked `resumed`.
3. **Zero LLM Tokens**: Recovery executes deterministically from the SQLite WAL ledger—no LLM re-reasoning required.

---

## 4. ReplayLab Wind Tunnel & Zeller `ddmin` (`windtunnel.py`)

`windtunnel.py` injects deterministic boundary faults (`timeout_after_commit`, `rate_limit_429`, `malformed_payload`) across `HERMES_DEV_TRACE` and applies Zeller's delta debugging (`ddmin_trace`) to isolate the minimal 1-step counterexample in `<50ms` with 0 LLM calls.
