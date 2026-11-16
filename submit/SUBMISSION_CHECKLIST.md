# Phoenix v2.0.0 — Official Competition Submission Checklist

> **Target:** Hermes Plugin Catalog (`NousResearch/hermes-agent#154408`)  
> **Version:** `2.0.0`  
> **Plugin ID:** `phoenix`  
> **Maintainer:** `Ratz00007`  
> **Repository:** https://github.com/Ratz00007/phoenix  
> **Status:** Production-Ready, 100% Deterministic, Zero Dependencies

---

## 1. Phoenix v2.0.0 Feature Matrix & Deliverables

| Capability | Module & Implementation | Hermes Public Surface | Verification Receipt |
|---|---|---|---|
| **Transactional WAL Ledger** | `journal.py` (SQLite WAL mode, synchronous=NORMAL, mode 0600, profile-scoped durable data directory) | `plugin_data_dir("phoenix")` | Intent committed before execution, outcome committed after; survives SIGKILL. |
| **Turn-1 Autonomous Crash Detection** | `core.py` (`system_prompt_alert`) | `ctx.register_system_prompt_section("phoenix_recovery", ...)` | Injects proactive crash alert on turn 1 post-crash with target mutation status. |
| **Pre/Post State Fingerprinting** | `keys.py` (`target_fingerprint`, `has_target_changed`) | Extended coverage: `write_file`, `edit_file`, `patch` diffs, `terminal` / `tee` redirects, caller `idempotency_key` | Post-commit crash marked `recovered_landed` with 0 duplicate write dispatches. |
| **Real Middleware & ReplayLab Wind Tunnel** | `middleware.py`, `windtunnel.py`, `chaos.py` | `ctx.register_middleware("tool_execution", ...)` | Drives live session execution, deterministic trace replay, and 12/12 chaos boundary trials; Zeller `ddmin` shrinks 8 steps to 1 in <2ms. |
| **Live In-Session Idempotency Guard** | `middleware.py`, `keys.py` (`op_id`) | Canonical SHA-256 argument normalization (Opt-in, OFF by default) | Duplicate tool calls in-session return cached results (`status='deduped'`). |
| **Desktop SDK & Web Dashboard** | `desktop/plugin.js`, `dashboard/manifest.json`, `dashboard/plugin_api.py`, `dashboard/dist/index.js` | `@hermes/plugin-sdk` + Hermes Web Dashboard API | Valid manifests & endpoints; embeds live ledger, fingerprint inspector & wind tunnel into UI. |
| **Standalone HTML Forensic Report** | `report.py`, `core.py` (`report`) | `/phoenix report [path]`, `demo.py --html` | Zero-dependency, sleek dark-mode HTML report with zero `<script>` tags for security scanning. |
| **Hermes Slash Commands & Tools** | `commands.py`, `tools.py` | `/phoenix`, `/recover`, `phoenix_ledger`, `phoenix_stats`, `phoenix_windtunnel` | Zero collision with Hermes core (never uses `/resume`). |

---

## 2. Rule 13 Security & Safety Disclosure

- **Zero External Network Calls:** No outbound HTTP/TCP sockets, no telemetry, no phone-home, no LLM calls during recovery or replay.
- **Zero Secrets / Environment Reads:** No `requires_env`, no `config_schema`, zero secret reads.
- **Local Profile-Scoped Storage:** 100% local SQLite WAL ledger stored strictly inside `plugin_data_dir("phoenix")`.
- **Explicit Tool Dispatch Only:** `recover` dispatches via `ctx.dispatch_tool` strictly when invoked by the human owner (`/recover` or `/phoenix recover`). No model-callable replay or unprompted background tool dispatches.

---

## 3. Pre-Flight Verification Receipts

Run these commands in order from the `phoenix` root directory:

- [ ] **1. Clean Manifest & Structure Validation**
  ```bash
  python -c "import yaml; yaml.safe_load(open('plugin.yaml'))"
  ```
  *Receipt:* Valid YAML with name `phoenix`, version `2.0.0`, description, and kind `standard`.

- [ ] **2. Web Dashboard Manifest Validation**
  ```bash
  python -c "import json; data=json.load(open('dashboard/manifest.json')); assert data['name']=='phoenix' and data['version']=='2.0.0'"
  ```
  *Receipt:* Valid JSON manifest matching plugin specification.

- [ ] **3. Strict Self-Check Suite**
  ```bash
  python selfcheck.py
  ```
  *Receipt:* Prints `PHOENIX SELF-CHECK: PASS` across all 7 verification checks:
  - `[PASS] manifest`: name/version/description/kind present
  - `[PASS] dashboard manifest`: dashboard/manifest.json parses valid JSON
  - `[PASS] desktop surface`: desktop/plugin.js present and syntax/lint clean
  - `[PASS] register(ctx)`: registers middleware, 2 commands (/phoenix, /recover), 3 tools (phoenix_ledger, phoenix_stats, phoenix_windtunnel), and `phoenix_recovery` prompt section
  - `[PASS] public imports`: adheres strictly to the Hermes public API allow-list
  - `[PASS] no binaries`: no `.pyc`, `.so`, `.dll`, or bytecode artifacts
  - `[PASS] unit tests`: stdlib unittest discover passes green (110/110)

- [ ] **4. Automated Rehearsal & HTML Report Generation**
  ```bash
  python demo.py --chaos --html phoenix-report.html
  ```
  *Receipt:* Prints `PHOENIX DEMO: PASS` across all 4 acts + deterministic chaos:
  - Act 1: Pre-commit crash replayed once (`status='resumed'`)
  - Act 2: Post-commit crash detected via Turn-1 alert & fingerprint check (`status='recovered_landed'`, 0 re-writes)
  - Act 3: Wind tunnel chaos tests pass (6/6 GREEN guarded, ddmin minimized to 1 step) + 12/12 chaos trials
  - Act 4: HTML report generated at `phoenix-report.html` (>0 bytes, verified)

- [ ] **5. Full Unit Test Suite**
  ```bash
  python -m unittest discover -s tests -v
  ```
  *Receipt:* 110/110 unit tests passing.

---

## 4. Submission Steps

### Step 1: Push to Public GitHub Repository
```bash
git add .
git commit -m "feat: Phoenix v2.0.0 transactional WAL crash journal, Desktop SDK & ReplayLab ddmin wind tunnel"
git push origin main
```

### Step 2: Pin the 40-Character Commit SHA in PR #154408
```bash
git rev-parse HEAD
```
Update `plugin-catalog/phoenix.yaml` `sha:` and the PR description in `NousResearch/hermes-agent#154408` with the pushed 40-character commit SHA.

### Step 3: Open Catalog Pull Request
1. Fork `NousResearch/hermes-agent`.
2. Place `phoenix.yaml` into `plugin-catalog/phoenix.yaml`.
3. Open PR with title: `Add plugin: phoenix (crash-proof execution journal, idempotency guard & wind tunnel)`.
4. Copy description from `submit/PR-description.md`.
5. Attach screenshots of the Web Dashboard and `/phoenix report`.

### Step 4: Publish Video & Post on X
1. Film 90-second live demonstration following `submit/X_POST_AND_VIDEO_SCRIPT.md`.
2. Post video on X tagging `@NousResearch` using the pre-drafted tweet copy.
3. Add link to your PR in the replies.
