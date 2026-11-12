import React from "react";
import { Call } from "./api";

interface DiffViewProps {
  call: Call | null;
}

export const DiffView: React.FC<DiffViewProps> = ({ call }) => {
  if (!call) {
    return (
      <div style={{ padding: "20px", textAlign: "center", color: "#6b7280", fontStyle: "italic" }}>
        Select a tool call from the flight timeline to inspect state transition hashes.
      </div>
    );
  }

  return (
    <div style={{ background: "rgba(0, 0, 0, 0.2)", borderRadius: "8px", padding: "16px", border: "1px solid rgba(255, 255, 255, 0.08)" }}>
      <h4 style={{ margin: "0 0 12px 0", fontSize: "13px", textTransform: "uppercase", letterSpacing: "0.05em", color: "#9ca3af" }}>
        Deterministic State Transition — Call {call.id.slice(0, 8)}
      </h4>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        <div style={{ background: "rgba(239, 68, 68, 0.05)", border: "1px solid rgba(239, 68, 68, 0.2)", borderRadius: "6px", padding: "10px" }}>
          <div style={{ fontSize: "11px", fontWeight: 600, color: "#f87171", marginBottom: "4px" }}>PRE-STATE FINGERPRINT</div>
          <div style={{ fontFamily: "monospace", fontSize: "11px", color: "#d1d5db", wordBreak: "break-all" }}>
            {call.pre_fingerprint || "none (read-only or clean init)"}
          </div>
        </div>
        <div style={{ background: "rgba(16, 185, 129, 0.05)", border: "1px solid rgba(16, 185, 129, 0.2)", borderRadius: "6px", padding: "10px" }}>
          <div style={{ fontSize: "11px", fontWeight: 600, color: "#34d399", marginBottom: "4px" }}>POST-STATE FINGERPRINT</div>
          <div style={{ fontFamily: "monospace", fontSize: "11px", color: "#d1d5db", wordBreak: "break-all" }}>
            {call.post_fingerprint || "pending (uncommitted in-flight)"}
          </div>
        </div>
      </div>
    </div>
  );
};
