/**
 * Phoenix Desktop API Client.
 * 
 * Guarantee: SDK-only communication with host; no direct network or DOM access.
 */

export type Call = {
  id: string;
  session_id: string;
  seq: number;
  tool_name: string;
  status: "pending" | "committed" | "failed" | "recovered";
  side_effect_class: "read" | "write" | "external";
  pre_fingerprint?: string;
  post_fingerprint?: string;
  duration_ms?: number;
  cost_cents: number;
  started_at: string;
  committed_at?: string;
  crash_marker?: boolean;
};

export type Stats = {
  dupes_prevented: number;
  ops_recovered: number;
  llm_calls_avoided: number;
  cost_saved_cents: number;
};

export async function fetchCalls(sdk: any, sessionId?: string): Promise<Call[]> {
  const result = await sdk.invokeTool("phoenix_ledger", { action: "timeline" });
  if (typeof result === "string") {
    try {
      return JSON.parse(result);
    } catch {
      return [];
    }
  }
  return result?.calls || [];
}

export async function fetchStats(sdk: any): Promise<Stats> {
  const result = await sdk.invokeTool("phoenix_stats", {});
  if (typeof result === "string") {
    try {
      return JSON.parse(result);
    } catch {
      return { dupes_prevented: 0, ops_recovered: 0, llm_calls_avoided: 0, cost_saved_cents: 0 };
    }
  }
  return result || { dupes_prevented: 0, ops_recovered: 0, llm_calls_avoided: 0, cost_saved_cents: 0 };
}

export async function triggerRecovery(sdk: any, dryRun: boolean = false): Promise<any> {
  return await sdk.invokeTool("phoenix_recover", { dry_run: dryRun });
}
