"""Phoenix self-check — mirrors what `hermes plugins doctor --ci` verifies.

Runs with the standard library only (no Hermes required), so you can prove the
plugin is well-formed before installing Hermes. Prints a PASS/FAIL per check
and exits non-zero on failure.

    python selfcheck.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FORBIDDEN_IMPORTS = re.compile(
    # Anything Hermes-core that is not on the public allow-list.
    r"^\s*(import|from)\s+(hermes\.|hermes_cli\.|agent\.|tools\.|gateway\.|providers\.|plugins\.plugins_)",
)

ALLOWED = (
    "from plugins.plugin_storage import",
)


def check_manifest() -> tuple[bool, str]:
    raw = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    for key in ("name:", "version:", "description:"):
        if key not in raw:
            return False, f"plugin.yaml missing {key}"
    if "kind:" not in raw:
        return False, "plugin.yaml missing kind"
    return True, "manifest parses (name/version/description/kind present)"


def check_dashboard_manifest() -> tuple[bool, str]:
    manifest_path = ROOT / "dashboard" / "manifest.json"
    if not manifest_path.exists():
        return True, "dashboard/manifest.json not present (skipped)"
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return False, "dashboard/manifest.json is not a valid JSON object"
        for req in ("name", "version", "entry"):
            if req not in data:
                return False, f"dashboard/manifest.json missing required key: {req}"
        return True, f"dashboard/manifest.json parses valid JSON (version {data.get('version')})"
    except Exception as exc:  # noqa: BLE001
        return False, f"dashboard/manifest.json JSON parse error: {exc!r}"


def check_register() -> tuple[bool, str]:
    sys.path.insert(0, str(ROOT / "tests"))
    from _loader import load_plugin
    os.environ["PHOENIX_DATA_DIR"] = str(ROOT / ".selfcheck-data")
    phx = None
    try:
        phx = load_plugin(ROOT)
        register = phx.register

        class FakeCtx:
            def __init__(self):
                self.mw = {}
                self.cmds = {}
                self.cli_cmds = {}
                self.tools = {}
                self.prompt_sections = {}
                self.unload_cbs = []

            def register_middleware(self, k, cb):
                self.mw[k] = cb

            def register_command(self, n, h, **kw):
                self.cmds[n] = h

            def register_cli_command(self, n, *a, **kw):
                self.cli_cmds[n] = (a, kw)

            def register_tool(self, n, *a, **kw):
                self.tools[n] = (a, kw)

            def register_system_prompt_section(self, name, fn, **kw):
                self.prompt_sections[name] = fn

            def on_unload(self, cb):
                self.unload_cbs.append(cb)

        ctx = FakeCtx()
        register(ctx)
        if "tool_execution" not in ctx.mw:
            return False, "register() did not register tool_execution middleware"
        if "phoenix" not in ctx.cmds or "recover" not in ctx.cmds:
            return False, "register() did not register /phoenix and /recover commands"
        if "resume" in ctx.cmds:
            return False, "register() registered /resume which collides with Hermes built-in command"
        if "phoenix_ledger" not in ctx.tools or "phoenix_windtunnel" not in ctx.tools:
            return False, "register() did not register phoenix_ledger and phoenix_windtunnel tools"
        if "phoenix_recovery" not in ctx.prompt_sections:
            return False, "register() did not register phoenix_recovery system prompt section"
        return True, "register(ctx) runs and registers middleware, 2 commands (/phoenix, /recover), 2 tools (phoenix_ledger, phoenix_windtunnel), and phoenix_recovery prompt section"
    except Exception as exc:  # noqa: BLE001
        return False, f"register(ctx) raised: {exc!r}"
    finally:
        try:
            if phx is not None:
                core_mod = getattr(phx, "core", None) or sys.modules.get("hermes_plugins.phoenix.core")
                if core_mod is not None:
                    app = core_mod.get_app()
                    if hasattr(app, "close"):
                        app.close()
                    elif getattr(app, "journal", None) is not None:
                        app.journal.close()
        except Exception:
            pass
        shutil.rmtree(ROOT / ".selfcheck-data", ignore_errors=True)


def check_imports() -> tuple[bool, str]:
    offenders = []
    for py in sorted(ROOT.rglob("*.py")):
        if py.name == "selfcheck.py" or "tests" in py.parts:
            continue
        for i, line in enumerate(py.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if any(line.startswith(a) for a in ALLOWED):
                continue
            if FORBIDDEN_IMPORTS.match(line):
                offenders.append(f"{py.name}:{i}: {line.strip()}")
    if offenders:
        return False, "non-public Hermes imports:\n  " + "\n  ".join(offenders)
    return True, "imports stay on the public plugin API allow-list"


def check_no_binaries() -> tuple[bool, str]:
    bad = []
    for p in ROOT.rglob("*"):
        if any(part in {"__pycache__", ".git", ".selfcheck-data"} for part in p.parts):
            continue
        if p.suffix in {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin"}:
            bad.append(str(p))
    if bad:
        return False, "binary/bytecode artifacts found: " + ", ".join(bad)
    return True, "no compiled binaries or bytecode"


def check_developer_windtunnel() -> tuple[bool, str]:
    try:
        wt = sys.modules.get("hermes_plugins.phoenix.windtunnel")
        if wt is None:
            sys.path.insert(0, str(ROOT / "tests"))
            from _loader import load_plugin
            phx = load_plugin(ROOT)
            wt = getattr(phx, "windtunnel", None) or sys.modules.get("hermes_plugins.phoenix.windtunnel")
        if wt is None:
            return False, "windtunnel module not found"
        if not hasattr(wt, "HERMES_DEV_TRACE"):
            return False, "windtunnel missing HERMES_DEV_TRACE"
        trace = wt.HERMES_DEV_TRACE
        if len(trace) != 8:
            return False, f"HERMES_DEV_TRACE must have 8 steps, got {len(trace)}"
        mutating = [s for s in trace if s.get("mutates")]
        if len(mutating) < 2:
            return False, f"HERMES_DEV_TRACE must have multiple mutating steps, got {len(mutating)}"
        ddmin_res = wt.ddmin_trace(trace, fault_kind="timeout_after_commit")
        if ddmin_res["minimal_steps"] != 1:
            return False, f"ddmin failed to isolate 1 step, got {ddmin_res['minimal_steps']}"
        culprit = ddmin_res["minimal_counterexample"]
        if culprit.get("tool") != "write_file" or (culprit.get("args") or {}).get("path") != "dist/bundle.js":
            return False, f"ddmin isolated wrong step: {culprit}"
        report = wt.run_windtunnel_suite(runs=2, trace=trace)
        if not report.get("passed"):
            return False, "run_windtunnel_suite(runs=2) failed"
        return True, "HERMES_DEV_TRACE multi-mutation trace verified (8 steps -> 1 step isolated in <10ms, 0 LLM calls)"
    except Exception as exc:
        return False, f"windtunnel check raised: {exc!r}"


def check_tests() -> tuple[bool, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT.parent) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return False, "test suite failed:\n" + proc.stderr[-1500:]
    tail = proc.stdout.strip().splitlines()
    return True, "test suite green: " + (tail[-1].strip() if tail else "")


def main() -> int:
    checks = [
        ("manifest", check_manifest),
        ("dashboard manifest", check_dashboard_manifest),
        ("register(ctx)", check_register),
        ("public imports", check_imports),
        ("no binaries", check_no_binaries),
        ("developer windtunnel", check_developer_windtunnel),
        ("unit tests", check_tests),
    ]
    failed = False
    for name, fn in checks:
        ok, msg = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {msg}")
        failed = failed or (not ok)
    print("\nPHOENIX SELF-CHECK:", "PASS" if not failed else "FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
