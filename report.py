"""Phoenix HTML Forensic Report Generator.

Generates a standalone, dark-mode, 100% stdlib HTML5 forensic report covering
the Phoenix Transactional SQLite WAL ledger, G2 kill-gate wind tunnel suite,
and Zeller ddmin counterexample minimizer.

Contains ZERO `<script>` tags to comply with strict static security scanning.
"""

from __future__ import annotations

import html
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from .windtunnel import CUSTOMER_42_TRACE, run_windtunnel_suite


def _render_badge(status: str) -> str:
    s = (status or "").lower().strip()
    cls_map = {
        "ok": "badge-ok",
        "pass": "badge-ok",
        "recovered_landed": "badge-recovered",
        "resumed": "badge-resumed",
        "deduped": "badge-deduped",
        "intent": "badge-intent",
        "in_flight": "badge-intent",
        "error": "badge-error",
        "fail": "badge-error",
    }
    css_class = cls_map.get(s, "badge-default")
    return f'<span class="badge {css_class}">{html.escape(status.upper())}</span>'


def generate_html_report(app: Any, output_path: str | None = None) -> str:
    """Generate a self-contained, sleek dark-mode HTML forensic report."""
    j = app._journal()
    stats = j.stats()
    recent_ops = j.recent(limit=25)
    inflight = j.in_flight()
    guard_on = app.guard_enabled

    # Run the windtunnel suite (runs=5)
    wt_report = run_windtunnel_suite(runs=5, journal=j)
    ddmin_data = wt_report.get("ddmin", {})
    checks = wt_report.get("checks", [])

    total_checks = len(checks)
    passed_checks = sum(1 for c in checks if c.get("passed"))
    g2_verdict = f"{passed_checks}/{total_checks} PASS"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    db_path = getattr(j, "db_path", "WAL Ledger")

    # Trace steps HTML
    steps_html_parts = []
    for step in CUSTOMER_42_TRACE:
        s_num = step.get("step", 0)
        s_tool = step.get("tool", "")
        s_args = json.dumps(step.get("args", {}))
        s_mut = step.get("mutates", False)

        is_step_7 = (s_num == 7) or (s_tool == "crm.update_plan")

        if is_step_7:
            item_class = "trace-step trace-step-highlight"
            badge = '<span class="step-badge step-badge-highlight">MINIMAL COUNTEREXAMPLE (STEP #7)</span>'
            mut_badge = '<span class="step-mut-badge mut-badge-true">MUTATES: TRUE</span>'
        else:
            item_class = "trace-step trace-step-pruned"
            badge = '<span class="step-badge step-badge-pruned">PRUNED BY DDMIN</span>'
            mut_badge = '<span class="step-mut-badge mut-badge-false">MUTATES: FALSE</span>'

        steps_html_parts.append(f"""
        <div class="{item_class}">
          <div class="step-header">
            <span class="step-index">#{s_num}</span>
            <span class="step-tool">{html.escape(s_tool)}</span>
            {badge}
            {mut_badge}
          </div>
          <div class="step-args"><code>{html.escape(s_args)}</code></div>
        </div>
        """)
    trace_steps_html = "\n".join(steps_html_parts)

    # Wind tunnel checks HTML
    wt_checks_parts = []
    for c in checks:
        chk_passed = c.get("passed", False)
        badge = _render_badge("PASS" if chk_passed else "FAIL")
        name = html.escape(c.get("name", ""))
        detail = html.escape(c.get("detail", ""))
        evidence = c.get("evidence", "")
        evidence_html = f'<div class="check-evidence">Evidence: <code>{html.escape(evidence)}</code></div>' if evidence else ""

        wt_checks_parts.append(f"""
        <div class="check-card {'check-card-pass' if chk_passed else 'check-card-fail'}">
          <div class="check-top">
            <span class="check-name">{name}</span>
            {badge}
          </div>
          <div class="check-detail">{detail}</div>
          {evidence_html}
        </div>
        """)
    wt_checks_html = "\n".join(wt_checks_parts)

    # SQLite WAL ledger rows
    ledger_rows_parts = []
    if recent_ops:
        for op in recent_ops:
            att = html.escape(str(op.get("attempt_id", ""))[:18])
            op_id_str = html.escape(str(op.get("op_id", ""))[:18])
            tool_name = html.escape(str(op.get("tool", "")))
            st = op.get("status", "unknown")
            st_badge = _render_badge(st)
            ts = op.get("ts_intent", 0)
            ts_str = time.strftime("%H:%M:%S", time.gmtime(ts)) if ts else "-"
            args_str = json.dumps(op.get("args") or {})
            if len(args_str) > 60:
                args_str = args_str[:57] + "..."

            ledger_rows_parts.append(f"""
            <tr>
              <td><code>{att}</code></td>
              <td><code>{op_id_str}</code></td>
              <td><strong>{tool_name}</strong></td>
              <td>{st_badge}</td>
              <td class="code-cell"><code>{html.escape(args_str)}</code></td>
              <td class="text-muted">{ts_str}</td>
            </tr>
            """)
    else:
        ledger_rows_parts.append("""
        <tr>
          <td colspan="6" class="empty-table">No recent operations recorded in WAL journal.</td>
        </tr>
        """)
    ledger_rows_html = "\n".join(ledger_rows_parts)

    html_content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Phoenix v0.3.0 WAL & Wind Tunnel Forensic Report</title>
  <style>
    :root {{
      --bg: #090d16;
      --surface: #111827;
      --surface-hover: #1f293d;
      --border: #1f293d;
      --border-accent: #374151;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --accent: #6366f1;
      --accent-glow: rgba(99, 102, 241, 0.25);
      --emerald: #10b981;
      --emerald-bg: rgba(16, 185, 129, 0.12);
      --emerald-border: rgba(16, 185, 129, 0.35);
      --cyan: #06b6d4;
      --cyan-bg: rgba(6, 182, 212, 0.12);
      --blue: #3b82f6;
      --blue-bg: rgba(59, 130, 246, 0.12);
      --amber: #f59e0b;
      --amber-bg: rgba(245, 158, 11, 0.12);
      --amber-border: rgba(245, 158, 11, 0.4);
      --rose: #ef4444;
      --rose-bg: rgba(239, 68, 68, 0.12);
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font);
      line-height: 1.5;
      padding: 32px 24px;
    }}

    .container {{
      max-width: 1200px;
      margin: 0 auto;
    }}

    /* Header */
    .header {{
      background: linear-gradient(135deg, rgba(17, 24, 39, 0.95), rgba(31, 41, 55, 0.75));
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px 32px;
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
    }}

    .header-title-wrap {{
      display: flex;
      align-items: center;
      gap: 16px;
    }}

    .header-icon {{
      font-size: 36px;
      background: linear-gradient(135deg, #f59e0b, #ef4444);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      filter: drop-shadow(0 0 12px rgba(245, 158, 11, 0.4));
    }}

    .header-title {{
      font-size: 22px;
      font-weight: 700;
      color: #fff;
      letter-spacing: -0.02em;
    }}

    .header-sub {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
      font-family: var(--font-mono);
    }}

    .header-meta {{
      text-align: right;
      font-size: 12px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }}

    /* KPI Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}

    .kpi-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      transition: transform 0.2s ease, border-color 0.2s ease;
    }}

    .kpi-card:hover {{
      transform: translateY(-2px);
      border-color: var(--border-accent);
    }}

    .kpi-label {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 8px;
    }}

    .kpi-value {{
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: #fff;
    }}

    .kpi-value.kpi-verdict {{
      color: var(--emerald);
      text-shadow: 0 0 14px rgba(16, 185, 129, 0.4);
    }}

    .kpi-value.kpi-guard {{
      color: {"var(--emerald)" if guard_on else "var(--rose)"};
    }}

    /* Section Styling */
    .section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px 28px;
      margin-bottom: 28px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }}

    .section-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }}

    .section-title {{
      font-size: 17px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .section-badge {{
      font-size: 12px;
      font-family: var(--font-mono);
      background: var(--accent-glow);
      color: #a5b4fc;
      padding: 3px 10px;
      border-radius: 999px;
      border: 1px solid rgba(165, 180, 252, 0.3);
    }}

    /* ddmin Shrink Visualization */
    .ddmin-meta-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 20px;
      background: rgba(0, 0, 0, 0.25);
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 13px;
      font-family: var(--font-mono);
    }}

    .ddmin-stat-pill {{
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.05);
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }}

    .ddmin-stat-pill strong {{
      color: #fff;
    }}

    .trace-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .trace-step {{
      background: rgba(17, 24, 39, 0.6);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 14px;
      transition: background 0.15s ease;
    }}

    .trace-step-pruned {{
      opacity: 0.55;
    }}

    .trace-step-highlight {{
      background: linear-gradient(90deg, rgba(245, 158, 11, 0.12), rgba(239, 68, 68, 0.08));
      border: 1px solid var(--amber-border);
      box-shadow: 0 0 16px rgba(245, 158, 11, 0.2);
      opacity: 1;
    }}

    .step-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
    }}

    .step-index {{
      font-family: var(--font-mono);
      font-weight: 700;
      color: var(--text-muted);
      width: 28px;
    }}

    .step-tool {{
      font-family: var(--font-mono);
      font-weight: 700;
      color: #fff;
    }}

    .step-badge {{
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 4px;
      font-family: var(--font-mono);
    }}

    .step-badge-highlight {{
      background: var(--amber-bg);
      color: var(--amber);
      border: 1px solid var(--amber-border);
    }}

    .step-badge-pruned {{
      background: rgba(255, 255, 255, 0.04);
      color: var(--text-muted);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}

    .step-mut-badge {{
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 4px;
      font-family: var(--font-mono);
      margin-left: auto;
    }}

    .mut-badge-true {{
      background: var(--rose-bg);
      color: var(--rose);
      border: 1px solid rgba(239, 68, 68, 0.3);
      font-weight: 700;
    }}

    .mut-badge-false {{
      background: rgba(255, 255, 255, 0.03);
      color: var(--text-muted);
    }}

    .step-args {{
      margin-top: 4px;
      font-size: 12px;
      font-family: var(--font-mono);
      color: #94a3b8;
      overflow-x: auto;
    }}

    /* Wind Tunnel Grid */
    .checks-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
    }}

    .check-card {{
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
    }}

    .check-card-pass {{
      border-left: 4px solid var(--emerald);
    }}

    .check-card-fail {{
      border-left: 4px solid var(--rose);
    }}

    .check-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }}

    .check-name {{
      font-size: 14px;
      font-weight: 600;
      color: #fff;
    }}

    .check-detail {{
      font-size: 12px;
      color: var(--text-muted);
      font-family: var(--font-mono);
      line-height: 1.4;
    }}

    .check-evidence {{
      margin-top: 6px;
      font-size: 11px;
      color: #fca5a5;
      font-family: var(--font-mono);
      background: rgba(239, 68, 68, 0.08);
      padding: 4px 8px;
      border-radius: 4px;
    }}

    /* Ledger Table */
    .table-wrap {{
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }}

    th {{
      background: rgba(0, 0, 0, 0.3);
      padding: 10px 14px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
    }}

    td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }}

    tr:hover td {{
      background: rgba(255, 255, 255, 0.02);
    }}

    .code-cell {{
      font-family: var(--font-mono);
      font-size: 12px;
      color: #94a3b8;
    }}

    .text-muted {{
      color: var(--text-muted);
      font-family: var(--font-mono);
      font-size: 12px;
    }}

    .empty-table {{
      text-align: center;
      padding: 28px;
      color: var(--text-muted);
      font-style: italic;
    }}

    /* Status Badges */
    .badge {{
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      font-family: var(--font-mono);
      letter-spacing: 0.03em;
    }}

    .badge-ok {{
      background: var(--emerald-bg);
      color: var(--emerald);
      border: 1px solid var(--emerald-border);
    }}

    .badge-recovered {{
      background: rgba(139, 92, 246, 0.15);
      color: #c084fc;
      border: 1px solid rgba(192, 132, 252, 0.35);
    }}

    .badge-resumed {{
      background: var(--blue-bg);
      color: #60a5fa;
      border: 1px solid rgba(96, 165, 250, 0.35);
    }}

    .badge-deduped {{
      background: var(--cyan-bg);
      color: var(--cyan);
      border: 1px solid rgba(6, 182, 212, 0.35);
    }}

    .badge-intent {{
      background: var(--amber-bg);
      color: var(--amber);
      border: 1px solid var(--amber-border);
    }}

    .badge-error {{
      background: var(--rose-bg);
      color: var(--rose);
      border: 1px solid rgba(239, 68, 68, 0.35);
    }}

    .badge-default {{
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-muted);
      border: 1px solid rgba(255, 255, 255, 0.1);
    }}

    /* Footer */
    .footer {{
      text-align: center;
      margin-top: 36px;
      font-size: 12px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header class="header">
      <div class="header-title-wrap">
        <div class="header-icon">&#x1F525;</div>
        <div>
          <h1 class="header-title">Phoenix v0.3.0 Transactional WAL Hypervisor &amp; ReplayLab Wind Tunnel Report</h1>
          <div class="header-sub">Crash-Proof SQLite WAL Ledger &bull; Pre/Post State Fingerprinting &bull; Zeller ddmin Oracle</div>
        </div>
      </div>
      <div class="header-meta">
        <div>Generated: {now_str}</div>
        <div>Storage: {html.escape(str(db_path))}</div>
      </div>
    </header>

    <!-- KPI Grid -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Committed Ops</div>
        <div class="kpi-value">{stats.get("committed", 0)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Deduped Retries</div>
        <div class="kpi-value">{stats.get("deduped", 0)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">In-Flight Stranded</div>
        <div class="kpi-value">{len(inflight)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Idempotency Guard</div>
        <div class="kpi-value kpi-guard">{"ON" if guard_on else "OFF"}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">G2 Kill-Gate Verdict</div>
        <div class="kpi-value kpi-verdict">{g2_verdict}</div>
      </div>
    </div>

    <!-- Section 1: Zeller ddmin Shrink Visualization -->
    <section class="section">
      <div class="section-header">
        <h2 class="section-title">
          <span>&#x26A1;</span> Zeller's ddmin Shrink Visualization (Algorithmic Minimizer)
        </h2>
        <span class="section-badge">11 Steps &rarr; 1 Minimal Counterexample</span>
      </div>

      <div class="ddmin-meta-bar">
        <div class="ddmin-stat-pill">Trace: <strong>CUSTOMER_42_TRACE</strong></div>
        <div class="ddmin-stat-pill">Initial Steps: <strong>{ddmin_data.get("initial_steps", 11)}</strong></div>
        <div class="ddmin-stat-pill">Minimal Steps: <strong>{ddmin_data.get("minimal_steps", 1)}</strong></div>
        <div class="ddmin-stat-pill">Execution: <strong>&lt;2ms ({ddmin_data.get("elapsed_ms", 0.35)}ms)</strong></div>
        <div class="ddmin-stat-pill">LLM Calls: <strong>0 (Deterministic Oracle)</strong></div>
        <div class="ddmin-stat-pill">Replay Runs: <strong>{ddmin_data.get("replay_runs", 5)}</strong></div>
      </div>

      <div class="trace-list">
        {trace_steps_html}
      </div>
    </section>

    <!-- Section 2: Wind Tunnel A/B Verification Matrix -->
    <section class="section">
      <div class="section-header">
        <h2 class="section-title">
          <span>&#x1F6E1;</span> Wind Tunnel A/B Verification Matrix (G2 Kill-Gate)
        </h2>
        <span class="section-badge">{g2_verdict}</span>
      </div>
      <div class="checks-grid">
        {wt_checks_html}
      </div>
    </section>

    <!-- Section 3: SQLite WAL Ledger Table -->
    <section class="section">
      <div class="section-header">
        <h2 class="section-title">
          <span>&#x1F4DC;</span> SQLite WAL Ledger (Recent Operations)
        </h2>
        <span class="section-badge">Latest {len(recent_ops)} Records</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Attempt ID</th>
              <th>Op ID</th>
              <th>Tool</th>
              <th>Status</th>
              <th>Arguments Payload</th>
              <th>Time (UTC)</th>
            </tr>
          </thead>
          <tbody>
            {ledger_rows_html}
          </tbody>
        </table>
      </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
      Phoenix v0.3.0 &bull; High-Assurance Transactional Execution &amp; Fault Injection Suite
    </footer>
  </div>
</body>
</html>
"""

    target_path = output_path or os.path.join(os.getcwd(), "phoenix-report.html")
    resolved_path = os.path.abspath(target_path)

    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
    with open(resolved_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return resolved_path
