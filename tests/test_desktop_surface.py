"""Tests for Phoenix Desktop & Web Dashboard UI surfaces."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP_PLUGIN = ROOT / "desktop" / "plugin.js"
DASHBOARD_BUNDLE = ROOT / "dashboard" / "dist" / "index.js"
DASHBOARD_MANIFEST = ROOT / "dashboard" / "manifest.json"

FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("eval", re.compile(r"(?<![\w$.])eval\(")),
    ("new Function", re.compile(r"\bnew\s+Function\b")),
    ("dynamic import()", re.compile(r"\bimport\s*\(")),
    ("<script>", re.compile(r"<script\b", re.IGNORECASE)),
    ("data-slot", re.compile(r"data-slot")),
    ("data-tour", re.compile(r"data-tour")),
    ("data-sidebar", re.compile(r"data-sidebar")),
    ("data-testid", re.compile(r"data-testid")),
    ("MutationObserver", re.compile(r"\bMutationObserver\b")),
    ("webview", re.compile(r"\bwebview\b", re.IGNORECASE)),
    ("window.hermesDesktop", re.compile(r"\bhermesDesktop\b")),
    ("JSX opening tag", re.compile(r"<[A-Za-z][A-Za-z0-9._-]*[\s/>]")),
    ("JSX closing tag", re.compile(r"</[A-Za-z][A-Za-z0-9._-]*>")),
]


class TestDesktopSurface(unittest.TestCase):
    """Validate desktop/plugin.js and dashboard/dist/index.js syntax, SDK contracts, and lint rules."""

    def test_files_exist(self) -> None:
        self.assertTrue(DESKTOP_PLUGIN.is_file(), f"Missing {DESKTOP_PLUGIN}")
        self.assertTrue(DASHBOARD_BUNDLE.is_file(), f"Missing {DASHBOARD_BUNDLE}")
        self.assertTrue(DASHBOARD_MANIFEST.is_file(), f"Missing {DASHBOARD_MANIFEST}")

    def test_node_syntax_check(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "node executable is required for syntax validation")
        for target in (DESKTOP_PLUGIN, DASHBOARD_BUNDLE):
            proc = subprocess.run(
                [node, "--check", str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"node --check failed for {target}: {proc.stderr or proc.stdout}",
            )

    def test_no_forbidden_patterns(self) -> None:
        for target in (DESKTOP_PLUGIN, DASHBOARD_BUNDLE):
            src = target.read_text(encoding="utf-8")
            for label, pattern in FORBIDDEN_PATTERNS:
                match = pattern.search(src)
                self.assertIsNone(
                    match,
                    f"Forbidden pattern '{label}' found in {target}: {match.group(0) if match else ''}",
                )

    def test_desktop_plugin_sdk_contract(self) -> None:
        src = DESKTOP_PLUGIN.read_text(encoding="utf-8")
        allowed_modules = {"react", "react/jsx-runtime", "@hermes/plugin-sdk"}
        imports = re.findall(r"from\s+['\"]([^'\"]+)['\"]", src)
        self.assertTrue(imports, "Expected ESM imports in desktop/plugin.js")
        self.assertTrue(
            set(imports).issubset(allowed_modules),
            f"Unexpected imports: {set(imports) - allowed_modules}",
        )
        for area_const in (
            "ROUTES_AREA",
            "SIDEBAR_NAV_AREA",
            "PANES_AREA",
            "STATUSBAR_AREAS",
            "PALETTE_AREA",
        ):
            self.assertIn(area_const, src, f"Missing SDK area constant: {area_const}")
        self.assertIn("registerMany", src)
        self.assertIn("host.navigate", src)
        self.assertIn("id: 'phoenix'", src)
        self.assertIn("register(ctx)", src)
        self.assertIn("/windtunnel", src)
        self.assertIn("/timeline", src)
        self.assertIn("/status", src)
        self.assertNotIn("TabsContent", src)
        self.assertNotIn("ctx.navigate", src)

    def test_dashboard_bundle_sdk_contract(self) -> None:
        src = DASHBOARD_BUNDLE.read_text(encoding="utf-8")
        self.assertIn("window.__HERMES_PLUGIN_SDK__", src)
        self.assertIn("window.__HERMES_PLUGINS__", src)
        self.assertIn("SDK.fetchJSON", src)
        self.assertIn('REGISTRY.register("phoenix"', src)
        self.assertIn("/api/plugins/phoenix/status", src)
        self.assertIn("/api/plugins/phoenix/timeline", src)
        self.assertIn("/api/plugins/phoenix/windtunnel", src)
        self.assertNotIn("window.React", src)
        self.assertNotIn("registerPanel", src)

    def test_dashboard_manifest_schema(self) -> None:
        data = json.loads(DASHBOARD_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "phoenix")
        self.assertEqual(data["label"], "Phoenix")
        self.assertEqual(data["version"], "2.0.0")
        self.assertEqual(data["entry"], "dist/index.js")
        self.assertEqual(data["api"], "plugin_api.py")
        self.assertEqual(data["icon"], "Shield")
        self.assertEqual(data["tab"]["path"], "/phoenix")

    def test_desktop_plugin_uses_valid_theme_tokens(self) -> None:
        src = DESKTOP_PLUGIN.read_text(encoding="utf-8")
        dead_token_patterns = [
            r"--ui-surface\b",
            r"--ui-surface-elevated\b",
            r"--ui-surface-active\b",
            r"--ui-bg\b",
            r"--ui-border\b",
            r"--ui-text(?![\w-])",
            r"--ui-text-muted\b",
            r"--ui-font-mono\b",
            r"--ui-success\b",
            r"--ui-warning\b",
            r"--ui-danger\b",
        ]
        for pat in dead_token_patterns:
            self.assertIsNone(
                re.search(pat, src),
                f"Dead CSS token pattern {pat!r} found in desktop/plugin.js",
            )
        for token in (
            "--ui-text-primary",
            "--ui-text-tertiary",
            "--ui-stroke-secondary",
            "--font-mono",
            "--ui-accent",
            "--chrome-action-hover",
        ):
            self.assertIn(token, src, f"Expected real Hermes Desktop token {token} in desktop/plugin.js")

    def test_desktop_plugin_guard_defaults_to_false(self) -> None:
        src = DESKTOP_PLUGIN.read_text(encoding="utf-8")
        guard_lines = [line for line in src.splitlines() if "guard_enabled" in line and "guardOn" in line]
        self.assertEqual(len(guard_lines), 3, f"Expected 3 guardOn initializers in desktop/plugin.js, got {guard_lines}")
        for line in guard_lines:
            self.assertTrue(
                line.rstrip().endswith(": false;"),
                f"Expected guard_enabled fallback to default to false: {line}",
            )

    def test_dashboard_bundle_uses_valid_theme_tokens_and_guard_default(self) -> None:
        src = DASHBOARD_BUNDLE.read_text(encoding="utf-8")
        self.assertIsNone(
            re.search(r"--ui-", src),
            "Dead --ui-* CSS token found in dashboard/dist/index.js",
        )
        for token in (
            "--background-base",
            "--color-card",
            "--color-card-foreground",
            "--color-secondary",
            "--color-border",
            "--color-muted-foreground",
            "--color-primary",
            "--color-success",
            "--color-warning",
            "--color-destructive",
            "--theme-font-sans",
            "--theme-font-mono",
        ):
            self.assertIn(token, src, f"Expected real Hermes Web Dashboard token {token} in dashboard/dist/index.js")
        guard_lines = [line for line in src.splitlines() if "guard_enabled" in line and "guardOn" in line]
        self.assertEqual(len(guard_lines), 1)
        self.assertIn(": false);", guard_lines[0])


if __name__ == "__main__":
    unittest.main()
