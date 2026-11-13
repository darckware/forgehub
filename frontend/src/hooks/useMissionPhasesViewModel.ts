import { useState } from "react";
import { ApiError } from "@/lib/api";
import { useMissionPhaseMutation, type MissionPhase, type MissionPhaseRequest } from "@/hooks/useMissions";

/** ViewModel Hook for MissionPhases.tsx (§21 of the frontend standard; see
 * useImprovePromptViewModel.ts for the reference pair). Mission phases
 * (docs/architecture/MISSION_PHASES_PLAN.md): the admin adds, edits, moves
 * and deletes phases while the plan is still open (draft/planning, no
 * baseline), and approves or returns a homologated phase. Every write goes to
 * its own guarded route; the backend re-checks every rule, so the screen only
 * hides what cannot apply. */
export type MissionPhasesStatus = "idle" | "submitting" | "confirming" | "error";

export interface MissionPhasesViewModel {
  status: MissionPhasesStatus;
  errorMessage?: string;
  phases: MissionPhase[];
  canEdit: boolean;
  canDecide: boolean;
  expanded: ReadonlySet<string>;
  toggle(phaseId: string): void;
  draftName: string;
  draftObjective: string;
  setDraftName(value: string): void;
  setDraftObjective(value: string): void;
  addPhase(): void;
  editingId: string | null;
  editName: string;
  editObjective: string;
  setEditName(value: string): void;
  setEditObjective(value: string): void;
  startEdit(phase: MissionPhase): void;
  cancelEdit(): void;
  saveEdit(): void;
  move(phase: MissionPhase, direction: -1 | 1): void;
  pendingDelete: MissionPhase | null;
  askDelete(phase: MissionPhase): void;
  cancelDelete(): void;
  confirmDelete(): void;
  approve(phase: MissionPhase): void;
  returning: MissionPhase | null;
  returnReason: string;
  setReturnReason(value: string): void;
  askReturn(phase: MissionPhase): void;
  cancelReturn(): void;
  confirmReturn(): void;
}

export function phaseErrorText(error: unknown): string {
  if (error instanceof ApiError && error.body && typeof error.body === "object") {
    const detail = (error.body as { detail?: unknown }).detail;
    if (detail && typeof detail === "object") {
      const { code, message } = detail as { code?: string; message?: string };
      if (code) return `${code}: ${message ?? ""}`.trim();
    }
  }
  return error instanceof Error ? error.message : "Request failed";
}

export function useMissionPhasesViewModel({
  projectId, phases, canEdit, canDecide,
}: {
  projectId: string; phases: MissionPhase[]; canEdit: boolean; canDecide: boolean;
}): MissionPhasesViewModel {
  const mutation = useMissionPhaseMutation(projectId);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [draftName, setDraftName] = useState("");
  const [draftObjective, setDraftObjective] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editObjective, setEditObjective] = useState("");
  const [pendingDelete, setPendingDelete] = useState<MissionPhase | null>(null);
  const [returning, setReturning] = useState<MissionPhase | null>(null);
  const [returnReason, setReturnReason] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | undefined>();

  function run(request: MissionPhaseRequest, onSuccess?: () => void) {
    setErrorMessage(undefined);
    mutation.mutate(request, {
      onSuccess: () => onSuccess?.(),
      onError: (error) => setErrorMessage(phaseErrorText(error)),
    });
  }

  const status: MissionPhasesStatus = mutation.isPending ? "submitting"
    : pendingDelete || returning ? "confirming"
      : errorMessage ? "error" : "idle";

  return {
    status,
    errorMessage,
    phases,
    canEdit,
    canDecide,
    expanded,
    toggle: (phaseId) => setExpanded((current) => {
      const next = new Set(current);
      if (next.has(phaseId)) next.delete(phaseId); else next.add(phaseId);
      return next;
    }),
    draftName,
    draftObjective,
    setDraftName,
    setDraftObjective,
    addPhase: () => {
      const name = draftName.trim();
      if (!name) return;
      run({ method: "POST", path: "/phases", body: { name, objective: draftObjective.trim() || null } }, () => {
        setDraftName("");
        setDraftObjective("");
      });
    },
    editingId,
    editName,
    editObjective,
    setEditName,
    setEditObjective,
    startEdit: (phase) => {
      setEditingId(phase.phase_id);
      setEditName(phase.name);
      setEditObjective(phase.objective ?? "");
    },
    cancelEdit: () => setEditingId(null),
    saveEdit: () => {
      if (!editingId || !editName.trim()) return;
      run({ method: "PATCH", path: `/phases/${editingId}`,
        body: { name: editName.trim(), objective: editObjective.trim() || null } }, () => setEditingId(null));
    },
    move: (phase, direction) => {
      const ids = phases.map((p) => p.phase_id);
      const index = ids.indexOf(phase.phase_id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= ids.length) return;
      [ids[index], ids[target]] = [ids[target], ids[index]];
      run({ method: "POST", path: "/phases:reorder", body: { phase_ids: ids } });
    },
    pendingDelete,
    askDelete: (phase) => setPendingDelete(phase),
    cancelDelete: () => setPendingDelete(null),
    confirmDelete: () => {
      if (!pendingDelete) return;
      run({ method: "DELETE", path: `/phases/${pendingDelete.phase_id}` }, () => setPendingDelete(null));
    },
    approve: (phase) => run({ method: "POST", path: `/phases/${phase.phase_id}:approve`,
      body: { expected_phase_status: "awaiting_approval" } }),
    returning,
    returnReason,
    setReturnReason,
    askReturn: (phase) => { setReturning(phase); setReturnReason(""); },
    cancelReturn: () => setReturning(null),
    confirmReturn: () => {
      if (!returning || !returnReason.trim()) return;
      run({ method: "POST", path: `/phases/${returning.phase_id}:return`,
        body: { reason: returnReason.trim(), expected_phase_status: "awaiting_approval" } }, () => setReturning(null));
    },
  };
}
