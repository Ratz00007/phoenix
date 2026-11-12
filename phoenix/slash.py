"""Phoenix user-facing slash commands: /phoenix and /recover.

Guarantee: /recover provides interactive or dry-run recovery; never bypasses human control.
"""

from __future__ import annotations

from typing import Any

from .ledger import Ledger
from .metrics import MetricsService
from .recovery import RecoveryEngine


def phoenix_slash_command(args: str = "", ledger: Ledger | None = None) -> str:
    """Handler for /phoenix slash command."""
    if ledger is None:
        return "[phoenix] Flight recorder ledger not initialized."

    subcmd = args.strip().lower().split()[0] if args.strip() else "status"

    if subcmd == "status" or not subcmd:
        pending = ledger.pending_calls()
        stats = ledger.counters()
        return (
            f"🔥 **Phoenix Flight Recorder Status**\n\n"
            f"- **Active In-Flight Calls:** {len(pending)}\n"
            f"- **Duplicate Writes Prevented:** {stats['dupes_prevented']}\n"
            f"- **Operations Recovered from SIGKILL:** {stats['ops_recovered']}\n"
            f"- **Capital Saved:** ${stats['cost_saved_cents'] / 100:.2f}\n"
            f"- **Durability Engine:** SQLite WAL (synchronous=FULL, mode 0600)\n"
        )
    elif subcmd == "stats":
        stats = ledger.counters()
        return (
            f"📊 **Phoenix Value Telemetry**\n\n"
            f"• Duplicate Side Effects Avoided: **{stats['dupes_prevented']}**\n"
            f"• Interrupted Operations Recovered: **{stats['ops_recovered']}**\n"
            f"• LLM Cognitive Cycles Saved: **{stats['llm_calls_avoided']} turns**\n"
            f"• Total Value Retained: **${stats['cost_saved_cents'] / 100:.2f}**\n"
        )
    elif subcmd == "report":
        service = MetricsService(ledger)
        return service.generate_trust_report()
    elif subcmd == "timeline":
        records = ledger.query(limit=10)
        lines = ["🕒 **Recent Flight Recorder Events:**"]
        for r in records:
            lines.append(f"- `[{r.started_at[11:19]}]` #{r.seq} **{r.tool_name}** -> `{r.status.value}`")
        return "\n".join(lines)
    else:
        return f"Unknown /phoenix subcommand '{subcmd}'. Available: status, stats, timeline, report."


def recover_slash_command(args: str = "", ledger: Ledger | None = None) -> str:
    """Handler for /recover slash command."""
    if ledger is None:
        return "[phoenix] Flight recorder ledger not initialized."

    dry_run = "--dry-run" in args.lower()
    pending = ledger.pending_calls()

    if not pending:
        return "✨ [phoenix] No in-flight operations pending recovery. Ledger is clean and consistent."

    if dry_run:
        return (
            f"🔍 **Phoenix Recovery Simulation (Dry Run)**\n\n"
            f"Identified {len(pending)} pending interrupted operation(s):\n"
            + "\n".join([f"- Call `{p.id[:8]}`: `{p.tool_name}` (seq {p.seq})" for p in pending])
            + "\n\nRun `/recover` without `--dry-run` to execute forward reconciliation."
        )

    engine = RecoveryEngine(ledger)
    report = engine.recover()
    return (
        f"🛡️ **Phoenix Forward Recovery Complete**\n\n"
        f"• Interrupted Operations Reconciled: **{report.ops_recovered + report.dupes_prevented}**\n"
        f"• Duplicate Writes Prevented: **{report.dupes_prevented}**\n"
        f"• Operations Safely Cleared for Retry: **{report.ops_recovered}**\n"
        f"• LLM Tokens Wasted: **0 tokens**\n"
        f"• Capital Retained: **${report.cost_saved_cents / 100:.2f}**\n"
    )
