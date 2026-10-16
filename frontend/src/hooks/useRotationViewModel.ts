import { useMemo, useState } from "react";
import { useHostReadiness, useRotateMachines, type RotationKind } from "@/hooks/useHostInventory";
import { useServers, type Server } from "@/hooks/useServers";

/** Rotation dialog: pick Ready machines, confirm, run as one execution. */
export interface RotationViewModel {
  status: "idle" | "confirming" | "submitting" | "error";
  kind: RotationKind;
  candidates: Server[];
  selected: Set<string>;
  toggle: (id: string) => void;
  selectAll: () => void;
  review: () => void;
  back: () => void;
  submit: () => void;
  error: string | null;
}

export function useRotationViewModel(kind: RotationKind, onExecution: (id: string) => void): RotationViewModel {
  const { data: servers } = useServers();
  const readiness = useHostReadiness();
  const rotate = useRotateMachines();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);

  const ready = useMemo(
    () => new Set((readiness.data?.entries ?? []).filter((e) => e.readiness === "ready").map((e) => e.server_id)),
    [readiness.data],
  );
  const candidates = useMemo(
    () => (servers ?? []).filter((s) => ready.has(s.id) && s.ssh_key_path).sort((a, b) => a.name.localeCompare(b.name)),
    [servers, ready],
  );

  return {
    status: rotate.isPending ? "submitting" : rotate.isError ? "error" : confirming ? "confirming" : "idle",
    kind,
    candidates,
    selected,
    toggle: (id) =>
      setSelected((cur) => {
        const next = new Set(cur);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }),
    selectAll: () => setSelected(new Set(candidates.map((c) => c.id))),
    review: () => {
      rotate.reset();
      setConfirming(true);
    },
    back: () => setConfirming(false),
    submit: () =>
      rotate.mutate({ server_ids: [...selected], kind }, { onSuccess: (r) => onExecution(r.execution_id) }),
    error: rotate.error?.message ?? null,
  };
}
