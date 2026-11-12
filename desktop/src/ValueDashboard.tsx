import React from "react";
import { Stats } from "./api";

interface ValueDashboardProps {
  stats: Stats;
}

export const ValueDashboard: React.FC<ValueDashboardProps> = ({ stats }) => {
  const cards = [
    {
      label: "Capital Saved",
      value: `$${(stats.cost_saved_cents / 100).toFixed(2)}`,
      color: "#10b981", // Emerald
      subtext: "Protected from duplicate charges",
    },
    {
      label: "Dupes Prevented",
      value: stats.dupes_prevented.toLocaleString(),
      color: "#3b82f6", // Blue
      subtext: "Suppressed duplicate side-effects",
    },
    {
      label: "Operations Recovered",
      value: stats.ops_recovered.toLocaleString(),
      color: "#f59e0b", // Amber
      subtext: "Resumed post-SIGKILL",
    },
    {
      label: "LLM Tokens Avoided",
      value: `${(stats.llm_calls_avoided * 1500).toLocaleString()}`,
      color: "#8b5cf6", // Purple
      subtext: `${stats.llm_calls_avoided} zero-LLM turns`,
    },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px", marginBottom: "16px" }}>
      {cards.map((c, i) => (
        <div
          key={i}
          style={{
            background: "rgba(255, 255, 255, 0.03)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "8px",
            padding: "12px 14px",
          }}
        >
          <div style={{ fontSize: "11px", color: "#9ca3af", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {c.label}
          </div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: c.color, margin: "4px 0" }}>{c.value}</div>
          <div style={{ fontSize: "10px", color: "#6b7280" }}>{c.subtext}</div>
        </div>
      ))}
    </div>
  );
};
