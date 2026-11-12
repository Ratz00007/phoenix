/**
 * Phoenix Flight Recorder Desktop Extension.
 * 
 * Invariants:
 * - SDK-only entry. Imports strictly @hermes/plugin-sdk and react.
 * - Zero eval, zero new Function, zero prototype modifications.
 * - Read-only telemetry; recovery actions require explicit user click.
 */

import React, { useState, useEffect } from "react";
import { getPluginSDK } from "@hermes/plugin-sdk";

export default function PhoenixFlightRecorder() {
  const sdk = getPluginSDK();
  const [calls, setCalls] = useState([]);
  const [stats, setStats] = useState({
    dupes_prevented: 0,
    ops_recovered: 0,
    llm_calls_avoided: 0,
    cost_saved_cents: 0,
  });
  const [selectedCall, setSelectedCall] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshData = async () => {
    try {
      const timelineRes = await sdk.invokeTool("phoenix_ledger", { action: "timeline" });
      const statsRes = await sdk.invokeTool("phoenix_stats", {});

      const parsedTimeline = typeof timelineRes === "string" ? JSON.parse(timelineRes) : timelineRes;
      const parsedStats = typeof statsRes === "string" ? JSON.parse(statsRes) : statsRes;

      if (Array.isArray(parsedTimeline)) {
        setCalls(parsedTimeline);
        if (!selectedCall && parsedTimeline.length > 0) {
          setSelectedCall(parsedTimeline[0]);
        }
      }
      if (parsedStats && typeof parsedStats === "object") {
        setStats(parsedStats);
      }
    } catch (err) {
      // Graceful fallback for demo or empty states
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: "16px", color: "#f3f4f6", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 700, letterSpacing: "-0.02em" }}>
            🔥 Phoenix Flight Recorder
          </h2>
          <p style={{ margin: "2px 0 0 0", fontSize: "12px", color: "#9ca3af" }}>
            The exactly-once trust layer for autonomous agents (WAL SQLite 0600)
          </p>
        </div>
        <button
          onClick={refreshData}
          style={{
            background: "rgba(255, 255, 255, 0.05)",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            color: "#e5e7eb",
            borderRadius: "6px",
            padding: "6px 12px",
            fontSize: "12px",
            cursor: "pointer",
          }}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Value Telemetry Dashboard */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px", marginBottom: "16px" }}>
        <div style={{ background: "rgba(255, 255, 255, 0.03)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", padding: "12px 14px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", textTransform: "uppercase" }}>Capital Saved</div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: "#10b981", margin: "4px 0" }}>
            ${(stats.cost_saved_cents / 100).toFixed(2)}
          </div>
          <div style={{ fontSize: "10px", color: "#6b7280" }}>Zero duplicate charges</div>
        </div>
        <div style={{ background: "rgba(255, 255, 255, 0.03)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", padding: "12px 14px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", textTransform: "uppercase" }}>Dupes Prevented</div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: "#3b82f6", margin: "4px 0" }}>
            {stats.dupes_prevented}
          </div>
          <div style={{ fontSize: "10px", color: "#6b7280" }}>Idempotent replays</div>
        </div>
        <div style={{ background: "rgba(255, 255, 255, 0.03)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", padding: "12px 14px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", textTransform: "uppercase" }}>Ops Recovered</div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: "#f59e0b", margin: "4px 0" }}>
            {stats.ops_recovered}
          </div>
          <div style={{ fontSize: "10px", color: "#6b7280" }}>Reconciled post-SIGKILL</div>
        </div>
        <div style={{ background: "rgba(255, 255, 255, 0.03)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: "8px", padding: "12px 14px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", textTransform: "uppercase" }}>LLM Tokens Saved</div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: "#8b5cf6", margin: "4px 0" }}>
            {(stats.llm_calls_avoided * 1500).toLocaleString()}
          </div>
          <div style={{ fontSize: "10px", color: "#6b7280" }}>Zero-LLM forward recovery</div>
        </div>
      </div>

      {/* Main Two-Column View */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: "16px", marginBottom: "16px" }}>
        {/* Timeline Column */}
        <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.06)", borderRadius: "8px", padding: "14px" }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: "13px", color: "#9ca3af", textTransform: "uppercase" }}>
            Flight Telemetry Timeline
          </h3>
          {calls.length === 0 ? (
            <div style={{ padding: "20px", textAlign: "center", color: "#6b7280", fontStyle: "italic", fontSize: "13px" }}>
              No in-flight calls recorded.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {calls.map((c) => (
                <div
                  key={c.id}
                  onClick={() => setSelectedCall(c)}
                  style={{
                    padding: "8px 12px",
                    borderRadius: "6px",
                    background: selectedCall?.id === c.id ? "rgba(59, 130, 246, 0.15)" : "transparent",
                    border: `1px solid ${selectedCall?.id === c.id ? "#3b82f6" : "rgba(255, 255, 255, 0.04)"}`,
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#6b7280" }}>#{c.seq}</span>
                    <span style={{ fontSize: "13px", fontWeight: 600 }}>{c.tool}</span>
                  </div>
                  <span style={{ fontSize: "11px", fontWeight: 600, textTransform: "uppercase", color: c.status === "committed" ? "#10b981" : "#f59e0b" }}>
                    {c.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* State Transition Diff Column */}
        <div style={{ background: "rgba(255, 255, 255, 0.02)", border: "1px solid rgba(255, 255, 255, 0.06)", borderRadius: "8px", padding: "14px" }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: "13px", color: "#9ca3af", textTransform: "uppercase" }}>
            State Fingerprint Inspector
          </h3>
          {selectedCall ? (
            <div>
              <div style={{ marginBottom: "12px", fontSize: "12px" }}>
                <strong>Tool:</strong> <code>{selectedCall.tool}</code> (Seq #{selectedCall.seq})
              </div>
              <div style={{ marginBottom: "12px", background: "rgba(0,0,0,0.3)", padding: "10px", borderRadius: "6px" }}>
                <div style={{ fontSize: "10px", color: "#f87171", fontWeight: 600, marginBottom: "4px" }}>PRE-STATE HASH</div>
                <div style={{ fontFamily: "monospace", fontSize: "11px", wordBreak: "break-all" }}>
                  {selectedCall.pre_fingerprint || "00000000000000000000000000000000"}
                </div>
              </div>
              <div style={{ background: "rgba(0,0,0,0.3)", padding: "10px", borderRadius: "6px" }}>
                <div style={{ fontSize: "10px", color: "#34d399", fontWeight: 600, marginBottom: "4px" }}>POST-STATE HASH</div>
                <div style={{ fontFamily: "monospace", fontSize: "11px", wordBreak: "break-all" }}>
                  {selectedCall.post_fingerprint || "pending (uncommitted in-flight)"}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ padding: "20px", textAlign: "center", color: "#6b7280", fontStyle: "italic", fontSize: "13px" }}>
              Select a call to inspect cryptographic fingerprints.
            </div>
          )}
        </div>
      </div>

      {/* Action Footer */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "rgba(255, 255, 255, 0.02)", padding: "12px 16px", borderRadius: "8px" }}>
        <div style={{ fontSize: "12px", color: "#9ca3af" }}>
          Interrupted in-flight tool calls? Trigger instant forward reconciliation.
        </div>
        <button
          onClick={async () => {
            await sdk.invokeTool("phoenix_recover", { dry_run: false });
            refreshData();
          }}
          style={{
            background: "linear-gradient(135deg, #f97316 0%, #ea580c 100%)",
            color: "#fff",
            border: "none",
            borderRadius: "6px",
            padding: "8px 16px",
            fontWeight: 600,
            fontSize: "13px",
            cursor: "pointer",
          }}
        >
          ⚡ One-Click Forward Recovery
        </button>
      </div>
    </div>
  );
}
