"""Phoenix crash-recovery & deterministic fault-injection wind tunnel rehearsal.

Runs the exact flow the demo video and benchmarks showcase against a real SQLite WAL file:

  Act 1 (Pre-commit crash -> /recover replays once):
    - a.txt commits via middleware.
    - b.txt records intent (with pre-state fingerprint) and dies BEFORE writing b.txt.
    - Fresh App() runs app2.recover("") -> b.txt is written once (status="resumed").

  Act 2 (Post-commit crash -> Pre/Post State Fingerprint Protection & Autonomous Crash Detection):
    - c.txt records intent with pre_fp before the file exists.
    - c.txt IS written to disk ("gamma"), and process dies BEFORE record_outcome.
    - Fresh App() boots: Turn-1 System Prompt Alert detects interrupted op autonomously.
    - app3.recover("") -> Phoenix detects has_target_changed(pre_fp) is True
      and marks c.txt as recovered_landed WITHOUT calling the write tool a second time!

  Act 3 (ReplayLab Wind Tunnel + ddmin + Live Idempotency Guard):
    - Runs deterministic fault-injection suite (runs=5).
    - Injects timeouts, 429 rate limits, and malformed payloads at the tool boundary.
    - Delta debugging (ddmin) shrinks 11-step failures to 1 step in <2ms with 0 LLM calls.
    - Verifies 5/5 RED unguarded -> 0/5 RED (5/5 GREEN) with Phoenix Guard ON.

  Act 4 (Standalone Dark-Mode HTML Forensic Report):
    - Generates self-contained forensic HTML report via /phoenix report or --html flag.

    python demo.py [--html [path]]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK / "tests"))
from _loader import load_plugin  # noqa: E402

phx = load_plugin(WORK)
mw = phx.middleware
App = phx.core.App
op_id = phx.keys.op_id
target_fingerprint = phx.keys.target_fingerprint


def write_tool(workdir: Path):
    def _write(args) -> dict:
        p = Path(args["path"])
        if not p.is_absolute():
            p = workdir / p
        p.write_text(args["content"], encoding="utf-8")
        return {"ok": True, "path": str(p), "bytes": len(args["content"])}
    return _write


def main() -> None:
    html_arg = None
    if "--html" in sys.argv:
        idx = sys.argv.index("--html")
        if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--"):
            html_arg = sys.argv[idx + 1]
        else:
            html_arg = "phoenix-report.html"

    workdir = Path(tempfile.mkdtemp(prefix="phoenix-demo-", dir=str(WORK)))
    os.environ["PHOENIX_DATA_DIR"] = str(workdir / "data")
    os.environ.pop("PHOENIX_DB_PATH", None)  # force the on-disk WAL file, not :memory:

    # Determine report destination
    if html_arg:
        target_report_path = Path(html_arg).resolve()
    else:
        target_report_path = workdir / "phoenix-report.html"

    app = None
    app2 = None
    app3 = None

    try:
        raw_tool = write_tool(workdir)

        # =====================================================================
        # ACT 1: Pre-commit crash -> /recover replays once
        # =====================================================================
        print("=" * 60)
        print("ACT 1: Pre-commit crash -> /recover replays once")
        print("=" * 60)

        app = App()
        app.bind(type("Ctx", (), {"dispatch_tool": staticmethod(lambda t, a: raw_tool(a))})())

        # a.txt: commits normally via middleware
        a_path = str(workdir / "a.txt")
        mw.tool_execution_middleware(
            tool_name="write_file",
            args={"path": a_path, "content": "alpha"},
            next_call=lambda a: raw_tool(a),
        )

        # b.txt: intent is journaled with pre_fp, then process dies BEFORE write
        b_path = str(workdir / "b.txt")
        b_args = {"path": b_path, "content": "beta"}
        b_pre_fp = target_fingerprint("write_file", b_args)
        b_attempt = uuid.uuid4().hex
        b_op = op_id("write_file", b_args)

        app.journal.record_intent(
            b_attempt,
            b_op,
            "write_file",
            b_args,
            pre_fp=b_pre_fp,
        )

        # Process 1 dies
        app.close()
        print("PROCESS 1 killed before writing b.txt. Ledger at:", app.journal.db_path)

        # Fresh Process 2: restart and recover
        app2 = App()
        app2.bind(type("Ctx", (), {"dispatch_tool": staticmethod(lambda t, a: raw_tool(a))})())

        print("\n/phoenix status (process 2):")
        print(app2.status_text())

        print("\n/recover (process 2):")
        rec_msg1 = app2.recover("")
        print(rec_msg1)

        b_row = app2.journal.get(b_attempt)
        assert b_row is not None and b_row[4] == "resumed", (
            f"Expected b.txt status='resumed', got {b_row[4] if b_row else None!r}"
        )
        assert (workdir / "b.txt").exists(), "b.txt was not created by /recover"
        assert (workdir / "b.txt").read_text(encoding="utf-8") == "beta"
        print("Act 1 PASS: b.txt replayed once with status='resumed'.")

        # =====================================================================
        # ACT 2: Post-commit crash -> Pre/Post State Fingerprint Protection
        # =====================================================================
        print("\n" + "=" * 60)
        print("ACT 2: Post-commit crash -> Pre/Post State Fingerprint Protection")
        print("=" * 60)

        c_path = str(workdir / "c.txt")
        c_args = {"path": c_path, "content": "gamma"}
        c_pre_fp = phx.keys.target_fingerprint("write_file", {"path": str(workdir / "c.txt"), "content": "gamma"})
        c_attempt = uuid.uuid4().hex
        c_op = op_id("write_file", c_args)

        # Record intent with pre_fp
        app2.journal.record_intent(
            c_attempt,
            c_op,
            "write_file",
            c_args,
            pre_fp=c_pre_fp,
        )

        # c.txt IS written to disk, and process dies BEFORE record_outcome
        raw_tool(c_args)
        print("c.txt written to disk ('gamma'); process dies BEFORE record_outcome.")

        # Process 2 dies
        app2.close()

        # Track tool dispatches in Process 3 to prove c.txt is NOT called again
        c_calls = 0

        def spy_tool(a):
            nonlocal c_calls
            if "c.txt" in str(a.get("path", "")):
                c_calls += 1
            return raw_tool(a)

        # Fresh Process 3: restart and recover
        app3 = App()
        app3.bind(type("Ctx", (), {"dispatch_tool": staticmethod(lambda t, a: spy_tool(a))})())

        print("\n/phoenix status (process 3 before recover):")
        print(app3.status_text())

        if hasattr(app3, "system_prompt_alert"):
            print("\nAutonomous Crash Detection (Turn-1 System Prompt Alert):")
            alert = app3.system_prompt_alert()
            print(alert if alert else "(no crash alert)")

        print("\n/recover (process 3):")
        rec_msg2 = app3.recover("")
        print(rec_msg2)

        c_row = app3.journal.get(c_attempt)
        assert c_row is not None and c_row[4] == "recovered_landed", (
            f"Expected c.txt status='recovered_landed', got {c_row[4] if c_row else None!r}"
        )
        assert c_calls == 0, f"c.txt write tool dispatched {c_calls} times during recovery (expected 0)!"
        print("Act 2 PASS: c.txt recognized as already landed (status='recovered_landed') with 0 redundant writes.")

        # =====================================================================
        # ACT 3: ReplayLab Wind Tunnel + ddmin + Live Idempotency Guard
        # =====================================================================
        print("\n" + "=" * 60)
        print("ACT 3: ReplayLab Wind Tunnel + ddmin + Live Idempotency Guard")
        print("=" * 60)

        wt_report = phx.windtunnel.run_windtunnel_suite(runs=5, journal=app3.journal)
        print(phx.windtunnel.format_windtunnel_report(wt_report))

        assert wt_report.get("passed") is True, f"Wind tunnel suite failed: {wt_report}"
        print("Act 3 PASS: Wind tunnel suite passed (5/5 RED unguarded -> ddmin shrunk -> 5/5 GREEN guarded).")

        # =====================================================================
        # ACT 4: Standalone Dark-Mode HTML Forensic Report
        # =====================================================================
        print("\n" + "=" * 60)
        print("ACT 4: Standalone Dark-Mode HTML Forensic Report")
        print("=" * 60)
        if hasattr(app3, "report"):
            rep_msg = app3.report(str(target_report_path))
            print(rep_msg)
            assert target_report_path.exists(), f"Report file {target_report_path} was not created!"
            assert target_report_path.stat().st_size > 0, f"Report file {target_report_path} is empty!"
            print(f"Report verified: {target_report_path} ({target_report_path.stat().st_size} bytes)")

        # =====================================================================
        # PROOF & ASSERTIONS
        # =====================================================================
        print("\n" + "=" * 60)
        print("PROOF - files on disk:")
        for f in sorted(workdir.glob("*.txt")):
            print(f"   {f.name} = {f.read_text(encoding='utf-8')!r}")

        s = app3.journal.stats()
        print("\nledger stats:", s)

        ok = (
            sorted(f.name for f in workdir.glob("*.txt")) == ["a.txt", "b.txt", "c.txt"]
            and (workdir / "a.txt").read_text(encoding="utf-8") == "alpha"
            and (workdir / "b.txt").read_text(encoding="utf-8") == "beta"
            and (workdir / "c.txt").read_text(encoding="utf-8") == "gamma"
            and c_calls == 0
            and wt_report.get("passed") is True
            and target_report_path.exists()
            and target_report_path.stat().st_size > 0
        )
        print("\nPHOENIX DEMO:", "PASS" if ok else "FAIL")
        if not ok:
            raise SystemExit(1)

    finally:
        for a in (app, app2, app3):
            if a is not None:
                try:
                    a.close()
                except Exception:
                    try:
                        if getattr(a, "journal", None) is not None:
                            a.journal.close()
                    except Exception:
                        pass
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
