"""Deterministic crash-boundary fault-injection engine for Phoenix.

Injects simulated process crashes at every critical boundary of an agent's
write lifecycle against a real SQLite WAL ledger:
  1. ``before_intent``             — crash before ``journal.record_intent``
  2. ``between_intent_and_tool``   — crash after ``record_intent``, before tool runs
  3. ``after_tool_before_post_fp`` — crash after tool mutates disk, before ``post_fp``
  4. ``before_commit``             — crash after ``post_fp``, before ``record_outcome``

Across seeded operations, verifies:
  - Zero duplicate tool executions
  - Exact forward recovery (``resumed`` or ``recovered_landed``)
  - Zero in-flight rows remaining after recovery
  - Exact expected target state on disk
"""

from __future__ import annotations

import random
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from .core import App
from .journal import Journal
from .keys import op_id, target_fingerprint

CRASH_BOUNDARIES: tuple[str, ...] = (
    "before_intent",
    "between_intent_and_tool",
    "after_tool_before_post_fp",
    "before_commit",
)


class CrashInjectedError(RuntimeError):
    """Raised when a deterministic crash boundary is triggered."""

    def __init__(self, boundary: str, op_key: str) -> None:
        self.boundary = boundary
        self.op_key = op_key
        super().__init__(f"Injected crash at boundary={boundary!r} for op={op_key}")


def _make_seeded_op(rng: random.Random, workdir: Path, boundary: str, op_index: int) -> dict[str, Any]:
    """Generate a deterministic write_file operation for a given seed and index."""
    token = f"{rng.getrandbits(32):08x}"
    filename = f"chaos_{boundary}_{op_index}_{token}.txt"
    target_path = workdir / filename
    content = f"seed-payload:{boundary}:{op_index}:{token}\n"
    args = {"path": str(target_path), "content": content}
    return {
        "tool": "write_file",
        "args": args,
        "target_path": target_path,
        "expected_content": content,
        "op_id": op_id("write_file", args),
    }


def _new_isolated_app(data_dir: Path, dispatch_fn) -> App:
    """Create an App bound to an isolated on-disk SQLite WAL Journal."""
    app = App()
    app.journal = Journal(data_dir)
    app.bind(type("ChaosCtx", (), {"dispatch_tool": staticmethod(dispatch_fn)})())
    return app


