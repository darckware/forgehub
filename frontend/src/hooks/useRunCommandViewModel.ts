import { useMemo, useState } from "react";
import { useHostGroups } from "@/hooks/useHostInventory";
import {
  shellForOs,
  useCreateHostExecution,
  type ExecShell,
  type HostExecutionDetail,
} from "@/hooks/useHostExecutions";
import { useServers, type Server } from "@/hooks/useServers";

/** "Run a command" dialog: pick machines and/or groups, write the command,
 * review, confirm. idle -> confirming -> submitting -> (closed | error). */
export interface RunCommandViewModel {
  status: "idle" | "confirming" | "submitting" | "error";
  machines: Server[];
  groups: { id: string; name: string; clientName: string | null; size: number }[];
  serverIds: Set<string>;
  groupIds: Set<string>;
  toggleServer: (id: string) => void;
  toggleGroup: (id: string) => void;
  /** Distinct machines the run will reach (groups expanded). */
  targetCount: number;
  command: string;
  setCommand: (value: string) => void;
  shell: ExecShell;
  setShell: (value: ExecShell) => void;
  /** The picked machines mix Windows with Linux/macOS. */
  mixedOs: boolean;
  timeoutSeconds: number;
  setTimeoutSeconds: (value: number) => void;
  canReview: boolean;
  review: () => void;
  back: () => void;
  submit: () => void;
  error: string | null;
}

export function useRunCommandViewModel(
  onStarted: (execution: HostExecutionDetail) => void,
  initialServerIds: string[] = [],
): RunCommandViewModel {
  const { data: servers } = useServers();
  const { data: hostGroups } = useHostGroups();
  const create = useCreateHostExecution();

  const [serverIds, setServerIds] = useState(() => new Set(initialServerIds));
  const [groupIds, setGroupIds] = useState<Set<string>>(new Set());
  const [command, setCommand] = useState("");
  const [shellChoice, setShellChoice] = useState<ExecShell | null>(null);
  const [timeoutSeconds, setTimeoutSeconds] = useState(300);
  const [confirming, setConfirming] = useState(false);

  const machines = useMemo(
    () => [...(servers ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [servers],
  );
  const targets = useMemo(() => {
    const ids = new Set(serverIds);
    for (const g of hostGroups ?? []) if (groupIds.has(g.id)) g.server_ids.forEach((id) => ids.add(id));
    return machines.filter((m) => ids.has(m.id));
  }, [serverIds, groupIds, hostGroups, machines]);

  const suggested = shellForOs(targets.map((t) => t.os_family));
  const shell = shellChoice ?? suggested ?? "sh";
  const toggle = (set: Set<string>, id: string) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  };

  const status = create.isPending
    ? "submitting"
    : create.isError
      ? "error"
      : confirming
        ? "confirming"
        : "idle";

  return {
    status,
    machines,
    groups: (hostGroups ?? []).map((g) => ({
      id: g.id, name: g.name, clientName: g.darckware_client_name, size: g.server_ids.length,
    })),
    serverIds,
    groupIds,
    toggleServer: (id) => setServerIds((cur) => toggle(cur, id)),
    toggleGroup: (id) => setGroupIds((cur) => toggle(cur, id)),
    targetCount: targets.length,
    command,
    setCommand,
    shell,
    setShell: setShellChoice,
    mixedOs: targets.length > 0 && suggested === null,
    timeoutSeconds,
    setTimeoutSeconds,
    canReview: targets.length > 0 && command.trim().length > 0,
    review: () => {
      create.reset();
      setConfirming(true);
    },
    back: () => {
      create.reset();
      setConfirming(false);
    },
    submit: () =>
      create.mutate(
        {
          command,
          shell,
          server_ids: [...serverIds],
          group_ids: [...groupIds],
          timeout_seconds: timeoutSeconds,
        },
        { onSuccess: onStarted },
      ),
    error: create.error?.message ?? null,
  };
}
