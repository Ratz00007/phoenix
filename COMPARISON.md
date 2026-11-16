# Phoenix vs Alternatives

Why **Phoenix v2.0.0** provides the missing exactly-once execution layer for autonomous Hermes agents.

| Capability | Blind Retry | Hermes Built-in `/rollback` | Temporal / External Orchestrator | **Phoenix v2.0.0** |
| :--- | :--- | :--- | :--- | :--- |
| **Crash Recovery Direction** | Re-runs blindly | Destructive backward undo | Forward replay | **Non-destructive forward recovery** |
| **Post-Commit Crash Protection** | ❌ Double-charges / corrupts files | ❌ Deletes local work; remote state desyncs | ⚠️ Requires explicit activity heartbeats | ✅ **SHA-256 pre/post target fingerprinting (`recovered_landed`)** |
| **LLM Tokens Used in Recovery** | High (re-generates from scratch) | High (re-prompts turn) | Zero | ✅ **Zero LLM calls (deterministic WAL replay)** |
| **Runtime Dependencies** | None | Built-in | Server cluster + SDK + Redis/Postgres | ✅ **0 external deps (Python 3.11+ stdlib + SQLite WAL)** |
| **Granularity** | Turn-level | Turn-level | Workflow activity | ✅ **Individual tool call (`op_id`)** |
| **Fault Debugging** | Manual log grepping | None | Replay history UI | ✅ **Built-in Zeller `ddmin` Wind Tunnel + Chaos Engine** |
| **Observability UI** | None | CLI output only | External Temporal Web UI | ✅ **Hermes Desktop SDK surface + Web Dashboard + HTML report** |
| **Owner Approval Preserved** | N/A | Manual `/rollback` | Separate UI | ✅ **Strictly owner-only `/recover` (zero model-callable replay)** |
