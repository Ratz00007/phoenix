"""Unit tests for the Phoenix deterministic crash-boundary chaos engine."""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from _loader import load_plugin  # noqa: E402

phx = load_plugin(ROOT)
chaos = importlib.import_module(f"{phx.__name__}.chaos")


class TestChaosEngine(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="phoenix-test-chaos-"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_before_intent_boundary(self):
        res = chaos.run_chaos_trial("before_intent", seed=101, op_index=0, workdir=self.tmpdir)
        self.assertTrue(res["passed"], res)
        self.assertTrue(res["crashed"])
        self.assertEqual(res["final_status"], "ok")
        self.assertEqual(res["exec_count"], 1)
        self.assertEqual(res["duplicate_executions"], 0)
        self.assertEqual(res["in_flight_after"], 0)

    def test_between_intent_and_tool_boundary(self):
        res = chaos.run_chaos_trial("between_intent_and_tool", seed=101, op_index=1, workdir=self.tmpdir)
        self.assertTrue(res["passed"], res)
        self.assertTrue(res["crashed"])
        self.assertEqual(res["final_status"], "resumed")
        self.assertEqual(res["exec_count"], 1)
        self.assertEqual(res["duplicate_executions"], 0)
        self.assertEqual(res["in_flight_after"], 0)

    def test_after_tool_before_post_fp_boundary(self):
        res = chaos.run_chaos_trial("after_tool_before_post_fp", seed=101, op_index=2, workdir=self.tmpdir)
        self.assertTrue(res["passed"], res)
        self.assertTrue(res["crashed"])
        self.assertEqual(res["final_status"], "recovered_landed")
        self.assertEqual(res["exec_count"], 1)
        self.assertEqual(res["duplicate_executions"], 0)
        self.assertEqual(res["in_flight_after"], 0)

    def test_before_commit_boundary(self):
        res = chaos.run_chaos_trial("before_commit", seed=101, op_index=3, workdir=self.tmpdir)
        self.assertTrue(res["passed"], res)
        self.assertTrue(res["crashed"])
        self.assertEqual(res["final_status"], "recovered_landed")
        self.assertEqual(res["exec_count"], 1)
        self.assertEqual(res["duplicate_executions"], 0)
        self.assertEqual(res["in_flight_after"], 0)

    def test_invalid_boundary_raises(self):
        with self.assertRaises(ValueError):
            chaos.run_chaos_trial("nonexistent_boundary", seed=1, workdir=self.tmpdir)

    def test_chaos_suite_deterministic_and_zero_duplicates(self):
        r1 = chaos.run_chaos_suite(seed=42, ops_per_boundary=2, workdir=self.tmpdir / "run1")
        r2 = chaos.run_chaos_suite(seed=42, ops_per_boundary=2, workdir=self.tmpdir / "run2")

        self.assertTrue(r1["passed"], r1)
        self.assertTrue(r2["passed"], r2)
        self.assertEqual(r1["total_trials"], 8)
        self.assertEqual(r1["passed_trials"], 8)
        self.assertEqual(r1["failed_trials"], 0)
        self.assertEqual(r1["duplicate_executions"], 0)
        self.assertEqual(
            [(t["boundary"], t["final_status"], t["exec_count"], t["duplicate_executions"]) for t in r1["trials"]],
            [(t["boundary"], t["final_status"], t["exec_count"], t["duplicate_executions"]) for t in r2["trials"]],
        )
        formatted = chaos.format_chaos_report(r1)
        self.assertIn("8/8 trials PASS", formatted)
        self.assertIn("duplicates=0", formatted)


if __name__ == "__main__":
    unittest.main()
