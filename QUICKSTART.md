# Phoenix v0.3.1 Quickstart Guide

Get up and running in 60 seconds with **0 external dependencies** and **0 API keys**.

---

## 1. Run the Complete Evaluation Scorecard
```bash
python judge_eval.py
```
Executes:
- **80/80 Unit Tests** (`python -m unittest discover -s tests`)
- **5 Hermes Official Doctor Checks** (manifest, dashboard, registration, public imports, clean build)
- **Developer Wind Tunnel & Zeller `ddmin`** (8-step trace minimized to 1 step in `<50ms`)

---

## 2. Run the 4-Act Crash-and-Recover Demo
```bash
python demo.py
```
Demonstrates:
1. **Act 1**: Pre-commit `SIGKILL` -> `/recover` replays once (`status='resumed'`).
2. **Act 2**: Post-commit `SIGKILL` -> Turn-1 prompt alert + SHA-256 fingerprint check -> marked `recovered_landed` with **0 redundant writes**.
3. **Act 3**: Real fault-injection wind tunnel (`5/5 RED` unguarded -> `ddmin` isolated -> `0/5 RED` guarded).
4. **Act 4**: Self-contained dark-mode HTML forensic report export.

---

## 3. Validate with Hermes CLI
```bash
hermes plugins validate .
```
Verifies manifest schema, capability registrations, zero built-in tool collisions, and security scan (`14/14` checks green).

---

## 4. In-Chat Commands & Tools
- `/phoenix status` — Inspect ledger counts and in-flight operations.
- `/recover` — Owner-only forward recovery of interrupted operations.
- `/phoenix guard on|off` — Toggle the opt-in same-session idempotency guard.
- `/phoenix windtunnel` — Run the 6-check fault-injection suite.
- `/phoenix report` — Generate standalone HTML forensic report.
- `phoenix_ledger` — Read-only model tool (`status`, `explain`, `report`).
- `phoenix_windtunnel` — Model tool to run the real wind tunnel suite.
