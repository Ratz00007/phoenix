"""Phoenix — crash-proof, exactly-once execution journal for Hermes agents.

Kill your agent mid-write. Phoenix shows you what was in flight, and resumes
it exactly once. No LLM in the resume loop: the journal is the source of truth.

Hermes surfaces used (public API only):
  * ``tool_execution`` middleware — journals intent before every tool call and
    outcome after it (fail-open: a journaling error never breaks the agent).
  * ``/phoenix`` and ``/recover`` slash commands (never /resume to avoid Hermes collision).
  * Native Hermes agent tools: ``phoenix_ledger`` and ``phoenix_windtunnel``.
  * ``plugin_data_dir("phoenix")`` — durable SQLite (WAL) ledger.
"""

from __future__ import annotations


def register(ctx):
    """Hermes entrypoint. Called once when the plugin is loaded."""
    from . import commands, middleware, tools
    from .core import get_app

    app = get_app()
    app.bind(ctx)

    if hasattr(ctx, "on_unload"):
        try:
            ctx.on_unload(app.close)
        except Exception:
            pass

    # Behavior-changing middleware: journal every tool execution.
    ctx.register_middleware("tool_execution", middleware.tool_execution_middleware)

    # In-session slash commands (/phoenix and /recover; never /resume to avoid collision).
    ctx.register_command(
        "phoenix",
        commands.phoenix_cmd,
        description="Phoenix ledger, crash recovery & wind tunnel: /phoenix [status|recover|windtunnel|guard|report|explain <op>|clear]",
        args_hint="[status|recover|windtunnel|guard|report|explain <op>|clear]",
    )
    ctx.register_command(
        "recover",
        commands.recover_cmd,
        description="Recover every interrupted operation exactly once: /recover [op_id ...]",
        args_hint="[op_id ...]",
    )

    if hasattr(ctx, "register_system_prompt_section"):
        try:
            ctx.register_system_prompt_section(
                "phoenix_recovery",
                app.system_prompt_alert,
                position="after_memory",
            )
        except Exception:
            pass

    if hasattr(ctx, "register_cli_command"):
        try:
            ctx.register_cli_command(
                "phoenix",
                "Phoenix crash-proof ledger and deterministic wind tunnel",
                commands.setup_cli,
                commands.cli_handler,
            )
        except Exception:
            pass

    tools.register_tools(ctx)
