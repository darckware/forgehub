import { useState } from "react";
import { useGrantAuthorityDelegation, useRevokeAuthorityDelegation } from "@/hooks/useGovernance";
import { REMOTE_ACCESS_ACTION, useAuthorizedAgents, type AuthorizedAgent, type RiskLevel } from "@/hooks/useAgentMaintenance";
import type { Agent } from "@/hooks/useAgent";

export const VALIDITY_DAYS = [30, 90, 180, 365] as const;

/** "Agentes autorizados" (Remote Access › Machines): grant several agents at
 * once -- one governance delegation each, so each is revoked on its own --
 * and revoke after a confirmation. idle -> granting -> submitting. */
export interface AuthorizedAgentsViewModel {
  status: "loading" | "idle" | "granting" | "submitting" | "error";
  authorized: AuthorizedAgent[];
  /** Agents that can still be granted (active, not yet authorized). */
  grantable: Agent[];
  /** The grant dialog is open (stays open on error, closes on success). */
  grantOpen: boolean;
  openGrant: () => void;
  closeGrant: () => void;
  chosen: Set<string>;
  toggleAgent: (id: string) => void;
  risk: RiskLevel;
  setRisk: (value: RiskLevel) => void;
  days: number;
  setDays: (value: number) => void;
  canGrant: boolean;
  grant: () => Promise<void>;
  revoking: AuthorizedAgent | null;
  askRevoke: (entry: AuthorizedAgent) => void;
  cancelRevoke: () => void;
  confirmRevoke: () => Promise<void>;
  revokePending: boolean;
  error: string | null;
}

export function useAuthorizedAgentsViewModel(): AuthorizedAgentsViewModel {
  const { authorized, agents, isLoading } = useAuthorizedAgents();
  const grantMutation = useGrantAuthorityDelegation();
  const revokeMutation = useRevokeAuthorityDelegation();
  const [granting, setGranting] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [risk, setRisk] = useState<RiskLevel>("medium");
  const [days, setDays] = useState(90);
  const [submitting, setSubmitting] = useState(false);
  const [revoking, setRevoking] = useState<AuthorizedAgent | null>(null);
  const [error, setError] = useState<string | null>(null);

  const authorizedIds = new Set(authorized.map((a) => a.agent.id));
  const grantable = agents.filter((a) => a.is_active && a.status === "active" && !authorizedIds.has(a.id))
    .sort((a, b) => a.name.localeCompare(b.name));

  const status = isLoading ? "loading" : submitting ? "submitting" : error ? "error" : granting ? "granting" : "idle";
  return {
    status,
    authorized,
    grantable,
    grantOpen: granting,
    openGrant: () => { setError(null); setChosen(new Set()); setGranting(true); },
    closeGrant: () => setGranting(false),
    chosen,
    toggleAgent: (id) => setChosen((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    }),
    risk,
    setRisk,
    days,
    setDays,
    canGrant: chosen.size > 0 && !submitting,
    grant: async () => {
      setSubmitting(true);
      setError(null);
      const expires = new Date(Date.now() + days * 86_400_000).toISOString();
      try {
        for (const id of chosen) {
          await grantMutation.mutateAsync({
            grantee_agent_id: id, allowed_actions: [REMOTE_ACCESS_ACTION], scope_type: "organization",
            max_risk: risk, expires_at: expires, reason: "Manutenção de máquinas pelo Acesso Remoto",
          });
        }
        setGranting(false);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setSubmitting(false);
      }
    },
    revoking,
    askRevoke: (entry) => { setError(null); setRevoking(entry); },
    cancelRevoke: () => setRevoking(null),
    confirmRevoke: async () => {
      if (!revoking) return;
      try {
        for (const d of revoking.delegations) await revokeMutation.mutateAsync(d.id);
        setRevoking(null);
      } catch (e) {
        setError((e as Error).message);
      }
    },
    revokePending: revokeMutation.isPending,
    error,
  };
}
