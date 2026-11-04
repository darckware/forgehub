import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface AgentAccessRow {
  id: string;
  name: string;
  slug: string | null;
  enabled: boolean;
  has_credential: boolean;
  last_session_at: string | null;
}

export interface AccessEvent {
  id: string;
  agent: string;
  event: string;
  occurred_at: string;
  details: { path?: string; area?: string; reason?: string; ip_address?: string; user_agent?: string };
}

export type AgentAccessStatus = "loading" | "ready" | "error";

export interface AgentAccessViewModel {
  status: AgentAccessStatus;
  agents: AgentAccessRow[];
  events: AccessEvent[];
  agentFilter: string;
  setAgentFilter: (agentId: string) => void;
  togglingId: string | null;
  toggleFailed: boolean;
  toggle: (agent: AgentAccessRow) => void;
}

/** Which agents may open the screens, and the audit of what they did. */
export function useAgentAccessViewModel(): AgentAccessViewModel {
  const queryClient = useQueryClient();
  const [agentFilter, setAgentFilter] = useState("");
  const agents = useQuery({
    queryKey: ["agent-access"],
    queryFn: () => apiClient.get<AgentAccessRow[]>("/api/v1/agent-access"),
  });
  const events = useQuery({
    queryKey: ["agent-access", "audit", agentFilter],
    queryFn: () =>
      apiClient.get<AccessEvent[]>(
        `/api/v1/agent-access/audit?limit=100${agentFilter ? `&agent_id=${agentFilter}` : ""}`,
      ),
  });
  const mutation = useMutation({
    mutationFn: (agent: AgentAccessRow) =>
      apiClient.put(`/api/v1/agent-access/${agent.id}`, { enabled: !agent.enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["agent-access"] }),
  });

  let status: AgentAccessStatus = "ready";
  if (agents.isLoading || events.isLoading) status = "loading";
  else if (agents.isError || events.isError) status = "error";

  return {
    status,
    agents: agents.data ?? [],
    events: events.data ?? [],
    agentFilter,
    setAgentFilter,
    togglingId: mutation.isPending ? (mutation.variables?.id ?? null) : null,
    toggleFailed: mutation.isError,
    toggle: (agent) => mutation.mutate(agent),
  };
}
