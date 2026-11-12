# Phoenix 2.0 Threat Model & Security Specification

> **Classification:** Security Specification & Boundary Audit  
> **Status:** Hardened & Verified  
> **Hermes Plugin Security Scan:** `safe` (0 `dangerous` / 0 `warning`)  
> **Runtime Invariant:** Python 3.11+ stdlib only (0 external dependencies)

---

## 1. Assets & Security Objectives

| Asset | Confidentiality | Integrity | Availability | Threat Addressed |
| :--- | :--- | :--- | :--- | :--- |
| **Tool Arguments & Results** | **CRITICAL** (secrets redacted) | **HIGH** (canonical hash) | **MEDIUM** | Credential leakage in logs |
| **SQLite WAL Ledger** | **HIGH** (0600 file mode) | **CRITICAL** (single-writer) | **CRITICAL** (crash-safe) | File-path traversal / tampering |
| **Idempotency Keys** | **MEDIUM** | **CRITICAL** (deterministic) | **HIGH** | Duplicate charge / replay forgery |
| **State Fingerprints** | **MEDIUM** | **CRITICAL** (SHA-256) | **HIGH** | Stale state replay / drift |
| **Agent Execution Control** | **HIGH** | **CRITICAL** (human approval) | **HIGH** | Autonomous rogue mutations |

---

## 2. Trust Boundaries & Attack Surfaces

```
+-----------------------------------------------------------------------+
|  UNTRUSTED ZONE: Autonomous LLM / Model Prompts & External Tools     |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
|  BOUNDARY 1: Parameter Validation & Path Confinement                 |
|  - Confined strictly to plugin_data_dir("phoenix")                   |
|  - Directory traversal ('..', symlinks) rejected immediately          |
|  - File permissions enforced to 0600 (owner read/write only)          |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
|  BOUNDARY 2: Data Sanitization & Secret Redaction                    |
|  - Secrets accessed exclusively via agent.secret_scope.get_secret     |
|  - Recursive regex redaction (Stripe, GitHub, JWT, API tokens)       |
|  - Redacted representation persisted to SQLite WAL                   |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
|  BOUNDARY 3: Idempotency & Replay Guard                              |
|  - Strictly OFF by default (opt-in per tool invocation)              |
|  - READ tools NEVER cached across sessions                            |
|  - Pre-state fingerprint verification prevents stale drift replay    |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
|  BOUNDARY 4: Forward Recovery Execution                              |
|  - ZERO LLM calls in the recovery loop                               |
|  - Never auto-approves mutating operations                            |
|  - Dry-run simulation mode supported                                 |
+-----------------------------------------------------------------------+
```

---

## 3. Mitigations for Maintainer Review Findings

### Finding 1: Path Confinement & Sandbox Integrity
- **Vulnerability:** Unsanitized database or report paths could allow directory traversal out of the plugin sandbox.
- **Mitigation (`phoenix/security.py`):**
  - All ledger paths must resolve strictly inside `plugin_data_dir("phoenix")` via `confine_storage_path`.
  - Directory traversal tokens (`..`) and absolute path escapes immediately raise `SecurityError`.
  - Database file permissions are set to `0600` on creation.

### Finding 2: Replay Safety & Idempotency Opt-In
- **Vulnerability:** Unchecked replay of tool outputs could deliver stale reads or unexpected caching.
- **Mitigation (`phoenix/idempotency.py`):**
  - The idempotency guard is **OFF by default** (`enabled=False`).
  - Tools must explicitly opt in with unique keys.
  - Read-only tools (`SideEffect.READ`) are **strictly prohibited** from cross-session caching.
  - State fingerprints confirm that underlying files/database rows have not drifted prior to replaying.

### Finding 3: Secret Handling & Credential Scope
- **Vulnerability:** API keys and credentials passed in tool arguments could be committed to disk.
- **Mitigation (`phoenix/security.py`):**
  - Secrets are retrieved only through `agent.secret_scope.get_secret`.
  - Before writing to SQLite WAL or emitting UI payloads, `redact_secrets()` strips all credential keys and patterns (`sk_live_*`, `bearer *`, passwords, JWTs).

### Finding 4: Human-in-the-Loop & Approval Respect
- **Vulnerability:** An agent could autonomously invoke recovery and trigger unintended mutations.
- **Mitigation (`phoenix/tools.py`):**
  - Mutating actions (`recover`, `clear`, `guard_on/off`) are restricted to human owner slash commands (`/recover` or `/phoenix <action>`).
  - `phoenix_recover` supports non-destructive `--dry-run` inspection and requires explicit human invocation.

---

## 4. Honest Guarantees & Limits

- **Guarantee:** Phoenix provides **at-most-once execution + at-least-once recording**, and **exactly-once observable effect** when the adapter can verify post-state or the external system honors an idempotency key.
- **Limits:** Phoenix does not guarantee exactly-once execution for uncooperative external services that lack idempotency keys and do not expose post-state query endpoints.
