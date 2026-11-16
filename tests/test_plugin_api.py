"""Unit tests for the Phoenix Dashboard Gateway API (dashboard/plugin_api.py)."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPO_PARENT = PLUGIN_ROOT.parent
if str(REPO_PARENT) not in sys.path:
    sys.path.insert(0, str(REPO_PARENT))
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from phoenix.core import App  # noqa: E402
from phoenix.dashboard import plugin_api  # noqa: E402
from phoenix.journal import Journal  # noqa: E402


class TestManifest(unittest.TestCase):
    def test_manifest_v2_and_api_field(self) -> None:
        manifest_path = PLUGIN_ROOT / "dashboard" / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "2.0.0")
        self.assertEqual(data["api"], "plugin_api.py")


class TestSingletonResolution(unittest.TestCase):
    def test_prefers_hermes_plugins_phoenix_core_over_phoenix_core(self) -> None:
        hermes_app = MagicMock(name="hermes_app")
        direct_app = MagicMock(name="direct_app")

        hermes_core = types.ModuleType("hermes_plugins.phoenix.core")
        hermes_core.get_app = lambda: hermes_app

        direct_core = types.ModuleType("phoenix.core")
        direct_core.get_app = lambda: direct_app

        with patch.dict(
            sys.modules,
            {
                "hermes_plugins.phoenix.core": hermes_core,
                "phoenix.core": direct_core,
            },
        ):
            self.assertIs(plugin_api._get_app(), hermes_app)

    def test_prefers_profile_scoped_hermes_plugins_phoenix_core(self) -> None:
        profile_app = MagicMock(name="profile_app")
        direct_app = MagicMock(name="direct_app")

        profile_core = types.ModuleType("hermes_plugins.phoenix__home_abcd1234.core")
        profile_core.get_app = lambda: profile_app

        direct_core = types.ModuleType("phoenix.core")
        direct_core.get_app = lambda: direct_app

        saved = sys.modules.pop("hermes_plugins.phoenix.core", None)
        try:
            with patch.dict(
                sys.modules,
                {
                    "hermes_plugins.phoenix__home_abcd1234.core": profile_core,
                    "phoenix.core": direct_core,
                },
            ):
                self.assertIs(plugin_api._get_app(), profile_app)
        finally:
            if saved is not None:
                sys.modules["hermes_plugins.phoenix.core"] = saved

    def test_falls_back_to_phoenix_core_when_hermes_module_absent(self) -> None:
        direct_app = MagicMock(name="direct_app")
        direct_core = types.ModuleType("phoenix.core")
        direct_core.get_app = lambda: direct_app

        saved = sys.modules.pop("hermes_plugins.phoenix.core", None)
        try:
            with patch.dict(sys.modules, {"phoenix.core": direct_core}):
                self.assertIs(plugin_api._get_app(), direct_app)
        finally:
            if saved is not None:
                sys.modules["hermes_plugins.phoenix.core"] = saved


class TestPluginApiEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)
        self.app = App()
        self.app.journal = Journal(self.data_dir)
        self.addCleanup(self.app.journal.close)

        # Seed two journal entries with distinct statuses
        self.app.journal.record_intent(
            "att-1", "op-1", "write_file", {"path": "/tmp/alpha.txt"}, session_id="s1", turn_id="t1"
        )
        self.app.journal.record_outcome("att-1", "op-1", "ok", result={"ok": True})

        self.app.journal.record_intent(
            "att-2", "op-2", "terminal", {"command": "pytest"}, session_id="s1", turn_id="t2"
        )
        self.app.journal.record_outcome("att-2", "op-2", "error", error="exit code 1")

    def tearDown(self) -> None:
        pass

    def test_get_status_is_read_only_and_returns_expected_fields(self) -> None:
        def _boom(*args, **kwargs):
            raise AssertionError("GET /status must NEVER call run_windtunnel_suite")

        with (
            patch.object(plugin_api, "_get_app", return_value=self.app),
            patch.object(plugin_api, "_get_windtunnel_runner", return_value=_boom),
        ):
            res = plugin_api.get_status()

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["guard_enabled"], self.app.guard_enabled)
        self.assertEqual(res["committed"], 1)
        self.assertEqual(res["errors"], 1)
        self.assertEqual(res["deduped"], 0)
        self.assertEqual(res["in_flight"], 0)
        self.assertEqual(res["recovered_landed"], 0)
        self.assertEqual(res["total"], 2)
        self.assertIsInstance(res["stats"], dict)
        self.assertGreater(res["db_bytes"], 0)
        self.assertEqual(res["windtunnel_verdict"], "UNKNOWN")
        self.assertIsNone(res["last_windtunnel_at"])

    def test_get_timeline_fallback_recent_with_filtering_and_limit(self) -> None:
        with patch.object(plugin_api, "_get_app", return_value=self.app):
            all_res = plugin_api.get_timeline(limit=10)
            self.assertEqual(all_res["status"], "ok")
            self.assertEqual(all_res["count"], 2)
            self.assertEqual(len(all_res["items"]), 2)

            err_res = plugin_api.get_timeline(limit=10, status="error")
            self.assertEqual(err_res["count"], 1)
            self.assertEqual(err_res["items"][0]["attempt_id"], "att-2")

            q_res = plugin_api.get_timeline(limit=10, q="ALPHA.TXT")
            self.assertEqual(q_res["count"], 1)
            self.assertEqual(q_res["items"][0]["attempt_id"], "att-1")

            lim_res = plugin_api.get_timeline(limit=1)
            self.assertEqual(lim_res["count"], 1)

    def test_get_timeline_uses_journal_timeline_when_available(self) -> None:
        mock_journal = MagicMock()
        mock_journal.timeline.return_value = [{"attempt_id": "att-x", "status": "ok"}]
        mock_app = MagicMock()
        mock_app._journal.return_value = mock_journal

        with patch.object(plugin_api, "_get_app", return_value=mock_app):
            res = plugin_api.get_timeline(limit=25, status="ok", q="write")

        mock_journal.timeline.assert_called_once_with(limit=25, status="ok", query="write")
        self.assertEqual(res, {"status": "ok", "items": [{"attempt_id": "att-x", "status": "ok"}], "count": 1})

    def test_get_timeline_clamps_limit_bounds(self) -> None:
        mock_journal = MagicMock()
        mock_journal.timeline.return_value = []
        mock_app = MagicMock()
        mock_app._journal.return_value = mock_journal

        with patch.object(plugin_api, "_get_app", return_value=mock_app):
            plugin_api.get_timeline(limit=99999)
            self.assertEqual(mock_journal.timeline.call_args.kwargs["limit"], 500)

            plugin_api.get_timeline(limit=-5)
            self.assertEqual(mock_journal.timeline.call_args.kwargs["limit"], 0)

            plugin_api.get_timeline(limit="not-a-number")  # type: ignore[arg-type]
            self.assertEqual(mock_journal.timeline.call_args.kwargs["limit"], 50)

    def test_post_windtunnel_runs_suite_and_persists_meta(self) -> None:
        fake_report = {
            "passed": True,
            "checks": [{"id": f"c{i}", "passed": True} for i in range(6)],
        }
        mock_runner = MagicMock(return_value=fake_report)

        with (
            patch.object(plugin_api, "_get_app", return_value=self.app),
            patch.object(plugin_api, "_get_windtunnel_runner", return_value=mock_runner),
        ):
            wt_res = plugin_api.post_windtunnel()
            status_res = plugin_api.get_status()

        mock_runner.assert_called_once_with(runs=3, journal=self.app.journal)
        self.assertEqual(wt_res["status"], "ok")
        self.assertEqual(wt_res["verdict"], "6/6 PASS")
        self.assertEqual(wt_res["report"], fake_report)

        self.assertEqual(status_res["windtunnel_verdict"], "6/6 PASS")
        self.assertIsNotNone(status_res["last_windtunnel_at"])
        self.assertEqual(self.app.journal.get_meta("windtunnel_verdict"), "6/6 PASS")
        self.assertTrue(bool(self.app.journal.get_meta("last_windtunnel_at")))


if __name__ == "__main__":
    unittest.main()
