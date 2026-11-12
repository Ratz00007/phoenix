# Phoenix 2.0 System Architecture

> **Phoenix — The Exactly-Once Trust Layer for Autonomous Agents**  
> Visual Flight Recorder + Zero-LLM Forward Recovery + 10,000-Crash Provable Durability

---

## 1. Architectural Philosophy: The Blind Window

Autonomous agents interact with real-world side effects: charging credit cards, writing source code, dispatching emails, and altering production databases.

Between the moment an agent dispatches a mutating tool and the moment the host receives the response, there exists a critical failure window: **The Blind Window**.

```
[Agent Host]                           [Target System (Stripe / Disk)]
     |                                              |
     |---- (1) Dispatch write_file / charge ------->|
     |                                              |
     |                                    [Mutation Commits]
     |                                              |
   [💥 SIGKILL / Power Loss / Host OOM]            |
     |                                              |
     x<--- (2) Dropped Network Response ------------+
```

### The Failure Modes of Existing Agent Systems:
1. **Blind Retry Agents:** When restarted, the LLM observes no response and retries the prompt. The customer is charged twice ($240 -> $480) or the file is overwritten with corrupted data.
2. **Rollback Agents (`/rollback`):** Blindly reverts local git commits or deletes local temp files without knowing that the remote payment or server write already succeeded. State diverges permanently.
3. **Phoenix Architecture:** Intercepts every tool call. Intent and cryptographic state hashes are journaled to SQLite WAL and `fsync`ed *before* execution. Upon restart, Phoenix reconciles in-flight operations non-destructively with **0 duplicate executions** and **0 LLM tokens**.

---

## 2. Core Subsystems

```
                                +-------------------+
                                |   Hermes Agent    |
                                +-------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                            PHOENIX RUNTIME LAYER                                  |
|                                                                                   |
|  +------------------------+      +------------------------+      +-------------+  |
|  | Interception Middleware| ---> | Deterministic Hash &   | ---> | ExactlyOnce |  |
|  | (tool_execution)       |      | Fingerprint Engine     |      | Controller  |  |
|  +------------------------+      +------------------------+      +-------------+  |
|              |                                                          |         |
|              v                                                          v         |
|  +-----------------------------------------------------------------------------+  |
|  | SQLite WAL Durability Ledger (synchronous=FULL, mode 0600, single-writer)  |  |
|  | - Table calls: UUID, args_hash, side_effect, idempotency_key, pre/post_fp  |  |
|  | - Table events: atomic journal of begin, pre_state, post_state, commit      |  |
|  | - Table recoveries: metrics of ops recovered, dupes prevented, $ saved      |  |
|  +-----------------------------------------------------------------------------+  |
|              ^                                                                    |
|              |                                                                    |
|  +------------------------+      +------------------------+      +-------------+  |
|  | Zero-LLM Forward       |      | Value Telemetry Engine |      | Desktop UI  |  |
|  | Recovery Engine        |      | ($ Saved, Dupes)       |      | Timeline    |  |
|  +------------------------+      +------------------------+      +-------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Data Contracts & Durability Protocol

### 3.1 SQLite WAL Ledger Schema
- **`journal_mode=WAL`**: Concurrency without reader-writer locking contention.
- **`synchronous=FULL`**: Guarantees disk sync before write acknowledgement.
- **Permissions `0600`**: Confined strictly to plugin storage (`plugin_data_dir("phoenix")`).
- **Single-Writer Pattern**: All mutations flow through `Ledger` class methods; readers use lightweight read-only connections.

### 3.2 Two-Phase Journaling Sequence
For every tool invocation:
1. **Phase 1 (`begin`)**:
   - Classify side effect (`read`, `write`, `external`).
   - Hash arguments canonically (`args_hash = SHA256(canonical_json(args))`).
   - Capture pre-state fingerprint (`pre_fingerprint`).
   - Persist record in `calls` table with status `PENDING`.
   - Append `begin` and `pre_state` events to `events` table and `fsync`.
2. **Execution**: Invoke underlying tool.
3. **Phase 2 (`commit`)**:
   - Capture post-state fingerprint (`post_fingerprint`).
   - Append `post_state` event to `events`.
   - Update call status to `COMMITTED` with duration in milliseconds.
   - Append `commit` event and `fsync`.

If execution crashes before Phase 2 completes, the record remains `PENDING` in SQLite WAL — serving as an undeniable cryptographic flight recorder marker.

---

## 4. Zero-LLM Forward Recovery Engine

When Phoenix boots after an interruption, `session_start_hook` detects any stranded `PENDING` calls:
1. **Target State Probing**: Phoenix computes the current post-state fingerprint or queries adapter idempotency endpoints.
2. **Reconciliation Decision**:
   - **If the side-effect landed:** Phoenix marks the call `RECOVERED` without re-executing it. `dupes_prevented` is incremented.
   - **If the side-effect did not land:** Phoenix marks the call `FAILED`, clearing the path for safe retry. `ops_recovered` is incremented.
3. **Zero Token Cost**: Recovery executes in < 5ms via deterministic Python logic without wasting LLM reasoning loops or tokens.

---

## 5. External Adapters

- **Stripe (`phoenix/adapters/stripe.py`)**: Passes deterministic `Idempotency-Key` headers on charges; probes charge status on recovery.
- **Email (`phoenix/adapters/email.py`)**: Computes deterministic `Message-ID` from content and recipient to prevent duplicate email dispatch.
- **SQL (`phoenix/adapters/sql.py`)**: Executes atomic upserts keyed on business identifiers and computes cryptographic row fingerprints.

---

## 6. Honest Guarantees & Limits (§3.6)

> **Verbatim Guarantee:** Phoenix provides **at-most-once execution + at-least-once recording**, and **exactly-once observable effect** when the adapter can verify post-state or the external system honors an idempotency key. It does not claim exactly-once for arbitrary unverifiable side effects without idempotency support.
