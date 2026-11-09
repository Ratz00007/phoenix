# Add plugin: `phoenix` v0.3.0 — transactional WAL crash journal, idempotency guard & deterministic wind tunnel

**Repository:** https://github.com/Ratz00007/phoenix  
**Pinned Commit:** `ea0d8e20a61ad83f244cb4fa47dfa647d4d3d55a` (https://github.com/Ratz00007/phoenix/commit/ea0d8e20a61ad83f244cb4fa47dfa647d4d3d55a)  
**Maintainer:** @Ratz00007  
**Version:** `0.3.0`  

**One line:** Journals every Hermes tool call *before* it runs and its outcome *after*. Features pre/post state fingerprinting to prevent double execution across crashes, Turn-1 proactive crash alerts, live in-session idempotency deduplication, Web Dashboard integration, and a deterministic fault-injection wind tunnel with `ddmin` delta debugging.

> Kill your agent mid-write. It recovers having executed exactly once — guaranteed by pre/post state fingerprints.

## Key Capabilities (v0.3.0 Championship Edition)

1. **Transactional SQLite WAL Crash Journal (`journal.py`):**
   Writes an intent row to a local SQLite WAL ledger in `plugin_data_dir("phoenix")` before every tool call, and commits the outcome immediately after. Survives abrupt process termination (`SIGKILL`, OOM, power loss, terminal crash).

2. **Pre/Post State Fingerprinting & Deduplication (`keys.py`):**
   Distinguishes a **pre-commit crash** (re-dispatches once as `resumed`) from a **post-commit crash** where the file or side-effect already landed on disk. Supports `write_file`, `edit_file`, unified `patch` diffs, `terminal` / `tee` redirects, and explicit caller `idempotency_key` metadata. Evaluates `has_target_changed(pre_fp)`: if the target was already modified before crash, Phoenix marks the op `recovered_landed` **without calling the write tool a second time**.

3. **Turn-1 Autonomous Crash Detection (`core.py`):**
   Registers a dynamic system prompt section (`phoenix_recovery`) on reboot via `ctx.register_system_prompt_section`. Immediately informs the agent on Turn 1 of any in-flight operations, interrupted tools, and target file mutation status so recovery can be planned autonomously without user prompting.

4. **Real Middleware & ReplayLab Wind Tunnel (`windtunnel.py` + `middleware.py`):**
   Shares the exact same SQLite WAL ledger and `tool_execution` middleware pipeline across production execution and chaotic trace replay. Injects boundary faults (`timeout_after_commit`, `rate_limit_429`, `malformed_payload`) and applies Zeller's delta debugging (`ddmin`) to isolate minimal failure counterexamples in `<2ms` with **0 LLM calls** (proving `5/5 RED` unguarded -> `0/5 RED (5/5 GREEN)` guarded).

5. **Live In-Session Idempotency Guard (`middleware.py`):**
   Derives a deterministic canonical `op_id` SHA-256 hash from `(tool_name, args)`. Intercepts duplicate tool retries in-session (`status='deduped'`) and returns cached commit outcomes directly without re-executing side effects.

6. **Native Web Dashboard & Standalone HTML Forensic Report:**
   Bundles a Hermes Web Dashboard extension (`dashboard/manifest.json`, `dashboard/dist/index.js`) for visual inspection of the WAL ledger, plus `/phoenix report [path]` for offline standalone HTML forensics with zero external CSS/JS dependencies.

## Hermes surfaces used

- `tool_execution` middleware (idempotency guard + WAL journaling)
- `ctx.register_system_prompt_section("phoenix_recovery", ...)` (Turn-1 crash awareness)
- Slash commands: `/phoenix` (`status`, `explain`, `guard`, `windtunnel`, `report`) and `/recover`
- CLI commands: `hermes phoenix status`, `hermes phoenix recover`, `hermes phoenix windtunnel`, `hermes phoenix report`
- Tools: `phoenix_ledger` (history inspection & recovery) and `phoenix_windtunnel` (chaos verification)
- Profile-scoped data: `plugin_data_dir("phoenix")` — SQLite WAL ledger

## Disclosure (Rule 13)

- **Network:** Zero external network calls. No telemetry, no phone-home, no LLM API calls during recovery or replay.
- **Secrets:** Zero secret reads. No `requires_env`, no `config_schema`, no environment variable inspection.
- **Data stored:** 100% local SQLite WAL ledger stored strictly inside `plugin_data_dir("phoenix")`. Stores tool names, canonical JSON args, SHA-256 target fingerprints, and execution outcomes. Nothing leaves the local machine.
- **Tool Dispatch & Security:** Read/write scoped strictly to plugin data directory and explicit target paths. `recover` dispatches via `ctx.dispatch_tool` **only when explicitly invoked** by the user (`/recover`) or agent (`phoenix_ledger(action="recover")`). No unattended tool dispatches, no background monkey-patching of Hermes core, no subprocess shells, and no self-updating code.
- **Dependencies:** Python standard library only (>=3.11). Zero third-party Python packages.

## Validation Receipts (Hermes v0.21.6)

```
✓ manifest — plugin.yaml parses (name: phoenix, version: 0.3.0)
✓ loadable — entry: __init__.py
✓ capability probe — register() ran in isolation
✓ declared tools / hooks / middleware — matches registrations (phoenix_ledger, phoenix_windtunnel, tool_execution)
✓ security scan — safe (zero unauthorized network, zero core overrides)
✓ no core override — no runtime rebinds of Hermes core (safe collision-free /recover)
Validation passed.
```

Receipts verified on clean checkout:
- `hermes plugins doctor . --ci` (import + registration passed)
- `python selfcheck.py` (`PHOENIX SELF-CHECK: PASS` across all 6 test suites)
- `python demo.py --html phoenix-report.html` (`PHOENIX DEMO: PASS` — all 4 acts verified)
- `python -m unittest discover -s tests -v` (53/53 unit tests passing green)

## Reproducible 1-Command Demonstration

```bash
python demo.py --html phoenix-report.html
```

Runs all 4 acts offline in `<1s` with zero external dependencies or API keys:
1. **Act 1 (Pre-Commit Crash):** Simulates process crash before write lands $\rightarrow$ `/recover` replays once (`status='resumed'`).
2. **Act 2 (Post-Commit Crash + Turn-1 System Prompt Alert):** Simulates process crash *after* write lands on disk $\rightarrow$ Turn-1 `[PHOENIX WAL CRASH ALERT]` detects target file SHA-256 changed and `/recover` marks `status='recovered_landed'` with **0 redundant writes**.
3. **Act 3 (ReplayLab Wind Tunnel + Zeller's `ddmin`):** Runs the real `tool_execution` middleware across an 11-step trace with `timeout_after_commit`, shrinks the unguarded failure from `11 -> 1 step` (`crm.update_plan`) in `<2ms` with `0` LLM calls, and proves Guard ON achieves `6/6 PASS` (`0/5 RED`).
4. **Act 4 (Forensic Report):** Exports the self-contained dark-mode HTML5 dashboard (`phoenix-report.html`).
