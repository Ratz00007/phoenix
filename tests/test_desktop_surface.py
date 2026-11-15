"""Tests for Phoenix Desktop & Web Dashboard UI surfaces."""

from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP_PLUGIN = ROOT / "desktop" / "plugin.js"
DASHBOARD_BUNDLE = ROOT / "dashboard" / "dist" / "index.js"

FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("eval", re.compile(r"\beval\b")),
    ("new Function", re.compile(r"\bnew\s+Function\b")),
    ("dynamic import()", re.compile(r"\bimport\s*\(")),
    ("<script>", re.compile(r"<script\b", re.IGNORECASE)),
    ("data-slot", re.compile(r"data-slot")),
    ("data-tour", re.compile(r"data-tour")),
    ("data-sidebar", re.compile(r"data-sidebar")),
    ("data-testid", re.compile(r"data-testid")),
    ("MutationObserver", re.compile(r"\bMutationObserver\b")),
    ("webview", re.compile(r"\bwebview\b", re.IGNORECASE)),
    ("JSX opening tag", re.compile(r"<[A-Za-z][A-Za-z0-9._-]*[\s/>]")),
    ("JSX closing tag", re.compile(r"</[A-Za-z][A-Za-z0-9._-]*>")),
]


class TestDesktopSurface(unittest.TestCase):
    """Validate desktop/plugin.js and dashboard/dist/index.js syntax and lint rules."""

    def test_files_exist(self) -> None:
        self.assertTrue(DESKTOP_PLUGIN.is_file(), f"Missing {DESKTOP_PLUGIN}")
        self.assertTrue(DASHBOARD_BUNDLE.is_file(), f"Missing {DASHBOARD_BUNDLE}")

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

    def test_desktop_plugin_imports_and_surfaces(self) -> None:
        src = DESKTOP_PLUGIN.read_text(encoding="utf-8")
        allowed_modules = {"react", "react/jsx-runtime", "@hermes/plugin-sdk"}
        imports = re.findall(r"from\s+['\"]([^'\"]+)['\"]", src)
        self.assertTrue(imports, "Expected ESM imports in desktop/plugin.js")
        self.assertTrue(
            set(imports).issubset(allowed_modules),
            f"Unexpected imports: {set(imports) - allowed_modules}",
        )
        for surface in ("sidebarNav", "routes", "panes", "statusBar", "palette"):
            self.assertIn(surface, src, f"Missing surface registration: {surface}")
        self.assertIn("id: 'phoenix'", src)
        self.assertIn("register(ctx)", src)
        self.assertIn("/windtunnel", src)
        self.assertIn("/timeline", src)
        self.assertIn("/status", src)

    def test_dashboard_bundle_endpoints(self) -> None:
        src = DASHBOARD_BUNDLE.read_text(encoding="utf-8")
        self.assertIn("window.React", src)
        self.assertIn("window.__HERMES_PLUGIN_SDK__", src)
        self.assertIn("/api/plugins/phoenix/status", src)
        self.assertIn("/api/plugins/phoenix/timeline", src)
        self.assertIn("/api/plugins/phoenix/windtunnel", src)


if __name__ == "__main__":
    unittest.main()