def run_chaos_trial(
    boundary: str,
    seed: int = 42,
    op_index: int = 0,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Execute one deterministic crash-and-recover trial at ``boundary``."""
    if boundary not in CRASH_BOUNDARIES:
        raise ValueError(f"Unknown crash boundary: {boundary!r}. Expected one of {CRASH_BOUNDARIES}")

    t0 = time.perf_counter()
    owns_workdir = workdir is None
    base_dir = Path(tempfile.mkdtemp(prefix=f"phoenix-chaos-{boundary}-")) if owns_workdir else workdir
    trial_dir = base_dir / f"trial_{boundary}_{seed}_{op_index}"
    data_dir = trial_dir / "ledger"
    files_dir = trial_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random((seed * 1009) + (CRASH_BOUNDARIES.index(boundary) * 131) + op_index)
    spec = _make_seeded_op(rng, files_dir, boundary, op_index)
    key = spec["op_id"]
    args = spec["args"]
    target_path: Path = spec["target_path"]
    expected_content: str = spec["expected_content"]

    exec_counts: dict[str, int] = {key: 0}

    def tracked_write(_tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        exec_counts[key] = exec_counts.get(key, 0) + 1
        p = Path(tool_args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tool_args["content"], encoding="utf-8")
        return {"ok": True, "path": str(p), "bytes": len(tool_args["content"])}

    app1: App | None = None
    app2: App | None = None
    crashed = False
    attempt_id = uuid.uuid4().hex

    try:
        # Phase 1: Run Process 1 up to the injected crash boundary.
        app1 = _new_isolated_app(data_dir, tracked_write)
        pre_fp = target_fingerprint("write_file", args)

        try:
            if boundary == "before_intent":
                raise CrashInjectedError(boundary, key)

            app1.journal.record_intent(
                attempt_id,
                key,
                "write_file",
                args,
                session_id="chaos-session",
                turn_id=f"turn-{op_index}",
                pre_fp=pre_fp,
                idem_key=key,
            )

            if boundary == "between_intent_and_tool":
                raise CrashInjectedError(boundary, key)

            result = tracked_write("write_file", args)

            if boundary == "after_tool_before_post_fp":
                raise CrashInjectedError(boundary, key)

            post_fp = target_fingerprint("write_file", args)
            app1.journal.record_post_fp(attempt_id, post_fp)

            if boundary == "before_commit":
                raise CrashInjectedError(boundary, key)

            app1.journal.record_outcome(attempt_id, key, "ok", result=result, post_fp=post_fp)
        except CrashInjectedError:
            crashed = True
        finally:
            app1.close()
            app1 = None

        # Phase 2: Boot fresh Process 2 against the same WAL ledger and recover.
        app2 = _new_isolated_app(data_dir, tracked_write)
        recovery_msg = app2.recover("")

        if boundary == "before_intent":
            # Nothing was journaled before crash; re-dispatching the operation once
            # must execute cleanly exactly once.
            in_flight_before = len(app2.journal.in_flight())
            fresh_attempt = uuid.uuid4().hex
            fresh_pre_fp = target_fingerprint("write_file", args)
            app2.journal.record_intent(
                fresh_attempt,
                key,
                "write_file",
                args,
                session_id="chaos-session",
                turn_id=f"turn-{op_index}-retry",
                pre_fp=fresh_pre_fp,
                idem_key=key,
            )
            res = tracked_write("write_file", args)
            fresh_post_fp = target_fingerprint("write_file", args)
            app2.journal.record_outcome(fresh_attempt, key, "ok", result=res, post_fp=fresh_post_fp)
            row = app2.journal.get(fresh_attempt)
            final_status = row[4] if row else None
            expected_status = "ok"
            boundary_ok = in_flight_before == 0 and final_status == "ok"
        else:
            row = app2.journal.get(attempt_id)
            final_status = row[4] if row else None
            expected_status = (
                "resumed" if boundary == "between_intent_and_tool" else "recovered_landed"
            )
            boundary_ok = final_status == expected_status

        in_flight_after = len(app2.journal.in_flight())
        disk_ok = target_path.exists() and target_path.read_text(encoding="utf-8") == expected_content
        exec_count = exec_counts.get(key, 0)
        duplicate_executions = max(0, exec_count - 1)
        timeline_rows = app2.journal.timeline(limit=10)
        wal_bytes = app2.journal.db_bytes()

        passed = (
            crashed
            and boundary_ok
            and in_flight_after == 0
            and disk_ok
            and exec_count == 1
            and duplicate_executions == 0
            and len(timeline_rows) >= 1
            and wal_bytes > 0
        )

        return {
            "boundary": boundary,
            "seed": seed,
            "op_index": op_index,
            "op_id": key,
            "passed": passed,
            "crashed": crashed,
            "final_status": final_status,
            "expected_status": expected_status,
            "exec_count": exec_count,
            "duplicate_executions": duplicate_executions,
            "in_flight_after": in_flight_after,
            "disk_ok": disk_ok,
            "db_bytes": wal_bytes,
            "recovery_msg": recovery_msg,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    finally:
        for app in (app1, app2):
            if app is not None:
                try:
                    app.close()
                except Exception:
                    pass
        if owns_workdir:
            shutil.rmtree(base_dir, ignore_errors=True)


def run_chaos_suite(
    seed: int = 42,
    ops_per_boundary: int = 3,
    boundaries: tuple[str, ...] = CRASH_BOUNDARIES,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Run deterministic crash-boundary trials across all configured boundaries."""
    t0 = time.perf_counter()
    owns_workdir = workdir is None
    base_dir = Path(tempfile.mkdtemp(prefix="phoenix-chaos-suite-")) if owns_workdir else workdir

    trials: list[dict[str, Any]] = []
    try:
        for boundary in boundaries:
            for op_idx in range(max(1, int(ops_per_boundary))):
                trials.append(
                    run_chaos_trial(
                        boundary=boundary,
                        seed=seed,
                        op_index=op_idx,
                        workdir=base_dir,
                    )
                )
    finally:
        if owns_workdir:
            shutil.rmtree(base_dir, ignore_errors=True)

    passed_trials = sum(1 for t in trials if t["passed"])
    failed_trials = len(trials) - passed_trials
    total_duplicates = sum(int(t.get("duplicate_executions", 0)) for t in trials)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return {
        "passed": failed_trials == 0 and total_duplicates == 0 and len(trials) > 0,
        "seed": seed,
        "ops_per_boundary": ops_per_boundary,
        "boundaries_tested": list(boundaries),
        "total_trials": len(trials),
        "passed_trials": passed_trials,
        "failed_trials": failed_trials,
        "duplicate_executions": total_duplicates,
        "elapsed_ms": elapsed_ms,
        "trials": trials,
    }


def format_chaos_report(report: dict[str, Any]) -> str:
    """Format a chaos suite report as human-readable telemetry lines."""
    lines = [
        f"Phoenix Chaos Engine | seed={report.get('seed')} | "
        f"{report.get('passed_trials')}/{report.get('total_trials')} trials PASS | "
        f"duplicates={report.get('duplicate_executions')} | "
        f"elapsed={report.get('elapsed_ms')}ms",
    ]
    for t in report.get("trials", []):
        tag = "PASS" if t.get("passed") else "FAIL"
        lines.append(
            f"  [{tag}] boundary={t.get('boundary'):<26} op={t.get('op_id')} "
            f"status={t.get('final_status')} execs={t.get('exec_count')} "
            f"dups={t.get('duplicate_executions')} wal={t.get('db_bytes')}B "
            f"({t.get('elapsed_ms')}ms)"
        )
    return "\n".join(lines)
