"""Phoenix crash-recovery & deterministic fault-injection wind tunnel rehearsal.

Runs the deterministic crash-recovery and Wind Tunnel rehearsal against a real SQLite WAL file:

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
    - Delta debugging (ddmin) shrinks 8-step failures to 1 step in milliseconds with 0 LLM calls.
    - Verifies 5/5 RED unguarded -> 0/5 RED (5/5 GREEN) with Phoenix Guard ON.

  Act 4 (Standalone Dark-Mode HTML Forensic Report):
    - Generates self-contained forensic HTML report via /phoenix report or --html flag.

    python demo.py [--html [path]] [--chaos]
"""

from __future__ import annotations

import importlib
import json
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


def run_chaos_demo() -> None:
    """Run a live multi-step crash-and-recover chaos scenario against a temp SQLite WAL ledger."""
    workdir = Path(tempfile.mkdtemp(prefix="phoenix-chaos-demo-", dir=tempfile.gettempdir()))
    prev_data_dir = os.environ.get("PHOENIX_DATA_DIR")
    prev_db_path = os.environ.get("PHOENIX_DB_PATH")
    os.environ["PHOENIX_DATA_DIR"] = str(workdir / "data")
    os.environ.pop("PHOENIX_DB_PATH", None)

    app1 = None
    app2 = None
    try:
        print("=" * 68)
        print("PHOENIX CHAOS DEMO: Multi-Step Crash & Forward Recovery (SQLite WAL)")
        print("=" * 68)

        raw_tool = write_tool(workdir)
        exec_counts: dict[str, int] = {}

        def tracked_write(tool_name, args):
            key = op_id(tool_name, args)
            exec_counts[key] = exec_counts.get(key, 0) + 1
            return raw_tool(args)

        # Multi-step workflow against a single shared temporary SQLite WAL ledger
        app1 = App()
        app1.bind(type("Ctx", (), {"dispatch_tool": staticmethod(tracked_write)})())
        print(f"WAL Ledger: {app1.journal.db_path}")

        step1_args = {"path": str(workdir / "step1_config.txt"), "content": "env=prod\n"}
        mw.tool_execution_middleware(
            tool_name="write_file",
            args=step1_args,
            next_call=lambda a: tracked_write("write_file", a),
        )

        # Step 2: crash between intent and tool
        step2_args = {"path": str(workdir / "step2_schema.txt"), "content": "CREATE TABLE t(id INT);\n"}
        step2_op = op_id("write_file", step2_args)
        step2_att = uuid.uuid4().hex
        app1.journal.record_intent(
            step2_att,
            step2_op,
            "write_file",
            step2_args,
            session_id="chaos-demo",
            turn_id="turn-2",
            pre_fp=target_fingerprint("write_file", step2_args),
            idem_key=step2_op,
        )

        # Step 3: crash after tool execution, before post_fp / commit
        step3_args = {"path": str(workdir / "step3_bundle.txt"), "content": "bundle_v2=ready\n"}
        step3_op = op_id("write_file", step3_args)
        step3_att = uuid.uuid4().hex
        app1.journal.record_intent(
            step3_att,
            step3_op,
            "write_file",
            step3_args,
            session_id="chaos-demo",
            turn_id="turn-3",
            pre_fp=target_fingerprint("write_file", step3_args),
            idem_key=step3_op,
        )
        tracked_write("write_file", step3_args)

        pre_crash_bytes = app1.journal.db_bytes()
        pre_crash_inflight = len(app1.journal.in_flight())
        print(f"Process 1 crashed: in_flight={pre_crash_inflight}, wal_db_bytes={pre_crash_bytes}")
        app1.close()
        app1 = None

        # Process 2 boots and recovers
        app2 = App()
        app2.bind(type("Ctx", (), {"dispatch_tool": staticmethod(tracked_write)})())
        rec_msg = app2.recover("")
        print("\nRecovery Output:")
        print(rec_msg)

        # Run full deterministic chaos boundary suite
        print("\nRunning deterministic crash-boundary fault-injection suite...")
        chaos_mod = importlib.import_module(f"{phx.__name__}.chaos")
        chaos_report = chaos_mod.run_chaos_suite(seed=42, ops_per_boundary=3, workdir=workdir / "suite")
        print(chaos_mod.format_chaos_report(chaos_report))

        timeline = app2.journal.timeline(limit=10)
        stats_snap = {
            **app2.journal.stats(),
            "guard_enabled": bool(app2.guard_enabled),
            "db_bytes": app2.journal.db_bytes(),
        }
        print("\nLive Recovery Telemetry:")
        print("  stats:", json.dumps(stats_snap))
        print(f"  timeline entries: {len(timeline)}")
        for entry in timeline:
            print(
                f"    - op={entry['op_id']} tool={entry['tool']} status={entry['status']} "
                f"duration_ms={entry['duration_ms']}"
            )

        ok = (
            pre_crash_inflight == 2
            and len(app2.journal.in_flight()) == 0
            and app2.journal.get(step2_att)[4] == "resumed"
            and app2.journal.get(step3_att)[4] == "recovered_landed"
            and exec_counts.get(step2_op, 0) == 1
            and exec_counts.get(step3_op, 0) == 1
            and chaos_report.get("passed") is True
            and chaos_report.get("duplicate_executions") == 0
        )
        print("\nPHOENIX CHAOS DEMO:", "PASS" if ok else "FAIL")
        if not ok:
            raise SystemExit(1)
    finally:
        for a in (app1, app2):
            if a is not None:
                try:
                    a.close()
                except Exception:
                    pass
        if prev_data_dir is None:
            os.environ.pop("PHOENIX_DATA_DIR", None)
        else:
            os.environ["PHOENIX_DATA_DIR"] = prev_data_dir
        if prev_db_path is None:
            os.environ.pop("PHOENIX_DB_PATH", None)
        else:
            os.environ["PHOENIX_DB_PATH"] = prev_db_path
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> None:
    if "--chaos" in sys.argv:
        run_chaos_demo()
        return

    html_arg = None
    if "--html" in sys.argv:
        idx = sys.argv.index("--html")
        if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--"):
            html_arg = sys.argv[idx + 1]
        else:
            html_arg = "phoenix-report.html"

    workdir = Path(tempfile.mkdtemp(prefix="phoenix-demo-", dir=tempfile.gettempdir()))
    prev_data_dir = os.environ.get("PHOENIX_DATA_DIR")
    prev_db_path = os.environ.get("PHOENIX_DB_PATH")
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
        # ACT 1: Pre-commit crash in developer workflow -> /recover replays once
        # =====================================================================
        print("=" * 60)
        print("ACT 1: Pre-commit crash in developer workflow -> /recover replays once")
        print("=" * 60)
        print("Realistic developer scenario:")
        print("  - Developer agent edits config/auth (a.txt commits via middleware).")
        print("  - Agent journals intent for b.txt with pre-state fingerprint.")
        print("  - Process 1 killed (SIGKILL / timeout) BEFORE writing b.txt to disk.")
        print("  - Fresh agent resurrects: /recover replays b.txt once.")

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
        print("\nPROCESS 1 killed before writing b.txt. Ledger at:", app.journal.db_path)

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
        print("Realistic developer scenario:")
        print("  - Developer agent writes c.txt ('gamma'). File lands on disk.")
        print("  - Process dies BEFORE record_outcome (ambiguous fuzzy write).")
        print("  - Fresh agent boots: Turn-1 Autonomous Crash Alert detects interrupted op.")
        print("  - Phoenix inspects target fingerprint on disk -> recognizes mutation landed.")
        print("  - /recover marks c.txt as recovered_landed with 0 redundant writes!")

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
        # ACT 3: Developer Real-World Wind Tunnel (HERMES_DEV_TRACE) + ddmin
        # =====================================================================
        print("\n" + "=" * 60)
        print("ACT 3: Developer Real-World Wind Tunnel (HERMES_DEV_TRACE) + ddmin")
        print("=" * 60)
        print("Realistic 8-step Hermes developer/cron workflow trace:")
        print("  1. read_file('src/config.py')                    [read]")
        print("  2. write_file('src/auth.py')                     [mutate]")
        print("  3. patch('src/routes.py')                        [mutate]")
        print("  4. write_file('migrations/001_schema.sql')       [mutate]")
        print("  5. terminal('pytest')                            [read]")
        print("  6. terminal('git commit -m \"feat: auth\"')       [mutate]")
        print("  7. write_file('dist/bundle.js')                  [mutate - POST-COMMIT TIMEOUT FAULT]")
        print("  8. terminal('pytest --cov')                      [read]")
        print("\nRunning 6-check fault-injection suite (timeout_after_commit, rate_limit_429, malformed_payload) with Zeller ddmin...")

        wt_report = phx.windtunnel.run_windtunnel_suite(runs=5, journal=app3.journal)
        print(phx.windtunnel.format_windtunnel_report(wt_report))

        assert wt_report.get("passed") is True, f"Wind tunnel suite failed: {wt_report}"
        print("Act 3 PASS: Wind tunnel suite passed (5/5 RED unguarded -> ddmin shrunk to 1 step -> 0/5 RED guarded).")

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
        print("PROOF - Clean Crash Resurrection Verified:")
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
        if prev_data_dir is None:
            os.environ.pop("PHOENIX_DATA_DIR", None)
        else:
            os.environ["PHOENIX_DATA_DIR"] = prev_data_dir
        if prev_db_path is None:
            os.environ.pop("PHOENIX_DB_PATH", None)
        else:
            os.environ["PHOENIX_DB_PATH"] = prev_db_path
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
