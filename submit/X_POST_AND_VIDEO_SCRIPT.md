# Phoenix v0.3.0 — X Post & 90-Second Video Script

---

## 1. Official X (Twitter) Post Copy

> **Post Target:** Post on X with video attachment, tagging `@NousResearch`.  
> **Character Count:** Optimized for X Premium / standard thread format.

### Primary Tweet:
```text
Kill your agent mid-write. It recovers having executed exactly once — guaranteed by pre/post state fingerprints.

Introducing Phoenix v0.3.0 for @NousResearch Hermes: the crash-proof execution journal, idempotency guard, Web Dashboard & fault-injection wind tunnel.

Here is the 90s proof: 🧵👇
```

### Video Attachment Tweet / Thread Details:
```text
Why Phoenix v0.3.0 is a game-changer for autonomous Hermes agents:

1️⃣ Transactional WAL Journal + Pre/Post Fingerprinting:
Catches the lethal post-commit window. SHA-256 state hashes across write_file, edit_file, patch diffs, and shell redirects prove whether a write landed before a crash — preventing duplicate writes with ZERO LLM calls.

2️⃣ Turn-1 Autonomous Crash Detection:
Hooks into register_system_prompt_section("phoenix_recovery"). When Hermes boots after an interruption, the agent autonomously sees pending recoveries before turn 1 begins.

3️⃣ ReplayLab Wind Tunnel + ddmin Minimizer:
Deterministic fault-injection suite. Injects 429s, timeouts, and payload corruptions. Zeller's delta debugging shrinks 11-step failure traces to 1 step in <2ms. (5/5 RED -> 5/5 GREEN).

4️⃣ Native Web Dashboard & HTML Forensic Reports:
Embeds directly into the Hermes UI via dashboard/manifest.json, with standalone zero-dependency dark-mode HTML forensic exports (/phoenix report).

Zero external dependencies. Python 3.11+ stdlib only. 100% deterministic.

GitHub: https://github.com/Ratz00007/phoenix
Catalog PR: https://github.com/NousResearch/hermes-agent/pull/[PR_NUMBER]

#Hermes #AI #AutonomousAgents #NousResearch
```

---

## 2. 90-Second Video Script

**Constraint:** Exactly $\le 90$s. Every screen is real (no simulated UI, no fake mockups). Real terminal, real Hermes process kill, real SQLite WAL ledger, real state hashes, real wind tunnel, real HTML report.

**Screen Setup:** 1080p+, terminal font $\ge 16$pt, dark mode theme. Burned-in captions.

| # | Time | Screen (All Real) | Voiceover | On-Screen Text Overlay |
|---|---|---|---|---|
| **1** | 0:00–0:09 | Hermes CLI session: agent executing a multi-step task (`a.txt`, `b.txt`, `c.txt`). First step commits. | "Agents die in the worst window: after a write commits, before the response returns. The agent retries, and customer 42 gets billed twice." | `write_file(a.txt) -> OK` |
| **2** | 0:09–0:17 | **Kill the agent mid-write.** Execute `taskkill /F /PID <pid>` while journaling `b.txt`. Terminal terminates abruptly. | "Kill the process mid-write. Network drop, OOM, gateway timeout. What happens when you restart?" | `PROCESS KILLED (b.txt in-flight)` |
| **3** | 0:17–0:27 | Launch fresh Hermes. Prompt shows **Turn-1 System Prompt Crash Alert**. Run `/phoenix`. Ledger shows `1 in-flight`. | "Restart Hermes. Phoenix's Turn-1 crash alert autonomously detects the interruption. The WAL ledger caught the exact intent." | `Turn-1 Crash Alert: 1 in-flight` · `phoenix status` |
| **4** | 0:27–0:38 | Execute `/recover`. Interrupted call `b.txt` is replayed once (`status='resumed'`). File verified on disk. | "Run `/recover`. Phoenix finishes the interrupted call exactly once. Zero duplicates, zero LLM calls." | `b.txt -> status='resumed' (1 write)` |
| **5** | 0:38–0:52 | **Act 2: The Lethal Post-Commit Crash.** `c.txt` writes to disk (`"gamma"`), then process dies before outcome row. Fresh restart shows crash alert. | "Now the lethal bug: what if the file DID land on disk before the crash? Watch Phoenix inspect SHA-256 pre/post fingerprints." | `has_target_changed: TRUE` |
| **6** | 0:52–1:04 | Run `/recover`. Phoenix reports target already mutated, marks `recovered_landed` with **0 tool re-writes**! | "Fingerprint match! Phoenix sees `c.txt` already landed. It marks it recovered with zero redundant writes. Customer 42 is safe." | `status='recovered_landed' (0 redundant writes)` |
| **7** | 1:04–1:17 | **Act 3: ReplayLab Wind Tunnel.** Run `/phoenix windtunnel`. Chaos injection triggers timeout & 429. `ddmin` minimizes 11 steps to 1 in <2ms. Guard flips suite green. | "Built-in fault-injection wind tunnel. Delta debugging shrinks an 11-step failure trace to 1 step in under two milliseconds. Five of five failures turn green." | `ddmin: 11 steps -> 1 step (<2ms)` · `5/5 GREEN` |
| **8** | 1:17–1:24 | **Act 4: Web Dashboard & HTML Report.** Open Hermes Web Dashboard (`dashboard/manifest.json`) and display `/phoenix report` dark-mode receipt. | "Inspect via the native Hermes Web Dashboard or export an instant, zero-dependency dark-mode HTML forensic receipt." | `Hermes Web Dashboard` · `/phoenix report` |
| **9** | 1:24–1:30 | Determinism card & call-to-action: API key unset, 0 network calls. Install command & @NousResearch handle. | "100% deterministic. Works offline with your API key unset. Pure standard library. Phoenix: kill your agent mid-write, recover once." | `hermes plugins install phoenix` · @NousResearch |

---

## 3. Production & Pre-Shoot Checklist

- [ ] Run `python selfcheck.py` -> verifies `PHOENIX SELF-CHECK: PASS` across all 6 checks.
- [ ] Run `python demo.py --html phoenix-report.html` -> verifies `PHOENIX DEMO: PASS` and opens HTML report.
- [ ] Run `python -m unittest discover -s tests -v` -> verifies all unit tests green.
- [ ] High-contrast visual cues:
  - Red highlight for `1 in-flight` and `5/5 RED (unguarded)`.
  - Emerald green highlight for `recovered_landed`, `5/5 GREEN (guarded)`, and HTML forensic report.
- [ ] Stopwatch verified at $\le 88.0$ seconds.
- [ ] Tag `@NousResearch` in the primary tweet with GitHub repository link in the first reply.
