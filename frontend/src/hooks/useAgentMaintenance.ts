import { useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import { useAgents, type Agent } from "@/hooks/useAgent";
import { useAuthorityDelegations, type AuthorityDelegation } from "@/hooks/useGovernance";

/** Agents maintaining machines (2026-10-19): one machine account
 * (`darckware`), and an agent may act on it only through ForgeHub with an
 * active governance delegation for this action -- deny by default. */
export const REMOTE_ACCESS_ACTION = "remote_access.execute";
export const RISK_LEVELS = ["low", "medium", "high"] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];
const RISK_ORDER: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };
/** A script's risk -> the delegation ceiling it needs (backend _RISK_FOR_DELEGATION). */
export const SCRIPT_RISK_NEEDS: Record<string, RiskLevel> = { read: "low", change: "medium", destructive: "high" };

export interface AuthorizedAgent {
  agent: Agent;
  /** Highest ceiling among its active delegations. */
  maxRisk: string;
  delegations: AuthorityDelegation[];
}

export function riskCovers(ceiling: string, needed: string): boolean {
  return (RISK_ORDER[ceiling] ?? -1) >= (RISK_ORDER[needed] ?? 99);
}

export function isRemoteAccessDelegation(d: AuthorityDelegation, now = Date.now()): boolean {
  return d.status === "active" && d.allowed_actions.includes(REMOTE_ACCESS_ACTION)
    && !d.product_id && !d.project_id && new Date(d.expires_at).getTime() > now;
}

/** Agents with an active remote_access.execute delegation. */
export function useAuthorizedAgents(enabled = true) {
  const agents = useAgents();
  const delegations = useAuthorityDelegations(enabled);
  const authorized = useMemo<AuthorizedAgent[]>(() => {
    const byAgent = new Map<string, AuthorityDelegation[]>();
    for (const d of delegations.data ?? []) {
      if (!isRemoteAccessDelegation(d)) continue;
      byAgent.set(d.grantee_id, [...(byAgent.get(d.grantee_id) ?? []), d]);
    }
    return (agents.data ?? [])
      .filter((a) => byAgent.has(a.id))
      .map((agent) => {
        const list = byAgent.get(agent.id)!;
        const maxRisk = list.reduce((best, d) => (riskCovers(d.max_risk ?? "low", best) ? d.max_risk ?? "low" : best), "low");
        return { agent, maxRisk, delegations: list };
      })
      .sort((a, b) => a.agent.name.localeCompare(b.agent.name));
  }, [agents.data, delegations.data]);
  return { authorized, agents: agents.data ?? [], isLoading: agents.isLoading || delegations.isLoading, isError: delegations.isError };
}

export interface AgentRequestInput {
  agent_ids: string[];
  server_ids: string[];
  instruction: string;
  scripts: { script_id: string; parameter_values: Record<string, string> }[];
  darckware_item_kind?: "ticket" | "demand";
  darckware_item_id?: string;
}

export interface AgentRequestResult {
  agent_id: string;
  agent_name: string;
  demand_id: string;
  demand_number: number | null;
}

/** "Pedir ao agente": one Messages task per agent. */
export function useRequestAgentTask() {
  const qc = useQueryClient();
  return useMutation<AgentRequestResult[], Error, AgentRequestInput>({
    mutationFn: (body) => apiClient.post("/api/v1/host-executions/agent-requests", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["demands"] });
      void qc.invalidateQueries({ queryKey: ["servers"] });
    },
  });
}
