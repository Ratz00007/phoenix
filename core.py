"""Shared runtime state and the crash-resume / recovery logic."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from typing import Any

from .journal import Journal

try:
    from .keys import has_target_changed, is_hermes_error_result, is_target_fully_committed
except ImportError:
    # Safe fallbacks if keys.py is concurrently being written
    def has_target_changed(fp) -> bool:
        return False

    def is_hermes_error_result(result) -> tuple[bool, str | None]:
        if isinstance(result, dict) and "error" in result:
            return True, str(result["error"])
        return False, None

    def is_target_fully_committed(tool_name: str, args: Any, pre_fp: dict | None = None) -> bool:
        return False

_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_.:-]{1,64}$")
_OP_ID_RE = re.compile(r"^[a-zA-Z0-9_]{1,32}$")


def _sanitize_tool(tool: Any) -> str:
    s = str(tool or "")
    if _TOOL_NAME_RE.match(s):
        return s
    clean = re.sub(r"[^a-zA-Z0-9_.:-]", "_", s)[:64]
    return clean if _TOOL_NAME_RE.match(clean) else "unknown_tool"


def _sanitize_op_id(oid: Any) -> str:
    s = str(oid or "")
    if _OP_ID_RE.match(s):
        return s
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", s)[:32]
    return clean if _OP_ID_RE.match(clean) else "unknown_op"



class App:
    """Holds the plugin ctx and journal, and implements /phoenix + /recover."""

    def __init__(self) -> None:
        self.ctx = None
        self.journal: Journal | None = None
        self._guard_enabled: bool = True

    def bind(self, ctx) -> None:
        self.ctx = ctx
        if self.journal is None:
            self.journal = Journal(self._data_dir(), db_path=self._db_path())

    def reset(self) -> None:
        """Re-open the journal (used by tests and re-binds)."""
        if self.journal is not None:
            self.journal.close()
        self.journal = Journal(self._data_dir(), db_path=self._db_path())

    def close(self) -> None:
        """Close the journal if open and set self.journal = None."""
        if self.journal is not None:
            try:
                self.journal.close()
            except Exception:
                pass
            self.journal = None

    @property
    def guard_enabled(self) -> bool:
        """Check whether the idempotency guard is enabled, synced with journal meta."""
        try:
            j = self._journal()
            if hasattr(j, "get_meta"):
                val = j.get_meta("guard_enabled")
                if val:
                    self._guard_enabled = str(val).strip() in ("1", "true", "True", "on", "yes")
        except Exception:
            pass
        return self._guard_enabled

    def set_guard(self, enabled: bool) -> str:
        """Set idempotency guard state and persist in journal metadata."""
        self._guard_enabled = bool(enabled)
        try:
            j = self._journal()
            if hasattr(j, "set_meta"):
                j.set_meta("guard_enabled", "1" if self._guard_enabled else "0")
        except Exception:
            pass
        return f"Phoenix idempotency guard: {'ON' if self._guard_enabled else 'OFF'}"

    def _db_path(self) -> str | None:
        return os.environ.get("PHOENIX_DB_PATH")

    def _data_dir(self) -> str:
        # Hermes: durable, profile-scoped storage that survives update/remove.
        try:
            from plugins.plugin_storage import plugin_data_dir
            return str(plugin_data_dir("phoenix"))
        except Exception:
            pass
        # Fallback (unit tests, no Hermes installed).
        d = os.environ.get("PHOENIX_DATA_DIR") or os.path.join(tempfile.gettempdir(), "phoenix")
        os.makedirs(d, exist_ok=True)
        return d

    # -- commands -----------------------------------------------------------

    def status(self, raw_args: str = "") -> str:
        raw = (raw_args or "").strip()
        parts = raw.split(None, 1)
        subcmd = parts[0].lower() if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""

        if not subcmd or subcmd == "status":
            verbose = "verbose" in rest.lower() or "-v" in rest.lower()
            return self.status_text(verbose=verbose)
        if subcmd == "explain":
            return self.explain(rest)
        if subcmd == "clear":
            j = self._journal()
            j.clear_in_flight(reason="cleared by operator")
            return "Phoenix: in-flight markers cleared (recorded as errors)."
        if subcmd in ("recover", "resume"):
            return self.recover(rest)
        if subcmd in ("windtunnel", "test"):
            from .windtunnel import format_windtunnel_report, run_windtunnel_suite
            return format_windtunnel_report(run_windtunnel_suite(journal=self._journal()))
        if subcmd == "report":
            return self.report(rest)
        if subcmd == "guard":
            r = rest.lower()
            if r in ("on", "true", "1", "enable"):
                return self.set_guard(True)
            if r in ("off", "false", "0", "disable"):
                return self.set_guard(False)
            return f"Phoenix idempotency guard: {'ON' if self.guard_enabled else 'OFF'}"
        return self.status_text()

    def status_text(self, session_id: str | None = None, verbose: bool = False) -> str:
        j = self._journal()
        s = j.stats()
        lines = [
            f"phoenix | {s['committed']} committed | {s.get('deduped', 0)} deduped | "
            f"{s['errors']} errors | {s['in_flight']} in-flight ({s['total']} recorded total) | "
            f"guard={'ON' if self.guard_enabled else 'OFF'}",
        ]
        inflight = j.in_flight()
        if inflight:
            lines.append("interrupted (in-flight) operations:")
            for attempt_id, op_id, tool, args_json, sid, turn_id, ts in inflight:
                args_short = args_json if len(args_json) <= 96 else args_json[:93] + "..."
                lines.append(f"  - {tool}  {op_id}  {args_short}")
            lines.append("run /recover (or /phoenix recover) to finish them exactly once.")
        else:
            lines.append("nothing in flight — every recorded operation has a known outcome.")
            lines.append("Run '/phoenix windtunnel' to launch the 5-fault stress test.")

        # Flight Recorder Timeline
        recent_ops = j.recent(limit=25 if verbose else 10)
        if session_id:
            recent_ops = [op for op in recent_ops if op.get("session_id") == session_id]

        if recent_ops or inflight:
            lines.append("")
            lines.append("--- Phoenix Flight Recorder Timeline ---")
            seen_ops = set()
            for op in recent_ops:
                op_id = op.get("op_id")
                seen_ops.add(op_id)
                status = op.get("status")
                tool = op.get("tool", "unknown")
                args = op.get("args") or {}

                arg_repr = ""
                if isinstance(args, dict):
                    path = args.get("path") or args.get("file_path") or args.get("target")
                    cmd = args.get("command")
                    url = args.get("url")
                    if path:
                        arg_repr = repr(str(path))
                    elif cmd:
                        c = str(cmd).strip().replace("\n", " ")
                        arg_repr = repr(c[:28] + "..." if len(c) > 28 else c)
                    elif url:
                        u = str(url).strip()
                        arg_repr = repr(u[:28] + "..." if len(u) > 28 else u)
                    elif args:
                        first_k = next(iter(args))
                        v = str(args[first_k]).replace("\n", " ")
                        arg_repr = repr(f"{first_k}={v[:18]}...") if len(v) > 18 else repr(f"{first_k}={v}")
                elif args:
                    a_str = str(args).strip().replace("\n", " ")
                    arg_repr = repr(a_str[:25] + "..." if len(a_str) > 25 else a_str)

                call_str = f"{tool}({arg_repr})"

                if status == "recovered_landed":
                    badge = "[LANDED]   "
                    detail = "pre/post verified"
                elif status in ("ok", "resumed"):
                    badge = "[COMMITTED]"
                    sha = None
                    if isinstance(op.get("result"), dict) and "sha256" in op["result"]:
                        sha = op["result"]["sha256"]
                    elif isinstance(args, dict) and ("content" in args or "patch" in args or "diff" in args):
                        c = str(args.get("content") or args.get("patch") or args.get("diff") or "")
                        sha = hashlib.sha256(c.encode("utf-8")).hexdigest()
                    if sha:
                        detail = f"sha256:{sha[:8]}..."
                    else:
                        detail = "ok"
                elif status in ("intent", "in_flight"):
                    badge = "[IN-FLIGHT]"
                    detail = "pending replay"
                elif status == "error":
                    badge = "[ERROR]    "
                    err = str(op.get("error") or "failed")
                    detail = f"err: {err[:24]}"
                elif status == "deduped":
                    badge = "[DEDUPED]  "
                    detail = "idempotent replay skipped"
                else:
                    badge = f"[{str(status).upper()[:8]:<8}] "
                    detail = str(status)

                lines.append(f"{badge} {call_str} -> {detail}")

            for inf in inflight:
                if inf[1] not in seen_ops:
                    tool = inf[2]
                    try:
                        args = json.loads(inf[3]) if inf[3] else {}
                    except Exception:
                        args = {}
                    arg_repr = ""
                    if isinstance(args, dict):
                        p = args.get("path") or args.get("file_path") or args.get("target") or args.get("command") or ""
                        arg_repr = repr(str(p)[:28]) if p else ""
                    call_str = f"{tool}({arg_repr})"
                    lines.append(f"[IN-FLIGHT] {call_str} -> pending replay")

        return "\n".join(lines)

    def explain(self, target: str) -> str:
        j = self._journal()
        if not target:
            return "usage: /phoenix explain <attempt_id|op_id>"
        row = j.find(target)
        if row is None:
            return f"phoenix: no operation matches {target!r}."
        attempt_id, op_id, tool, args_json, status, result_json, error, sid, tid, tcid, ts_i, ts_d = row
        return (
            f"op   {op_id}\n"
            f"tool {tool}\n"
            f"args {args_json}\n"
            f"status {status}"
            + (f"\nerror {error}" if error else "")
        )

    def recover(self, raw_args: str = "") -> str:
        j = self._journal()
        inflight = j.in_flight()
        if not inflight:
            return "Phoenix: nothing in flight to recover."

        wanted = set(raw_args.split()) if raw_args.strip() else None
        resumed = 0
        lines = []

        # Resolve helper functions dynamically to catch concurrent sibling module updates
        try:
            from .keys import has_target_changed as _htc
        except ImportError:
            _htc = has_target_changed
        try:
            from .keys import is_hermes_error_result as _iher
        except ImportError:
            _iher = is_hermes_error_result
        try:
            from .keys import is_target_fully_committed as _itfc
        except ImportError:
            _itfc = is_target_fully_committed

        for attempt_id, op_id, tool, args_json, session_id, turn_id, ts in inflight:
            if wanted and not (attempt_id in wanted or op_id in wanted):
                continue
            try:
                args = json.loads(args_json)
            except Exception:
                args = {}

            pre_fp = None
            if hasattr(j, "get_pre_fp"):
                try:
                    pre_fp = j.get_pre_fp(attempt_id)
                except Exception:
                    pre_fp = None

            if isinstance(pre_fp, str):
                try:
                    pre_fp = json.loads(pre_fp)
                except Exception:
                    pass

            target_committed = False
            try:
                target_committed = _itfc(tool, args, pre_fp)
            except Exception:
                target_committed = False

            target_changed = False
            if pre_fp is not None:
                try:
                    target_changed = _htc(pre_fp)
                except Exception:
                    target_changed = False

            if target_committed or (pre_fp is not None and target_changed):
                landed_path = (pre_fp.get("path") if isinstance(pre_fp, dict) else None) or (args.get("path") or args.get("file_path"))
                landed_result = {"recovered": "already_landed", "path": str(landed_path) if landed_path else None}
                try:
                    j.mark_resumed(attempt_id, result=landed_result, status="recovered_landed")
                except TypeError:
                    j.mark_resumed(attempt_id, result=landed_result)
                resumed += 1
                lines.append(f"recover {tool} {op_id}")
                lines.append("  -> already landed on disk (fingerprint changed); marked recovered without re-executing")
                continue

            lines.append(f"recover {tool} {op_id}")
            recov_attempt_id = f"{attempt_id}_recov"
            try:
                j.record_intent(
                    recov_attempt_id,
                    op_id,
                    tool,
                    args,
                    session_id=session_id,
                    turn_id=turn_id,
                    pre_fp=pre_fp,
                )
                result = self.ctx.dispatch_tool(tool, args) if self.ctx is not None else None
                is_err = False
                err_msg = None
                try:
                    is_err, err_msg = _iher(result)
                except Exception:
                    if isinstance(result, dict) and "error" in result:
                        is_err = True
                        err_msg = str(result["error"])

                if is_err:
                    j.record_outcome(recov_attempt_id, op_id, "error", result=result, error=err_msg)
                    j.record_outcome(attempt_id, op_id, "error", result=result, error=err_msg)
                    lines.append(f"  -> failed: {err_msg}")
                else:
                    j.record_outcome(recov_attempt_id, op_id, "ok", result=result)
                    j.mark_resumed(attempt_id, result=result)
                    resumed += 1
                    lines.append("  -> resumed exactly once")
            except Exception as exc:  # noqa: BLE001 — recovery must record, never crash
                j.record_outcome(recov_attempt_id, op_id, "error", error=repr(exc))
                j.record_outcome(attempt_id, op_id, "error", error=repr(exc))
                lines.append(f"  -> failed: {exc}")

        lines.append(f"resumed {resumed} operation(s).")
        return "\n".join(lines)

    # Backward compatibility alias
    resume = recover

    def report(self, raw_args: str = "") -> str:
        from .report import generate_html_report
        out_path = raw_args.strip() or None
        path = generate_html_report(self, out_path)
        return f"Phoenix HTML forensic report written to: {path}"

    def system_prompt_alert(self, session_info: Any = None, *args: Any, **kwargs: Any) -> str:
        inflight = self._journal().in_flight()
        if not inflight:
            return ""

        try:
            from .keys import has_target_changed as _htc
        except ImportError:
            _htc = has_target_changed
        try:
            from .keys import is_target_fully_committed as _itfc
        except ImportError:
            _itfc = is_target_fully_committed

        lines = [
            f"[PHOENIX WAL CRASH ALERT] {len(inflight)} interrupted tool operation(s) detected from a prior crash/timeout:"
        ]
        j = self._journal()
        for row in inflight:
            attempt_id, op_id, tool, args_json, session_id, turn_id, ts = row
            clean_tool = _sanitize_tool(tool)
            clean_op = _sanitize_op_id(op_id)

            try:
                args_dict = json.loads(args_json) if args_json else {}
            except Exception:
                args_dict = {}

            pre_fp = None
            if hasattr(j, "get_pre_fp"):
                try:
                    pre_fp = j.get_pre_fp(attempt_id)
                except Exception:
                    pre_fp = None
            if isinstance(pre_fp, str):
                try:
                    pre_fp = json.loads(pre_fp)
                except Exception:
                    pass

            target_committed = False
            try:
                target_committed = _itfc(tool, args_dict, pre_fp)
            except Exception:
                target_committed = False

            target_changed = False
            if pre_fp is not None:
                try:
                    target_changed = _htc(pre_fp)
                except Exception:
                    target_changed = False

            if target_committed:
                landed_path = (pre_fp.get("path") if isinstance(pre_fp, dict) else None) or (args_dict.get("path") or args_dict.get("file_path"))
                landed_result = {"recovered": "already_landed", "path": str(landed_path) if landed_path else None}
                try:
                    j.mark_resumed(attempt_id, result=landed_result, status="recovered_landed")
                except TypeError:
                    j.mark_resumed(attempt_id, result=landed_result)
                lines.append(f"  - [{clean_tool}] {clean_op}: target ALREADY mutated on disk -> marked recovered_landed")
            elif target_changed:
                landed_path = pre_fp.get("path") if isinstance(pre_fp, dict) else None
                landed_result = {"recovered": "already_landed", "path": landed_path}
                try:
                    j.mark_resumed(attempt_id, result=landed_result, status="recovered_landed")
                except TypeError:
                    j.mark_resumed(attempt_id, result=landed_result)
                lines.append(f"  - [{clean_tool}] {clean_op}: target ALREADY mutated on disk -> safe to mark recovered_landed")
            else:
                lines.append(f"  - [{clean_tool}] {clean_op}: target unchanged -> needs replay (human confirmation recommended; run /recover or phoenix_ledger(action='recover'))")

        lines.append(
            "Advise the user to run /recover or call phoenix_ledger(action='recover') with human confirmation to replay safely without duplicate side-effects."
        )
        return "\n".join(lines)

    def _journal(self) -> Journal:
        if self.journal is None:
            self.journal = Journal(self._data_dir(), db_path=self._db_path())
        return self.journal


_APP = App()


def get_app() -> App:
    return _APP
