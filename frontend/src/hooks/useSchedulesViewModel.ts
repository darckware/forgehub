import { useState } from "react";
import {
  useDeleteHostSchedule,
  useHostSchedules,
  useRunHostScheduleNow,
  useUpdateHostSchedule,
  type HostSchedule,
} from "@/hooks/useHostScripts";
import type { HostExecutionDetail } from "@/hooks/useHostExecutions";

/** Schedules list: pause/resume, run now, delete (with confirmation). */
export interface SchedulesViewModel {
  status: "loading" | "error" | "ready";
  schedules: HostSchedule[];
  toggle: (schedule: HostSchedule) => void;
  togglingId: string | null;
  runNow: (schedule: HostSchedule) => void;
  runningId: string | null;
  deleting: HostSchedule | null;
  askDelete: (schedule: HostSchedule) => void;
  cancelDelete: () => void;
  confirmDelete: () => void;
  removing: boolean;
  error: string | null;
}

export function useSchedulesViewModel(onRan: (execution: HostExecutionDetail) => void): SchedulesViewModel {
  const query = useHostSchedules();
  const update = useUpdateHostSchedule();
  const runNow = useRunHostScheduleNow();
  const remove = useDeleteHostSchedule();
  const [deleting, setDeleting] = useState<HostSchedule | null>(null);

  return {
    status: query.isLoading ? "loading" : query.isError ? "error" : "ready",
    schedules: query.data ?? [],
    toggle: (s) => update.mutate({ id: s.id, data: { enabled: !s.enabled } }),
    togglingId: update.isPending ? update.variables?.id ?? null : null,
    runNow: (s) => runNow.mutate(s.id, { onSuccess: onRan }),
    runningId: runNow.isPending ? runNow.variables ?? null : null,
    deleting,
    askDelete: (s) => {
      remove.reset();
      setDeleting(s);
    },
    cancelDelete: () => setDeleting(null),
    confirmDelete: () => {
      if (deleting) remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
    },
    removing: remove.isPending,
    error: update.error?.message ?? runNow.error?.message ?? remove.error?.message ?? null,
  };
}
