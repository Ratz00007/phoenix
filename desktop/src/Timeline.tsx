import React from "react";
import { Call } from "./api";

interface TimelineProps {
  calls: Call[];
  selectedId: string | null;
  onSelectCall: (call: Call) => void;
}

export const Timeline: React.FC<TimelineProps> = ({ calls, selectedId, onSelectCall }) => {
  if (!calls || calls.length === 0) {
    return (
      <div style={{ padding: "24px", textAlign: "center", color: "#888", fontStyle: "italic" }}>
        No flight recorder events journaled yet. Execute agent tools to stream live telemetry.
      </div>
    );
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "committed":
        return "#10b981"; // Emerald
      case "pending":
        return "#f59e0b"; // Amber
      case "recovered":
        return "#3b82f6"; // Blue
      case "failed":
        return "#ef4444"; // Red
      default:
        return "#6b7280";
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "400px", overflowY: "auto" }}>
      {calls.map((call) => {
        const isSelected = call.id === selectedId;
        const statusColor = getStatusColor(call.status);

        return (
          <div
            key={call.id}
            onClick={() => onSelectCall(call)}
            style={{
              padding: "10px 14px",
              borderRadius: "8px",
              background: isSelected ? "rgba(59, 130, 246, 0.15)" : "rgba(255, 255, 255, 0.03)",
              border: `1px solid ${isSelected ? "#3b82f6" : "rgba(255, 255, 255, 0.08)"}`,
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "12px", fontFamily: "monospace", color: "#888" }}>#{call.seq}</span>
                <span style={{ fontWeight: 600, color: "#f3f4f6", fontSize: "14px" }}>{call.tool_name}</span>
                {call.crash_marker && (
                  <span style={{ fontSize: "11px", color: "#ef4444", background: "rgba(239, 68, 68, 0.1)", padding: "2px 6px", borderRadius: "4px" }}>
                    💥 SIGKILL
                  </span>
                )}
              </div>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  color: statusColor,
                  background: `${statusColor}18`,
                  padding: "3px 8px",
                  borderRadius: "6px",
                }}
              >
                {call.status}
              </span>
            </div>
            <div style={{ display: "flex", gap: "16px", marginTop: "6px", fontSize: "11px", color: "#9ca3af", fontFamily: "monospace" }}>
              <span>Side-Effect: {call.side_effect_class}</span>
              {call.duration_ms !== undefined && <span>Duration: {call.duration_ms}ms</span>}
              {call.cost_cents > 0 && <span>Valuation: ${call.cost_cents / 100}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
};
