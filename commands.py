"""Slash-command handlers and CLI integration for Phoenix.

Hermes calls a command handler as ``fn(raw_args: str) -> str | None``.
CLI subcommands are routed through ``setup_cli`` and ``cli_handler``.
"""

from __future__ import annotations

from .core import get_app


def phoenix_cmd(raw_args: str = "") -> str:
    return get_app().status(raw_args)


def recover_cmd(raw_args: str = "") -> str:
    return get_app().recover(raw_args)


resume_cmd = recover_cmd


def setup_cli(parser) -> None:
    """Configure argparse arguments for `hermes phoenix` CLI subcommand."""
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        help="Action to perform: status (default), recover, windtunnel, guard, report, explain, clear",
    )
    parser.add_argument(
        "params",
        nargs="*",
        help="Parameters for the action (e.g. op_id for explain/recover, on/off for guard)",
    )


def cli_handler(args) -> int:
    """Execute CLI subcommand `hermes phoenix ...`."""
    if isinstance(args, dict):
        action = args.get("action", "status") or "status"
        params = args.get("params", [])
    else:
        action = getattr(args, "action", "status") or "status"
        params = getattr(args, "params", [])

    if isinstance(params, (list, tuple)):
        params_str = " ".join(str(p) for p in params)
    else:
        params_str = str(params or "")

    raw_args = f"{action} {params_str}".strip() if params_str else action

    app = get_app()
    out = app.status(raw_args)
    if out:
        print(out)
    return 0
