# Phoenix Quickstart Guide

Get up and running with Phoenix in under 60 seconds on any Hermes installation.

---

## 1. Quick Installation (3 Commands)

Install Phoenix directly from the official Hermes plugin catalog:

```bash
# 1. Install Phoenix plugin into Hermes
hermes plugins install phoenix

# 2. Run the deterministic chaos demonstration (< 30 seconds)
python -m phoenix.demo --chaos

# 3. Inspect real-time value metrics ($ saved and dupes prevented)
hermes /phoenix stats
```

---

## 2. Using Phoenix in Your Hermes Agent Workflow

### Interactive Slash Commands
- `/phoenix status`: Displays active in-flight calls, dupes prevented, and ledger state.
- `/phoenix stats`: Shows total financial capital saved and avoided LLM cycles.
- `/phoenix report`: Generates a Markdown audit report of all intercepted calls.
- `/recover`: Reconciles interrupted operations post-SIGKILL with 0 duplicate writes.
- `/recover --dry-run`: Previews recovery actions without committing state changes.

### Native Hermes Tools
When your agent is running autonomously, Phoenix registers 4 zero-overhead tools:
- `phoenix_ledger`: Read-only queries for call timelines and event drilldowns.
- `phoenix_stats`: Value metrics and duplicate prevention counters.
- `phoenix_recover`: Programmatic forward crash recovery.
- `phoenix_windtunnel`: Deterministic fault-injection validation.

---

## 3. Verifying Provable Reliability Locally

Verify 10,000 simulated crash trials across all write boundaries:

```bash
python -m phoenix.chaos --trials 10000 --report RELIABILITY.md
```

All 10,000 trials will verify that Phoenix maintains **exactly 1 execution, 0 lost operations, and 0 duplicate writes**.
