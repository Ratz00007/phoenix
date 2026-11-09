# Phoenix — 90-second demo script

**Constraint:** ≤90s, posted on X, tag @NousResearch, *show the plugin working live*.
**One rule above all:** Every screen is real. No mock, no synthetic animation — real process kill, real SQLite WAL ledger, real state fingerprint check, real delta-debugging minimizer.

Shoot at 1080p+, terminal font ≥16pt, dark theme. Captions burned in.

| # | Time | Screen (all real) | Voiceover | On-screen text |
|---|---|---|---|---|
| 1 | 0:00–0:08 | Hermes chat: agent executing a 3-step write (`a.txt`, `b.txt`, `c.txt`). First write lands. | "Agents die in the worst place: right after a write commits, before the response returns." | `write_file(a.txt) -> OK` |
| 2 | 0:08–0:16 | **Kill it mid-write.** `taskkill /F /PID <pid>` (or Ctrl-C) while journaling `b.txt`. Terminal cuts out. | "Kill the process mid-write. Laptop lid closes, connection drops. What happens now?" | `PROCESS KILLED (b.txt in-flight)` |
| 3 | 0:16–0:26 | Restart Hermes. Run `/phoenix`. The ledger shows `1 in-flight`. | "Restart. Phoenix's WAL ledger caught the intent. Not a guess: exact tool, arguments, and pre-state fingerprint." | `phoenix | 1 committed | 1 in-flight` |
| 4 | 0:26–0:38 | Run `/recover`. It executes `b.txt` exactly once (`status: resumed`). | "Run `/recover`. Phoenix replays the interrupted write once. No duplicate, zero LLM calls." | `→ resumed exactly once` |
| 5 | 0:38–0:52 | **Act 2: The Post-Commit Kill.** `c.txt` is written to disk, then killed *before* outcome is journaled. Run `/recover`. | "Now the lethal bug: what if the write *did* land before the crash? Watch Phoenix compare state fingerprints." | `has_target_changed: TRUE` |
| 6 | 0:52–1:04 | Phoenix marks `c.txt` as `recovered_landed` **without calling the write tool a second time**! | "Fingerprint match! Phoenix detects `c.txt` already landed on disk. Zero redundant writes. Customer 42 is safe." | `status='recovered_landed' (0 re-writes)` |
| 7 | 1:04–1:18 | **Act 3: ReplayLab Wind Tunnel.** Run `/phoenix windtunnel`. Chaos injection triggers timeout & 429. `ddmin` shrinks 11 steps to 1 in <2ms. Phoenix Guard flips it green. | "Built-in fault-injection wind tunnel. Delta debugging shrinks 11 steps to 1 in under two milliseconds. Five of five failures turn green with Guard on." | `ddmin: 11 steps -> 1 step (<2ms)` · `5/5 GREEN` |
| 8 | 1:18–1:25 | Determinism proof: API key unset, 0 network calls. SQLite WAL inspected via `/phoenix explain`. | "100% deterministic. Works offline with your API key unset. Pure Python standard library." | `0 LLM calls · 0 external deps` |
| 9 | 1:25–1:30 | End card: install command + repo + Nous tag. | "Phoenix. Kill your agent mid-write — it recovers having done it exactly once." | `hermes plugins install phoenix` · @NousResearch |

## Edit notes

- **Beats 2, 4, 6, and 7 are the core value:**
  - Beat 2 & 4 prove pre-commit recovery (`resumed`).
  - Beat 5 & 6 prove post-commit fingerprint protection (`recovered_landed` with 0 duplicate tool executions).
  - Beat 7 shows the ReplayLab Wind Tunnel + `ddmin` speed and determinism.
- High-contrast visual cues:
  - Red highlight on `1 in-flight` and `5/5 RED (unguarded)`.
  - Emerald green highlight on `recovered_landed` and `0/5 RED (5/5 GREEN)`.
- Audio: punchy keystrokes, clean crisp voiceover, stopwatch verified at ≤88 seconds.

## Pre-shoot checklist

- [ ] `python selfcheck.py` returns `PHOENIX SELF-CHECK: PASS`
- [ ] `python demo.py` runs all 3 acts and outputs `PHOENIX DEMO: PASS`
- [ ] `python -m unittest discover -s tests -v` all tests green
- [ ] `hermes plugins validate .` passes with 0 warnings
- [ ] Video ≤90.0s on stopwatch; `@NousResearch` in post text; repo URL as first reply
