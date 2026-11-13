import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";
import { phaseErrorText } from "@/hooks/useMissionPhasesViewModel";

/** Marcelo's pending mission decisions, shown at the top of Pessoal → Tarefas
 * dos agentes (2026-11-13: one approval inbox). Read from
 * `GET /api/v1/missions/pending-decisions` (admin only); deciding goes through
 * the routes that own each decision -- the governed plan approval
 * (`/governed/approval-requests/{id}:decide`) and the phase routes
 * (`/missions/{id}/phases/{phase_id}:approve|:return`) -- never a shortcut.
 *
 * ViewModel Hook (§21 of the frontend standard): the card renders this
 * hook's fields; `status` is `loading → ready → confirming → submitting →
 * ready | error`. A rejection/return always carries a reason. */
export const pendingMissionDecisionSchema = z.object({
  kind: z.enum(["plan_approval", "phase_approval"]),
  mission_project_id: z.string(),
  mission_name: z.string(),
  title: z.string(),
  summary: z.string().nullable(),
  requested_at: z.string().nullable(),
  requested_by: z.string().nullable().optional(),
  approval_request_id: z.string().nullable().optional(),
  project_plan_id: z.string().nullable().optional(),
  task_count: z.number().nullable().optional(),
  phase_id: z.string().nullable().optional(),
  phase_position: z.number().nullable().optional(),
  phase_name: z.string().nullable().optional(),
  homologation_evidence: z.array(z.string()).default([]),
  link: z.string(),
});
export type PendingMissionDecision = z.infer<typeof pendingMissionDecisionSchema>;

export const missionDecisionsKey = ["mission-pending-decisions"] as const;

export type MissionDecisionChoice = "approve" | "reject";
export type MissionDecisionsStatus = "loading" | "ready" | "confirming" | "submitting" | "error";

export interface MissionDecisionsViewModel {
  status: MissionDecisionsStatus;
  items: PendingMissionDecision[];
  /** The card is hidden while nothing is pending (or the reader isn't an admin). */
  visible: boolean;
  loadFailed: boolean;
  errorMessage?: string;
  pending: { item: PendingMissionDecision; choice: MissionDecisionChoice } | null;
  reason: string;
  reasonRequired: boolean;
  setReason(value: string): void;
  ask(item: PendingMissionDecision, choice: MissionDecisionChoice): void;
  cancel(): void;
  confirm(): void;
  retry(): void;
}

export function decisionKey(item: PendingMissionDecision): string {
  return item.kind === "plan_approval" ? `plan:${item.approval_request_id}` : `phase:${item.phase_id}`;
}

async function decide(item: PendingMissionDecision, choice: MissionDecisionChoice, reason: string) {
  const comments = reason.trim() || undefined;
  if (item.kind === "plan_approval") {
    return apiClient.post(`/api/v1/governed/approval-requests/${item.approval_request_id}:decide`, {
      decision: choice === "approve" ? "approved" : "rejected", comments, idempotency_key: crypto.randomUUID(),
    });
  }
  const base = `/api/v1/missions/${item.mission_project_id}/phases/${item.phase_id}`;
  return choice === "approve"
    ? apiClient.post(`${base}:approve`, { reason: comments ?? null, expected_phase_status: "awaiting_approval" })
    : apiClient.post(`${base}:return`, { reason: reason.trim(), expected_phase_status: "awaiting_approval" });
}

export function useMissionDecisionsViewModel(enabled = true): MissionDecisionsViewModel {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: missionDecisionsKey,
    queryFn: async () => z.array(pendingMissionDecisionSchema).parse(
      await apiClient.get<unknown>("/api/v1/missions/pending-decisions")),
    enabled,
    refetchInterval: 60_000,
  });
  const [pending, setPending] = useState<MissionDecisionsViewModel["pending"]>(null);
  const [reason, setReason] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | undefined>();
  const mutation = useMutation({
    mutationFn: ({ item, choice, text }: { item: PendingMissionDecision; choice: MissionDecisionChoice; text: string }) =>
      decide(item, choice, text),
    onSuccess: (_data, { item }) => {
      void client.invalidateQueries({ queryKey: missionDecisionsKey });
      void client.invalidateQueries({ queryKey: ["governed-approval-requests"] });
      void client.invalidateQueries({ queryKey: ["mission-board", item.mission_project_id] });
      void client.invalidateQueries({ queryKey: ["missions"] });
    },
  });
  const items = query.data ?? [];
  const reasonRequired = pending?.choice === "reject";
  const status: MissionDecisionsStatus = query.isLoading ? "loading"
    : mutation.isPending ? "submitting"
      : pending ? "confirming"
        : errorMessage ? "error" : "ready";
  return {
    status,
    items,
    visible: items.length > 0 || Boolean(errorMessage),
    loadFailed: query.isError,
    errorMessage,
    pending,
    reason,
    reasonRequired,
    setReason,
    ask: (item, choice) => { setPending({ item, choice }); setReason(""); setErrorMessage(undefined); },
    cancel: () => { if (!mutation.isPending) setPending(null); },
    confirm: () => {
      if (!pending || (reasonRequired && !reason.trim())) return;
      setErrorMessage(undefined);
      mutation.mutate({ item: pending.item, choice: pending.choice, text: reason }, {
        onSuccess: () => setPending(null),
        onError: (error) => setErrorMessage(phaseErrorText(error)),
      });
    },
    retry: () => { void query.refetch(); },
  };
}
