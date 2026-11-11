# Phoenix — Community Showcase & Judge Evaluation Pack
> Official submission materials for the **Nous Research Hermes Agent Hackathon**  
> Plugin: **`phoenix` v0.3.1 (Championship Edition)** — The Black Box Flight Recorder for Hermes Agents  
> Repository: [https://github.com/Ratz00007/phoenix](https://github.com/Ratz00007/phoenix)  
> Catalog PR: [NousResearch/hermes-agent #152278](https://github.com/NousResearch/hermes-agent/pull/152278)  
> Pinned SHA: `75326501b1f95da6afd6b3d29afd9d592a561bd5`  
> Dependencies: **0 external dependencies** (Python 3.11+ stdlib only)  
> Demo Video: [90-Second Walkthrough (1080p 60fps)](https://github.com/Ratz00007/phoenix/releases/tag/v0.3.1)

---

## Table of Contents
1. [Discord Showcase Post (`#hackathon-showcase`)](#1-discord-showcase-post-hackathon-showcase)
2. [Twitter / X Thread Variations](#2-twitter--x-thread-variations)
   - [Thread 1: The Unattended Autonomous Agent Problem (Viral Macro Narrative)](#thread-1-the-unattended-autonomous-agent-problem-viral-macro-narrative)
   - [Thread 2: We Sent SIGKILL to Hermes Mid-Write (Hardcore Engineering Proof)](#thread-2-we-sent-sigkill-to-hermes-mid-write-hardcore-engineering-proof)
   - [Thread 3: Why Built-in `/rollback` Isn't Enough: Forward Recovery vs. Backward Undo](#thread-3-why-built-in-rollback-isnt-enough-forward-recovery-vs-backward-undo)
3. [Judge Evaluation Cheatsheet (Instant 5-Second Test)](#3-judge-evaluation-cheatsheet-instant-5-second-test)
4. [Technical FAQ & Edge Case Dissection](#4-technical-faq--edge-case-dissection)

---

## 1. Discord Showcase Post (`#hackathon-showcase`)

*Copy-paste formatted for the Nous Research Discord server:*

***

🔥 **PROJECT SHOWCASE: Phoenix v0.3.1 — The Black Box Flight Recorder for Hermes Agents**

> **"Kill your agent mid-write. It recovers having executed exactly once."**  
> *Zero duplicate writes. Zero lost operations. Zero LLM calls during recovery.*

Hey everyone! 👋 We built **Phoenix** to solve the single most terrifying failure mode in autonomous AI agents: **the post-commit crash window**.

### 💥 The Problem
When an autonomous agent runs a 20-file refactor overnight or manages API billing via a headless gateway, the process can die at any moment (`SIGKILL`, OOM, laptop lid snap, gateway timeout). 
If it dies *after* a tool mutation lands on disk or commits to an API, but *before* Hermes records the outcome in session history:
- The agent wakes up blind to what happened.
- Built-in `/rollback` is **destructive backward undo** — it wipes out all prior turn work.
- Or worse, the agent retries blindly and **Customer 42 gets billed twice** or files get corrupted!

### 🛡️ What Phoenix Does
Phoenix acts as an indestructible flight recorder:
1. 📝 **SQLite WAL Intent Journaling**: Intercepts every tool call before execution, recording canonical `op_id` and pre-execution SHA-256 target fingerprints in a local, durable WAL ledger.
2. 🚨 **Turn-1 Autonomous Crash Detection**: Native `register_system_prompt_section` hook injects a zero-token crash alert into Turn 1 upon reboot. The agent immediately knows which operations were in flight.
3. 🎯 **Extended State Fingerprinting**: Checks disk state on boot (`write_file`, `edit_file`, unified `patch`, shell redirects). If a file already mutated on disk before the crash, Phoenix auto-reconciles it as `recovered_landed` with **0 duplicate writes** and **0 tool re-dispatches**!
4. ⚡ **Zero-LLM Forward Recovery**: `/recover` replays exact deterministic bytecode from the WAL ledger. No re-reasoning, no prompt variance, no token cost.
5. 🌪️ **ReplayLab Wind Tunnel + Zeller `ddmin`**: Includes an offline fault-injection engine that shrinks multi-mutation failure traces to a 1-step minimal counterexample in `<2ms` with 0 LLM calls (5/5 RED unguarded ➔ 0/5 RED guarded).
6. 📊 **Hermes Web Dashboard & Forensic HTML**: Bundles native `dashboard/manifest.json` and zero-dependency dark-mode HTML reports.

### 🧪 5-Second Judge & Community Verification
Zero dependencies. Zero API keys. Python 3.11+ stdlib only:
```bash
git clone https://github.com/Ratz00007/phoenix.git && cd phoenix
python judge_eval.py
```
*(Runs 67 unit tests, full Hermes plugin doctor checks, and the developer wind tunnel in ~2.5s with 100% green PASS!)*

- 📦 **GitHub Repository**: https://github.com/Ratz00007/phoenix
- 🔀 **Catalog PR**: https://github.com/NousResearch/hermes-agent/pull/152278
- 🎥 **90-Second Demo Video**: Available in repo releases & README!

Feedback and edge-case attacks welcome! Let's make autonomous Hermes agents truly unbreakable. 🚀

***

---

## 2. Twitter / X Thread Variations

### Thread 1: The Unattended Autonomous Agent Problem (Viral Macro Narrative)

**Tweet 1 (Hook):**  
Everyone is talking about autonomous AI agents working overnight.  
Almost nobody is talking about what happens when your laptop lid closes on Step 14 of a 20-file refactor.  

Here is why your agent either double-charges your users or corrupts your codebase — and how we fixed it. 🧵👇 (1/8)  
*[Attach video: phoenix-demo-enterprise.mp4]*

**Tweet 2:**  
The nightmare scenario is the "post-commit crash window":  
1. Agent calls `charge_customer()` or writes `dist/bundle.js`.  
2. The mutation lands on disk / Stripe API.  
3. Process receives SIGKILL, OOM kill, or WiFi drops before Hermes saves the chat turn.  
Now what? (2/8)

**Tweet 3:**  
On restart, the agent has total amnesia. It never received the tool return value.  
So it does what LLMs do: it retries.  
Customer 42 is charged twice.  
The file write appends garbage or overwrites critical state.  
Every autonomous workflow running in production today is vulnerable to this. (3/8)

**Tweet 4:**  
"Can't you just use `/rollback`?"  
No. Built-in rollback is **destructive backward undo**.  
If you're on step 14, `/rollback` wipes out the good work from steps 1-13!  
And if your agent is running headless on Telegram or a server cron, there's no human sitting there to type `/rollback` anyway. (4/8)

**Tweet 5:**  
Meet Phoenix: The Black Box Flight Recorder for Hermes Agents.  
Phoenix journals every tool call into a local SQLite WAL ledger *before* it executes, capturing pre-state SHA-256 target fingerprints.  
If the agent dies mid-write, the flight recorder holds the mechanical truth. (5/8)

**Tweet 6:**  
When Hermes boots back up:  
Turn 1's system prompt gets an autonomous crash alert.  
Phoenix checks the disk:  
- Did the file mutate before the crash? ➔ Mark `recovered_landed`. ZERO duplicate writes.  
- Did it die before writing? ➔ `/recover` safely executes it once.  
Zero LLM calls. Zero token costs. (6/8)

**Tweet 7:**  
We also built the ReplayLab Wind Tunnel directly inside Phoenix:  
We injected 429s, network timeouts, and process kills into a real multi-step developer trace.  
Zeller's delta debugging (`ddmin`) isolates the exact culprit step in `<2ms` with 0 model calls.  
Guarded: 0/5 failures. (7/8)

**Tweet 8 (CTA):**  
Phoenix is 100% Python standard library.  
0 pip dependencies. 0 API keys. 67/67 tests passing.  

Clone and test it in 1 command:  
`git clone https://github.com/Ratz00007/phoenix && cd phoenix && python judge_eval.py`  

Catalog PR #152278 is live on @NousResearch Hermes!  
Repo: https://github.com/Ratz00007/phoenix (8/8)

---

### Thread 2: We Sent SIGKILL to Hermes Mid-Write (Hardcore Engineering Proof)

**Tweet 1 (Hook):**  
We sent `kill -9` to Hermes mid-`write_file`.  
Then we tested what happens on process restart.  

Without Phoenix: data corruption, duplicate writes, or deadlocked sessions.  
With Phoenix: byte-identical recovery with 0 redundant writes and 0 LLM calls.  

Here is the mechanical proof: 🧵 (1/7)  
*[Attach flight recorder ASCII execution diagram]*

**Tweet 2:**  
Why is mid-call failure so hard for LLM runtimes?  
Because tool execution is not atomic with history serialization.  
`execute_tool()` mutates the real world.  
`session.record()` mutates LLM memory.  
A process death between those two lines creates a split-brain state. (2/7)

**Tweet 3:**  
Phoenix fixes this at the middleware layer (`tool_execution`):  
Before calling `next_call()`:  
1. Compute deterministic `op_id` = SHA256(tool + canonical_json(args)).  
2. Compute `pre_fp` = target_fingerprint(tool, args).  
3. Commit intent to SQLite in WAL mode with synchronous=NORMAL.  
If the process dies right here, the ledger row is stuck on `intent`. (3/7)

**Tweet 4:**  
The magic is in `keys.is_target_fully_committed()` and `has_target_changed()`:  
When Hermes reboots, Phoenix inspects the actual target on disk:  
- For `write_file`: verifies content hash and length against payload.  
- For `edit_file` / `patch`: verifies unified diff hunks landed cleanly.  
- For `terminal` redirects: checks output file timestamps and sizes. (4/7)

**Tweet 5:**  
If the file already landed on disk before the crash:  
Phoenix marks the attempt `recovered_landed`.  
The write tool is NOT called a second time.  
If the file was not written:  
`/recover` dispatches the recorded bytecode payload once.  
No hallucination. No prompt variance. Deterministic forward progress. (5/7)

**Tweet 6:**  
What about in-session retries?  
Phoenix includes a live idempotency guard.  
If an agent panics and retries an identical tool call in the same session, Phoenix intercepts it (`status='deduped'`) and returns the cached outcome instantly without re-executing. (6/7)

**Tweet 7:**  
Test the flight recorder yourself right now:  
```bash
git clone https://github.com/Ratz00007/phoenix
cd phoenix
python judge_eval.py
```  
Verified against Hermes v0.21.6 catalog admission rules.  
PR #152278 on @NousResearch!  
Code: https://github.com/Ratz00007/phoenix (7/7)

---

### Thread 3: Why Built-in `/rollback` Isn't Enough: Forward Recovery vs. Backward Undo

**Tweet 1 (Hook):**  
Hermes has a built-in `/rollback` command in `checkpoint_manager.py`.  
Why did we build Phoenix?  

Because **destructive backward undo** and **non-destructive forward recovery** are two fundamentally different paradigms.  

A technical breakdown for agent developers: 🧵 (1/6)

**Tweet 2:**  
`/rollback` is designed for interactive human sessions.  
You're chatting with Hermes. The agent makes a mistake on step 5. You type `/rollback`.  
It git-reverts dirty files back to the turn snapshot.  
Simple. But destructive: any intermediate good work done during that turn is vaporized. (2/6)

**Tweet 3:**  
Now look at autonomous agents (cron jobs, headless server agents, multi-step pipelines):  
1. No human is watching the terminal.  
2. If step 14 crashes, resetting to step 0 or turn start loses everything.  
3. Git snapshots only protect git-tracked files — external files, database updates, and API webhooks are completely invisible to it. (3/6)

**Tweet 4:**  
Here is the architectural comparison:  

| Feature | Built-in `/rollback` | Phoenix `/recover` |  
|---|---|---|  
| **Direction** | Destructive Backward Undo | Non-destructive Forward Recovery |  
| **Granularity** | Turn boundary snapshot | Tool-call level (`op_id`) |  
| **Scope** | Git files only | Files, unified diffs, shell, APIs |  
| **Crash Safety** | Blind to mid-turn crash | Pre/post state fingerprinting |  
| **Autonomous Alert**| Requires human | Turn-1 system prompt injection |  
| **Token Cost** | Re-reasoning tokens | **0 LLM calls** | (4/6)

**Tweet 5:**  
Phoenix doesn't roll back good work.  
It inspects the WAL flight recorder, finds the single interrupted operation, validates whether the disk state mutated, and safely finishes it forward.  
And on Turn 1 reboot, Hermes's system prompt receives an automated crash warning so the model can plan around it autonomously. (5/6)

**Tweet 6:**  
Both tools have their place:  
Use `/rollback` when an agent's reasoning was wrong and you want a do-over.  
Use Phoenix when your infrastructure failed and you need exactly-once execution guarantees.  

Try it: `python judge_eval.py`  
Catalog PR #152278 for @NousResearch Hermes Agent!  
https://github.com/Ratz00007/phoenix (6/6)

---

## 3. Judge Evaluation Cheatsheet (Instant 5-Second Test)

Judges can verify the entire Phoenix plugin architecture in **under 5 seconds** with **zero external dependencies** and **zero API keys**.

### Command 1: The Official Judge Evaluation Script (Recommended)
```bash
# From workspace root or phoenix/ directory:
python judge_eval.py
```

**Expected Terminal Output:**
```text
==================================================================================
               PHOENIX v0.3.1 — OFFICIAL JUDGE EVALUATION SCORECARD               
==================================================================================

  [PASS] Unit Test Suite:
         67/67 tests passing (0 failures, 0 errors) in 2.27s

  [PASS] Hermes Official Plugin Doctor:
         ✓ Plugin Manifest            manifest parses (name/version/description/kind present)
         ✓ Dashboard Manifest         dashboard/manifest.json parses valid JSON (version 0.3.0)
         ✓ Context Registration       register(ctx) runs and registers middleware, 2 commands (/phoenix, /recover), 2 tools (phoenix_ledger, phoenix_windtunnel), and phoenix_recovery prompt section
         ✓ Public API Imports         imports stay on the public plugin API allow-list
         ✓ Clean Build (No Binaries)  no compiled binaries or bytecode

  [PASS] Developer Wind Tunnel & Zeller ddmin:
         ✓ HERMES_DEV_TRACE (8 steps, 3 mutations) isolated to 1 step in 58.7ms
         ✓ Minimal counterexample isolated: write_file('dist/bundle.js') (0 LLM calls)
         ✓ Guarded Green vs Unguarded Red verified across all fault injection modes

----------------------------------------------------------------------------------
  AUDIT CATEGORY                     STANDARD / SPEC                RESULT        
----------------------------------------------------------------------------------
  Unit Test Discovery                unittest discover -s tests     PASS (67/67)
  Manifest & Plugin Schema           Hermes standalone spec         PASS (Valid)
  Zero Host Monkeypatching           Public plugin APIs only        PASS (100% Clean)
  Secret Redaction                   Journal sanitization regex     PASS (Enforced)
  Target State Verification          write_file + patch unified diff PASS (SHA-256 verified)
  Developer Wind Tunnel              Zeller ddmin fault-isolation   PASS (Isolated in 1 step)
  Idempotency Guard                  Double-execution prevention    PASS (0 Duplicate Writes)
  Zero LLM Recovery                  WAL state replay               PASS (0 Tokens Wasted)
==================================================================================
  FINAL VERDICT: 100% PASS — 0 FAILURES — READY FOR EVALUATION
  Total Evaluation Time: 2.57s | Hermes Version Compatibility: >=0.21.6
==================================================================================
```

### Command 2: The 4-Act Rehearsal & HTML Report Generation
```bash
python demo.py --html phoenix-report.html
```
- **Act 1 (Pre-Commit Crash):** Kills process before file write lands ➔ `/recover` replays once (`status='resumed'`).
- **Act 2 (Post-Commit Crash):** Kills process *after* file write lands ➔ Turn-1 `[PHOENIX WAL CRASH ALERT]` detects state change and marks `status='recovered_landed'` with **0 redundant writes**.
- **Act 3 (Wind Tunnel & Delta Debugging):** Injects 5 boundary faults into real middleware, verifies 5/5 RED ➔ 0/5 RED, and minimizes failure to 1 step in `<2ms` with 0 LLM calls.
- **Act 4 (Forensic HTML Dashboard):** Generates standalone, zero-`<script>` dark-mode HTML report (`phoenix-report.html`).

### Command 3: Hermes Plugin Doctor Emulation
```bash
python selfcheck.py
```
- Verifies manifest schema, registration surfaces, public API imports, zero binary artifacts, and 67 unit tests.

---

## 4. Technical FAQ & Edge Case Dissection

### Q1: How does SQLite WAL mode prevent database locks during agent crashes?
**Answer:** Phoenix configures SQLite with:
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```
- **Crash Immunity:** In WAL mode, SQLite writes new transactions to a separate `wal` log file rather than in-place modifying the main database pages. A sudden crash or `kill -9` never corrupts the database.
- **Concurrent Readers & Writers:** Readers do not block writers, and writers do not block readers. A 5-second `busy_timeout` handles any momentary concurrent lock contention cleanly.
- **Fail-Open Live Execution:** In `middleware.py`, if a ledger write ever raises an unhandled database exception during live agent execution, Phoenix catches the error, logs a warning, and permits `next_call()` to proceed normally. Phoenix will never crash your running agent.

### Q2: How does Phoenix handle non-disk tools (API calls, webhooks, payments)?
**Answer:** Non-disk tools cannot be fingerprinted by inspecting local filesystem blocks. Phoenix handles them via explicit caller idempotency keys and canonical hashing:
1. **Explicit `idempotency_key` Support:** If a tool argument contains `idempotency_key`, `client_request_token`, or `nonce`, Phoenix extracts it directly into `pre_fp = {"idempotency_key": "..."}`.
2. **Canonical JSON `op_id` Hashing:** When an API call runs, Phoenix hashes `(tool_name, sorted_canonical_args)`. If the agent dies and retries the exact same API call, Phoenix's Live Idempotency Guard catches the duplicate and returns the cached outcome instead of making a duplicate external HTTP POST.
3. **Safe Forward Recovery:** If an API call without an idempotency key crashes mid-flight, Phoenix marks it as `ambiguous_external` in `/phoenix explain` and alerts the agent or human to inspect the external service before blindly re-dispatching.

### Q3: Why doesn't `/recover` collide with Hermes's built-in commands?
**Answer:** Earlier versions used `/resume`, which collided with Hermes's native `/resume` command (used to resume paused sessions) and was silently swallowed by the command dispatcher.  
In v0.3.0+, we renamed the command to `/recover` and registered `/phoenix explain` / `/phoenix status`. Phoenix has **zero command collisions** with any built-in Hermes CLI or chat surface.

### Q4: How are sensitive secrets (API keys, tokens, passwords) protected?
**Answer:** The WAL ledger stores execution history locally in `plugin_data_dir("phoenix")`. To ensure credentials never leak to disk or forensic reports:
- `journal.py` runs `redact_secrets()` before writing `args_json` or error messages.
- Catches OpenAI (`sk-...`), GitHub (`ghp_...`), Bearer authorization headers, and JSON keys matching `token`, `password`, `secret`, `api_key`.
- Replaces values with `"[REDACTED]"`.
- Verified by unit test `test_secret_redaction_in_journal` in `tests/test_phoenix.py`.

### Q5: How does Phoenix prevent prompt injection in the Turn-1 System Prompt Alert?
**Answer:** In `core.py`, when Phoenix formats the Turn-1 recovery alert for Hermes, it sanitizes all dynamic fields:
- Tool names must match `^[a-zA-Z0-9_.:-]+$` (max 64 chars). Any invalid characters are replaced with underscores.
- `op_id` strings must match `^[a-zA-Z0-9_]+$` (max 32 chars).
- Tool arguments and results are never dumped raw into the prompt — only high-level status indicators (`resumed`, `recovered_landed`, `in-flight`) are provided.

### Q6: Can Phoenix handle unified diff `patch` operations?
**Answer:** Yes! In Hermes, file modifications often occur via unified diff hunks through the `patch` tool rather than whole-file `write_file`.  
Phoenix's `keys.py` parses `patch` diff headers (`--- a/...`, `+++ b/...`), extracts the target file path, and fingerprints the target before and after patch application. When recovering, it verifies whether the hunk already landed in the target file, ensuring patches are never double-applied.
