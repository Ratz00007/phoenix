"""Deterministic idempotency-key derivation and target state fingerprinting.

The key is a pure function of (tool_name, args). It is stable across retries
of the same logical operation, so a crash + resume of the same call yields the
same key — the property that makes server-side dedupe (idempotency keys)
possible and makes the ledger joinable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable


def _canonical(value):
    """Normalize a value so equivalent structures hash identically.

    Dict keys are sorted; lists keep order (order can be semantically
    meaningful); sets are sorted by their JSON form.
    """
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True, default=str))
    return value


def canonical_json(args) -> str:
    return json.dumps(_canonical(args), sort_keys=True, separators=(",", ":"), default=str)


def op_id(tool_name: str, args, idempotency_key: str | None = None) -> str:
    """Return a short, stable idempotency key for a tool invocation."""
    ik = idempotency_key
    if not ik and isinstance(args, dict):
        ik = args.get("idempotency_key") or args.get("_idempotency_key")
        if not ik and isinstance(args.get("metadata"), dict):
            ik = args.get("metadata", {}).get("idempotency_key")
    if ik:
        payload = json.dumps(
            [tool_name, {"idempotency_key": str(ik)}],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    else:
        payload = json.dumps(
            [tool_name, _canonical(args)],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    return "phx_" + hashlib.sha256(payload).hexdigest()[:24]


def _stat_target(p: Path) -> tuple[bool, int | None, str | None]:
    """Helper to stat and hash a target file up to 10MB."""
    try:
        if p.is_file():
            size = p.stat().st_size
            sha256 = (
                hashlib.sha256(p.read_bytes()).hexdigest()
                if size <= 10 * 1024 * 1024
                else None
            )
            return True, size, sha256
        if p.exists():
            return True, None, None
        return False, None, None
    except OSError:
        return False, None, None


def _extract_target_paths(tool_name: str, args) -> list[str]:
    """Extract file target paths from tool arguments, diffs, or redirection commands."""
    if not isinstance(args, dict):
        return []
    paths: list[str] = []

    # 1. Direct path argument
    cand = (
        args.get("path")
        or args.get("file_path")
        or args.get("target")
        or args.get("destination")
    )
    if isinstance(cand, (str, Path)):
        s = str(cand).strip()
        if s and s != "/dev/null" and s not in paths:
            paths.append(s)

    # 2. Unified diff scanning
    if tool_name == "patch" or "patch" in args or "diff" in args:
        diff_str = args.get("patch") or args.get("diff") or args.get("content") or ""
        if isinstance(diff_str, str) and diff_str:
            for m in re.finditer(r"^\+\+\+\s+(?:b/)?([^\t\r\n]+)", diff_str, re.MULTILINE):
                target_p = m.group(1).strip()
                if target_p and target_p != "/dev/null" and target_p not in paths:
                    paths.append(target_p)

    # 3. Terminal/bash/shell redirection and tee
    if tool_name in ("terminal", "bash", "shell") and isinstance(args.get("command"), str):
        cmd = args["command"]
        for m in re.finditer(r">{1,2}\s*(?:'([^']+)'|\"([^\"]+)\"|([^\s'\";|&>]+))", cmd):
            target_p = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            if target_p and target_p != "/dev/null" and target_p not in paths:
                paths.append(target_p)
        for m in re.finditer(r"\btee\s+(?:-a\s+)?(?:'([^']+)'|\"([^\"]+)\"|([^\s'\";|&>]+))", cmd):
            target_p = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            if target_p and target_p != "/dev/null" and target_p not in paths:
                paths.append(target_p)

    return paths


def target_fingerprint(
    tool_name: str,
    args: Any,
    state_probe: Callable[[str, Any], Any] | None = None,
) -> dict | None:
    """Extract candidate file paths and probe custom state before execution."""
    has_probe = callable(state_probe)
    probe_val = state_probe(tool_name, args) if has_probe else None

    paths = _extract_target_paths(tool_name, args)
    targets: list[dict] = []
    if paths:
        base_dir = (
            (args.get("workdir") if isinstance(args, dict) else None)
            or os.environ.get("PHOENIX_WORKDIR")
            or os.getcwd()
        )
        for p_str in paths:
            if os.path.isabs(p_str):
                resolved = os.path.abspath(p_str)
            else:
                resolved = os.path.abspath(os.path.join(base_dir, p_str))
            p = Path(resolved)
            exists, size, sha256 = _stat_target(p)
            targets.append({
                "path": str(p),
                "exists": exists,
                "size": size,
                "sha256": sha256,
            })

    if not targets and not has_probe:
        return None

    res: dict[str, Any] = {}
    if targets:
        first = targets[0]
        res["path"] = first["path"]
        res["exists"] = first["exists"]
        res["size"] = first["size"]
        res["sha256"] = first["sha256"]
        res["targets"] = targets
    if has_probe:
        res["probe"] = probe_val

    return res


def has_target_changed(
    pre_fp: dict | None,
    state_probe: Callable[[str, Any], Any] | None = None,
) -> bool:
    """Compare post-execution state of target to its pre-execution fingerprint."""
    if not isinstance(pre_fp, dict):
        return False

    if "probe" in pre_fp and callable(state_probe):
        tool = pre_fp.get("tool", "")
        args = pre_fp.get("args", {})
        if state_probe(tool, args) != pre_fp["probe"]:
            return True

    if "targets" in pre_fp and isinstance(pre_fp["targets"], list):
        for t in pre_fp["targets"]:
            if isinstance(t, dict) and "path" in t:
                exists, size, sha256 = _stat_target(Path(t["path"]))
                if (exists, size, sha256) != (t.get("exists"), t.get("size"), t.get("sha256")):
                    return True
        return False

    if "path" in pre_fp:
        p = Path(pre_fp["path"])
        exists, size, sha256 = _stat_target(p)
        return (
            exists != pre_fp.get("exists")
            or size != pre_fp.get("size")
            or sha256 != pre_fp.get("sha256")
        )

    return False


def is_hermes_error_result(result) -> tuple[bool, str | None]:
    """Detect if a tool result represents an error returned by Hermes.

    Hermes ToolRegistry.dispatch() returns errors as a JSON string '{"error": "..."}'.
    """
    if isinstance(result, str) and result.strip().startswith("{"):
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and parsed.get("error") and parsed.get("ok") is not True:
                return True, str(parsed["error"])
        except (json.JSONDecodeError, ValueError):
            pass
    elif isinstance(result, dict) and result.get("error") and result.get("ok") is not True:
        return True, str(result["error"])
    return False, None


def is_target_fully_committed(
    tool_name: str,
    args: Any,
    pre_fp: dict | None = None,
) -> bool:
    """Check whether a tool's intended target state is fully committed on disk.

    If tool is 'write_file' and 'content' in args and 'path' in args (or file_path):
      check if file exists on disk and its content == args['content'] (or sha256 matches
      hashlib.sha256(args['content'].encode('utf-8')).hexdigest()). Return True if exactly matches,
      False otherwise.
    If tool is 'patch' or others, return False unless verified.
    """
    if not isinstance(args, dict):
        return False

    if tool_name == "write_file":
        cand = (
            args.get("path")
            or args.get("file_path")
            or (pre_fp.get("path") if isinstance(pre_fp, dict) else None)
        )
        if not cand or "content" not in args:
            return False

        content = args["content"]
        if not isinstance(content, (str, bytes)):
            return False

        base_dir = (
            args.get("workdir")
            or os.environ.get("PHOENIX_WORKDIR")
            or os.getcwd()
        )
        p_str = str(cand)
        if os.path.isabs(p_str):
            resolved = os.path.abspath(p_str)
        else:
            resolved = os.path.abspath(os.path.join(base_dir, p_str))

        p = Path(resolved)
        try:
            if not p.is_file():
                return False
            expected_bytes = content.encode("utf-8") if isinstance(content, str) else content
            expected_sha = hashlib.sha256(expected_bytes).hexdigest()
            file_bytes = p.read_bytes()
            actual_sha = hashlib.sha256(file_bytes).hexdigest()
            return actual_sha == expected_sha
        except OSError:
            return False

    if tool_name in ("patch", "apply_patch", "edit_file"):
        cand = (
            args.get("path")
            or args.get("file_path")
            or (pre_fp.get("path") if isinstance(pre_fp, dict) else None)
        )
        if not cand:
            extracted = _extract_target_paths(tool_name, args)
            cand = extracted[0] if extracted else None
        if not cand:
            return False

        base_dir = (
            args.get("workdir")
            or os.environ.get("PHOENIX_WORKDIR")
            or os.getcwd()
        )
        p_str = str(cand)
        if os.path.isabs(p_str):
            resolved = os.path.abspath(p_str)
        else:
            resolved = os.path.abspath(os.path.join(base_dir, p_str))

        p = Path(resolved)
        try:
            if not p.is_file():
                return False
            file_text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

        diff_str = (
            args.get("patch")
            or args.get("diff")
            or args.get("content")
            or ""
        )
        if not isinstance(diff_str, str) or not diff_str.strip():
            repl = args.get("Replacement") or args.get("replacement") or args.get("new_str") or args.get("new_string")
            if isinstance(repl, str) and repl.strip():
                return repl.strip() in file_text
            return False

        added_lines = [
            line[1:].strip()
            for line in diff_str.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        non_empty_added = [l for l in added_lines if l]
        if non_empty_added:
            return all(l in file_text for l in non_empty_added)

        repl = args.get("Replacement") or args.get("replacement") or args.get("new_str") or args.get("new_string")
        if isinstance(repl, str) and repl.strip():
            return repl.strip() in file_text

        return False

    return False

