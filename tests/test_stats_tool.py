"""Unit tests for Journal.timeline, Journal.db_bytes, phoenix_stats tool, and manifest alignment."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from _loader import load_plugin  # noqa: E402

phx = load_plugin(ROOT)
Journal = phx.journal.Journal
get_app = phx.core.get_app
tools = phx.tools


class TestJournalTimelineAndDbBytes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="phoenix-test-timeline-"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_timeline_joins_fingerprints_and_redacts_secrets(self):
        j = Journal(self.tmpdir)
        try:
            pre_fp = {"path": "/tmp/a.txt", "exists": False}
            post_fp = {"path": "/tmp/a.txt", "exists": True, "size": 5}
            j.record_intent(
                "att-1",
                "op-1",
                "write_file",
                {"path": "/tmp/a.txt", "api_key": "sk-supersecret123456"},
                session_id="sess-1",
                turn_id="turn-1",
                pre_fp=pre_fp,
                idem_key="idem-op-1",
            )
            j.record_outcome(
                "att-1",
                "op-1",
                "ok",
                result={"ok": True, "token": "ghp_secretToken999999"},
                post_fp=post_fp,
            )

            j.record_intent(
                "att-2",
                "op-2",
                "terminal",
                {"cmd": "echo hi"},
                session_id="sess-1",
                turn_id="turn-2",
            )
            j.record_outcome("att-2", "op-2", "error", error="Bearer mySecretBearerToken123")

            rows = j.timeline(limit=10)
            self.assertEqual(len(rows), 2)

            # Newest first
            r_err = rows[0]
            self.assertEqual(r_err["attempt_id"], "att-2")
            self.assertEqual(r_err["status"], "error")
            self.assertNotIn("mySecretBearerToken123", r_err["error"])
            self.assertIn("[REDACTED]", r_err["error"])

            r_ok = rows[1]
            expected_keys = {
                "attempt_id",
                "op_id",
                "tool",
                "status",
                "session_id",
                "turn_id",
                "ts_intent",
                "ts_done",
                "duration_ms",
                "pre_fp",
                "post_fp",
                "idem_key",
                "args",
                "result",
                "error",
            }
            self.assertEqual(set(r_ok.keys()), expected_keys)
            self.assertEqual(r_ok["pre_fp"], pre_fp)
            self.assertEqual(r_ok["post_fp"], post_fp)
            self.assertEqual(r_ok["idem_key"], "idem-op-1")
            self.assertIsNotNone(r_ok["duration_ms"])
            self.assertGreaterEqual(r_ok["duration_ms"], 0.0)
            self.assertEqual(r_ok["args"]["api_key"], "[REDACTED]")
            self.assertEqual(r_ok["result"]["token"], "[REDACTED]")

            # Status filter
            ok_only = j.timeline(limit=10, status="ok")
            self.assertEqual(len(ok_only), 1)
            self.assertEqual(ok_only[0]["attempt_id"], "att-1")

            # Query filter
            term_only = j.timeline(limit=10, query="terminal")
            self.assertEqual(len(term_only), 1)
            self.assertEqual(term_only[0]["attempt_id"], "att-2")

            # Limit=0
            self.assertEqual(j.timeline(limit=0), [])
        finally:
            j.close()

    def test_db_bytes_and_permissions(self):
        mem = Journal(self.tmpdir, db_path=":memory:")
        try:
            self.assertEqual(mem.db_bytes(), 0)
        finally:
            mem.close()

        disk = Journal(self.tmpdir)
        try:
            disk.record_intent("att-bytes", "op-bytes", "write_file", {"path": "x"})
            self.assertGreater(disk.db_bytes(), 0)
            if os.name != "nt":
                mode = stat.S_IMODE(Path(disk.db_path).stat().st_mode)
                self.assertEqual(mode, 0o600)
        finally:
            disk.close()


class TestPhoenixStatsTool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="phoenix-test-stats-"))
        self.prev_data_dir = os.environ.get("PHOENIX_DATA_DIR")
        self.prev_db_path = os.environ.get("PHOENIX_DB_PATH")
        os.environ["PHOENIX_DATA_DIR"] = str(self.tmpdir)
        os.environ.pop("PHOENIX_DB_PATH", None)
        self.app = get_app()
        self.app.reset()

    def tearDown(self):
        self.app.close()
        if self.prev_data_dir is None:
            os.environ.pop("PHOENIX_DATA_DIR", None)
        else:
            os.environ["PHOENIX_DATA_DIR"] = self.prev_data_dir
        if self.prev_db_path is None:
            os.environ.pop("PHOENIX_DB_PATH", None)
        else:
            os.environ["PHOENIX_DB_PATH"] = self.prev_db_path
        self.app.reset()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_phoenix_stats_returns_expected_fields(self):
        j = self.app._journal()
        j.record_intent("a1", "k1", "write_file", {"path": "a.txt"})
        j.record_outcome("a1", "k1", "ok", result={"ok": True})
        j.record_intent("a2", "k2", "write_file", {"path": "b.txt"})
        j.set_meta("windtunnel_verdict", "6/6 PASS")
        self.app.set_guard(True)

        raw = tools.phoenix_stats()
        data = json.loads(raw)

        for key in (
            "total",
            "committed",
            "in_flight",
            "deduped",
            "recovered_landed",
            "errors",
            "guard_enabled",
            "db_bytes",
            "windtunnel_verdict",
        ):
            self.assertIn(key, data)

        self.assertEqual(data["total"], 2)
        self.assertEqual(data["committed"], 1)
        self.assertEqual(data["in_flight"], 1)
        self.assertEqual(data["deduped"], 0)
        self.assertEqual(data["recovered_landed"], 0)
        self.assertEqual(data["errors"], 0)
        self.assertTrue(data["guard_enabled"])
        self.assertGreater(data["db_bytes"], 0)
        self.assertEqual(data["windtunnel_verdict"], "6/6 PASS")

    def test_plugin_yaml_matches_register_tools_1_to_1(self):
        manifest = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        self.assertIn('version: "2.0.0"', manifest)
        declared_tools = re.findall(r"^\s*-\s*(phoenix_[a-z0-9_]+)\s*$", manifest, flags=re.MULTILINE)

        registered: dict[str, object] = {}

        class FakeCtx:
            def register_middleware(self, *_a, **_kw):
                pass

            def register_command(self, *_a, **_kw):
                pass

            def register_cli_command(self, *_a, **_kw):
                pass

            def register_system_prompt_section(self, *_a, **_kw):
                pass

            def on_unload(self, *_a, **_kw):
                pass

            def register_tool(self, name, *a, **kw):
                registered[name] = (a, kw)

        phx.register(FakeCtx())
        self.assertEqual(set(declared_tools), set(registered.keys()))
        self.assertEqual(set(declared_tools), {"phoenix_ledger", "phoenix_windtunnel", "phoenix_stats"})

    def test_middleware_bypasses_phoenix_stats_without_journaling(self):
        mw = phx.middleware.make_middleware(lambda: self.app)
        called = []

        def next_call(args):
            called.append(args)
            return tools.phoenix_stats()

        raw = mw(tool_name="phoenix_stats", args={}, session_id="s1", next_call=next_call)
        data = json.loads(raw)
        self.assertEqual(data["total"], 0)
        self.assertEqual(self.app._journal().stats()["total"], 0)
        self.assertEqual(len(called), 1)

    def test_middleware_records_pre_and_post_fp_in_timeline(self):
        mw = phx.middleware.make_middleware(lambda: self.app)
        target = self.tmpdir / "captured.txt"

        def write_next(args):
            Path(args["path"]).write_text(args["content"], encoding="utf-8")
            return {"ok": True, "path": args["path"]}

        mw(
            tool_name="write_file",
            args={"path": str(target), "content": "phoenix-v2"},
            session_id="sess-fp",
            next_call=write_next,
        )

        rows = self.app._journal().timeline(limit=5)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status"], "ok")
        self.assertIsNotNone(row["pre_fp"])
        self.assertFalse(row["pre_fp"]["exists"])
        self.assertIsNotNone(row["post_fp"])
        self.assertTrue(row["post_fp"]["exists"])
        self.assertEqual(row["post_fp"]["size"], len("phoenix-v2"))
        self.assertIsNotNone(row["post_fp"]["sha256"])

    def test_mark_resumed_inserts_missing_fingerprint_row(self):
        j = self.app._journal()
        j.record_intent("att-miss", "op-miss", "write_file", {"path": str(self.tmpdir / "m.txt")})
        with j._lock:
            c = j._connect()
            c.execute("DELETE FROM fingerprints WHERE attempt_id=?", ("att-miss",))
            j._commit(c)

        post_fp = {"path": str(self.tmpdir / "m.txt"), "exists": True, "sha256": "abc"}
        j.mark_resumed("att-miss", result={"recovered": "already_landed"}, status="recovered_landed", post_fp=post_fp)
        rows = j.timeline(limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "recovered_landed")
        self.assertEqual(rows[0]["post_fp"], post_fp)

    def test_system_prompt_alert_persists_post_fp_on_recovered_landed(self):
        target = self.tmpdir / "landed.txt"
        pre_fp = phx.keys.target_fingerprint("write_file", {"path": str(target), "content": "ok"})
        j = self.app._journal()
        j.record_intent(
            "att-alert",
            "op-alert",
            "write_file",
            {"path": str(target), "content": "ok"},
            pre_fp=pre_fp,
            idem_key="op-alert",
        )
        target.write_text("ok", encoding="utf-8")

        alert = self.app.system_prompt_alert()
        self.assertIn("recovered_landed", alert)

        rows = j.timeline(limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "recovered_landed")
        self.assertIsNotNone(rows[0]["post_fp"])
        self.assertTrue(rows[0]["post_fp"]["exists"])
        self.assertIsNotNone(rows[0]["post_fp"]["sha256"])

    def test_middleware_deduped_attempts_record_idem_key_and_fingerprints(self):
        self.app.set_guard(True)
        mw = phx.middleware.make_middleware(lambda: self.app)
        target = self.tmpdir / "dedup.txt"
        calls = []

        def write_next(args):
            calls.append(args)
            Path(args["path"]).write_text(args["content"], encoding="utf-8")
            return {"ok": True, "path": args["path"]}

        res1 = mw(
            tool_name="write_file",
            args={"path": str(target), "content": "once"},
            session_id="sess-dedup",
            next_call=write_next,
        )
        res2 = mw(
            tool_name="write_file",
            args={"path": str(target), "content": "once"},
            session_id="sess-dedup",
            next_call=write_next,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(res1, res2)

        # Also test timeout-after-commit dedup branch (prior attempt in 'intent' but disk mutated)
        target2 = self.tmpdir / "timeout-landed.txt"
        args2 = {"path": str(target2), "content": "landed-before-crash"}
        key2 = phx.keys.op_id("write_file", args2)
        pre_fp2 = phx.keys.target_fingerprint("write_file", args2)
        self.app._journal().record_intent(
            "att-timeout",
            key2,
            "write_file",
            args2,
            session_id="sess-dedup",
            pre_fp=pre_fp2,
            idem_key=key2,
        )
        target2.write_text("landed-before-crash", encoding="utf-8")
        res3 = mw(
            tool_name="write_file",
            args=args2,
            session_id="sess-dedup",
            next_call=write_next,
        )
        self.assertIsInstance(res3, dict)
        self.assertTrue(res3["deduped"])

        deduped_rows = self.app._journal().timeline(limit=10, status="deduped")
        self.assertEqual(len(deduped_rows), 2)
        for row in deduped_rows:
            self.assertIsNotNone(row["idem_key"])
            self.assertIsNotNone(row["pre_fp"])
            self.assertIsNotNone(row["post_fp"])
            self.assertEqual(row["pre_fp"], row["post_fp"])


if __name__ == "__main__":
    unittest.main()
