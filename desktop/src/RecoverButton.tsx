import React, { useState } from "react";
import { triggerRecovery } from "./api";

interface RecoverButtonProps {
  sdk: any;
  onRecovered?: (report: any) => void;
}

export const RecoverButton: React.FC<RecoverButtonProps> = ({ sdk, onRecovered }) => {
  const [loading, setLoading] = useState(false);
  const [lastOutcome, setLastOutcome] = useState<string | null>(null);

  const handleRecover = async (dryRun: boolean) => {
    setLoading(true);
    setLastOutcome(null);
    try {
      const res = await triggerRecovery(sdk, dryRun);
      const parsed = typeof res === "string" ? JSON.parse(res) : res;
      setLastOutcome(
        dryRun
          ? `Dry run identified ${parsed.pending_ops?.length || 0} operations.`
          : `Recovered ${parsed.dupes_prevented || 0} dupes with 0 LLM calls.`
      );
      if (onRecovered) {
        onRecovered(parsed);
      }
    } catch (err: any) {
      setLastOutcome(`Error: ${err?.message || "Recovery failed"}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
      <button
        onClick={() => handleRecover(false)}
        disabled={loading}
        style={{
          background: "linear-gradient(135deg, #f97316 0%, #ea580c 100%)",
          color: "#fff",
          border: "none",
          borderRadius: "6px",
          padding: "8px 16px",
          fontWeight: 600,
          fontSize: "13px",
          cursor: loading ? "wait" : "pointer",
          boxShadow: "0 2px 4px rgba(249, 115, 22, 0.2)",
        }}
      >
        {loading ? "Reconciling State..." : "⚡ One-Click Forward Recovery"}
      </button>
      <button
        onClick={() => handleRecover(true)}
        disabled={loading}
        style={{
          background: "transparent",
          color: "#9ca3af",
          border: "1px solid rgba(255, 255, 255, 0.15)",
          borderRadius: "6px",
          padding: "8px 12px",
          fontSize: "12px",
          cursor: loading ? "wait" : "pointer",
        }}
      >
        Dry Run
      </button>
      {lastOutcome && <span style={{ fontSize: "12px", color: "#10b981", marginLeft: "8px" }}>{lastOutcome}</span>}
    </div>
  );
};
