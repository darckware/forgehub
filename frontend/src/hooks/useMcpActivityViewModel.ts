import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

/** Auditoria do MCP do ForgeHub (Marcelo, 2026-11-15: "prefiro auditar o acesso"): what each agent
 * called on the ForgeHub MCP and which restarts/queries went to approval. Read-only, admin only. */

export interface McpCall {
  occurred_at: string;
  agent: string;
  server: string | null;
  tool: string;
  status: string | null;
  duration_ms: number | null;
}

export interface McpApprovalRequest {
  number: number;
  agent: string;
  action: string;
  approval_status: string | null;
  dispatch_status: string | null;
  created_at: string;
}

export interface McpActivity {
  days: number;
  calls: McpCall[];
  approvals: McpApprovalRequest[];
}

export type McpActivityStatus = "idle" | "loading" | "ready" | "error";

export interface McpActivityViewModel {
  status: McpActivityStatus;
  agentId: string;
  setAgentId: (id: string) => void;
  days: number;
  setDays: (days: number) => void;
  calls: McpCall[];
  approvals: McpApprovalRequest[];
}

export function useMcpActivityViewModel(active: boolean): McpActivityViewModel {
  const admin = useAuthStore((s) => Boolean(s.user?.is_admin));
  const [agentId, setAgentId] = useState("");
  const [days, setDays] = useState(7);
  const activity = useQuery({
    queryKey: ["mcp-access", "activity", agentId, days],
    queryFn: () =>
      apiClient.get<McpActivity>(
        `/api/v1/mcp-access/activity?days=${days}${agentId ? `&agent_id=${agentId}` : ""}`,
      ),
    enabled: admin && active,
  });
  return {
    status: !active ? "idle" : activity.isLoading ? "loading" : activity.isError || !activity.data ? "error" : "ready",
    agentId,
    setAgentId,
    days,
    setDays,
    calls: activity.data?.calls ?? [],
    approvals: activity.data?.approvals ?? [],
  };
}
