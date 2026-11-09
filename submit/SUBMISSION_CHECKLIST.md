# Phoenix v0.3.0 — Official Competition Submission Checklist

> **Target:** Hermes Plugin Competition (`NousResearch/hermes-agent`)  
> **Version:** `0.3.0`  
> **Plugin ID:** `phoenix`  
> **Maintainer:** `Ratz00007`  
> **Repository:** https://github.com/Ratz00007/phoenix  
> **Pinned Commit:** `0000000000000000000000000000000000000000`  
> **Status:** Production-Ready, 100% Deterministic, Zero Dependencies

---

## 1. Phoenix v0.3.0 Feature Matrix & Deliverables

| Capability | Module & Implementation | Hermes Public Surface | Verification Receipt |
|---|---|---|---|
| **Transactional WAL Ledger** | `journal.py` (SQLite WAL mode, synchronous=NORMAL, profile-scoped durable data directory) | `plugin_data_dir("phoenix")` | Intent committed before execution, outcome committed after; survives SIGKILL. |
| **Turn-1 Autonomous Crash Detection** | `core.py` (`system_prompt_alert`) | `ctx.register_system_prompt_section("phoenix_recovery", ...)` | Injects proactive crash alert on turn 1 post-crash with target mutation status. |
| **Pre/Post State Fingerprinting** | `keys.py` (`target_fingerprint`, `has_target_changed`) | Extended coverage: `write_file`, `edit_file`, `patch` diffs, `terminal` / `tee` redirects, caller `idempotency_key` | `c.txt` post-commit crash marked `recovered_landed` with 0 duplicate write dispatches. |
| **Real Middleware & ReplayLab Wind Tunnel** | `middleware.py`, `windtunnel.py` | `ctx.register_middleware("tool_execution", ...)` | Drives live session execution and deterministic trace replay; Zeller `ddmin` shrinks 11 steps to 1 in <2ms. (5/5 RED -> 5/5 GREEN). |
| **Live In-Session Idempotency Guard** | `middleware.py`, `keys.py` (`op_id`) | Canonical SHA-256 argument normalization | Duplicate tool calls in-session return cached results (`status='deduped'`). |
| **Native Web Dashboard Extension** | `dashboard/manifest.json`, `dashboard/dist/index.js` | Hermes Web Dashboard API | Valid manifest declared; embeds real-time ledger & wind tunnel directly into Web UI. |
| **Standalone HTML Forensic Report** | `report.py`, `core.py` (`report`) | `/phoenix report [path]`, `demo.py --html` | Zero-dependency, sleek dark-mode HTML report with zero `<script>` tags for security scanning. |
| **Hermes Slash Commands & Tools** | `commands.py`, `tools.py` | `/phoenix`, `/recover`, `phoenix_ledger`, `phoenix_windtunnel` | Zero collision with Hermes core (never uses `/resume`). |

---

## 2. Rule 13 Security & Safety Disclosure

- **Zero External Network Calls:** No outbound HTTP/TCP sockets, no telemetry, no phone-home, no LLM calls during recovery or replay.
- **Zero Secrets / Environment Reads:** No `requires_env`, no `config_schema`, zero secret reads.
- **Local Profile-Scoped Storage:** 100% local SQLite WAL ledger stored strictly inside `plugin_data_dir("phoenix")`.
- **Explicit Tool Dispatch Only:** `recover` dispatches via `ctx.dispatch_tool` strictly when invoked by user (`/recover`) or agent (`phoenix_ledger(action="recover")`). No unprompted background tool dispatches.

---

## 3. Pre-Flight Verification Receipts

Run these commands in order from the `phoenix` root directory:

- [ ] **1. Clean Manifest & Structure Validation**
  ```bash
  python -c "import yaml; yaml.safe_load(open('plugin.yaml'))"
  ```
  *Receipt:* Valid YAML with name `phoenix`, version `0.3.0`, description, and kind `standard`.

- [ ] **2. Web Dashboard Manifest Validation**
  ```bash
  python -c "import json; data=json.load(open('dashboard/manifest.json')); assert data['name']=='phoenix' and data['version']=='0.3.0'"
  ```
  *Receipt:* Valid JSON manifest matching plugin specification.

- [ ] **3. Strict Self-Check Suite**
  ```bash
  python selfcheck.py
  ```
  *Receipt:* Prints `PHOENIX SELF-CHECK: PASS` across all 6 verification checks:
  - `[PASS] manifest`: name/version/description/kind present
  - `[PASS] dashboard manifest`: dashboard/manifest.json parses valid JSON
  - `[PASS] register(ctx)`: registers middleware, 2 commands, 2 tools, and `phoenix_recovery` prompt section
  - `[PASS] public imports`: adheres strictly to the Hermes public API allow-list
  - `[PASS] no binaries`: no `.pyc`, `.so`, `.dll`, or bytecode artifacts
  - `[PASS] unit tests`: stdlib unittest discover passes green

- [ ] **4. Automated Rehearsal & HTML Report Generation**
  ```bash
  python demo.py --html phoenix-report.html
  ```
  *Receipt:* Prints `PHOENIX DEMO: PASS` across all 4 acts:
  - Act 1: Pre-commit crash replayed once (`status='resumed'`)
  - Act 2: Post-commit crash detected via Turn-1 alert & fingerprint check (`status='recovered_landed'`, 0 re-writes)
  - Act 3: Wind tunnel chaos tests pass (5/5 RED -> ddmin minimized -> 5/5 GREEN)
  - Act 4: HTML report generated at `phoenix-report.html` (>0 bytes, verified)

- [ ] **5. Full Unit Test Suite**
  ```bash
  python -m unittest discover -s tests -v
  ```
  *Receipt:* All unit tests passing.

---

## 4. Submission Steps

### Step 1: Push to Public GitHub Repository
```bash
git init -b main
git add .
git commit -m "feat: Phoenix v0.3.0 transactional WAL crash journal & ReplayLab ddmin wind tunnel"
gh repo create Ratz00007/phoenix --public --description "Transactional SQLite WAL crash-recovery journal, idempotency guard & ReplayLab ddmin wind tunnel for Hermes Agent" --source=. --remote=origin --push
```

### Step 2: Pin the 40-Character Commit SHA
```bash
git rev-parse HEAD
```
Update `submit/phoenix.yaml`, `submit/PR-description.md`, and `submit/SUBMISSION_CHECKLIST.md` with your repository URL and the full 40-character commit SHA.

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
