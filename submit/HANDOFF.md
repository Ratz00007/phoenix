# Phoenix v0.3.0 — Submission Handoff (Do these in order)

Deadline: **Wed 11 Nov 2026, 5:00 PM ET = 22:00 UTC** (10:00 PM your time).  
Target: everything completed by **Tue 10 Nov**; Wed is buffer only.

## 0. Replace Placeholders

- `submit/phoenix.yaml`: `repo: https://github.com/Ratz00007/phoenix`, `maintainer: Ratz00007`, and the 40-char `sha`.
- `submit/PR-description.md` & `submit/SUBMISSION_CHECKLIST.md`: Pinned 40-char commit SHA.

## 1. Create the Repo and Push

```bash
cd "C:\Users\ratin\Downloads\Hermes plugn compition\phoenix"
git init -b main
git add .
git commit -m "feat: Phoenix v0.3.0 transactional WAL crash journal & ReplayLab ddmin wind tunnel"
gh repo create Ratz00007/phoenix --public --description "Transactional SQLite WAL crash-recovery journal, idempotency guard & ReplayLab ddmin wind tunnel for Hermes Agent" --source=. --remote=origin --push
```

## 2. Re-verify from a Clean Clone (The Receipts)

```bash
git clone https://github.com/Ratz00007/phoenix && cd phoenix
hermes plugins validate .                       # must print "Validation passed."
hermes plugins doctor . --ci                    # must print "OK ... registration passed"
python -m unittest discover -s tests -v         # all unit tests green
python selfcheck.py                             # PHOENIX SELF-CHECK: PASS
python demo.py --html phoenix-report.html       # PHOENIX DEMO: PASS (all 4 acts)
```

Pin the SHA **after** these pass:

```bash
$sha = (git rev-parse HEAD).Trim()
# Paste $sha into submit/phoenix.yaml, submit/PR-description.md, and submit/SUBMISSION_CHECKLIST.md
```

## 3. Open the Catalog PR

1. Fork `NousResearch/hermes-agent`.
2. Add ONE file `plugin-catalog/phoenix.yaml` (the contents of `submit/phoenix.yaml` with the pinned 40-char commit SHA).
3. PR title: `Add plugin: phoenix (crash-proof execution journal, idempotency guard & wind tunnel)`.
4. PR body: paste `submit/PR-description.md`, fill the two `[PR DAY]` markers.
5. Attach real Hermes screenshots (`/phoenix status` after a kill, post-`/recover` fingerprint proof, and `/phoenix windtunnel` report).

Open the PR **Monday**, not Wednesday, to allow time for CI review.

## 4. Video (Tue 10 Nov)

- Shoot from `submit/video-script-90s.md` / `submit/X_POST_AND_VIDEO_SCRIPT.md`.
- Act 1 (Pre-commit kill -> `/recover`), Act 2 (Post-commit kill -> State Fingerprint prevents double-write), Act 3 (ReplayLab Wind Tunnel + `ddmin`).
- Post on X, tag `@NousResearch` in the post text; repo URL (`https://github.com/Ratz00007/phoenix`) as the **first reply**.
- ≤90.0s on a stopwatch. Dark theme, captions burned in.

## 5. Form (Wed, before 3:00 PM ET)

- Submit the PR link + video link via the official form at least 2h before the 5 PM ET deadline.

## 6. If Anything Flakes

- `hermes plugins validate .` is the gate. If it fails, read the ✗ line and fix only that.
- Phoenix runs with 0 LLM calls in recovery and replay loops: `/recover` and `/phoenix windtunnel` need no API key, so a model provider outage will not disrupt video day or local rehearsal.
