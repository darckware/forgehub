import { useEffect, useMemo, useState } from "react";
import { useCreateHostExecution, type ExecShell, type HostExecutionDetail } from "@/hooks/useHostExecutions";
import { useHostGroups, useHostReadiness, type HostReadiness } from "@/hooks/useHostInventory";
import {
  scriptFits,
  systemScriptFor,
  useCreateHostSchedule,
  useHostScripts,
  useRenderHostScript,
  useScriptCategories,
  type HostSchedule,
  type HostScript,
  type RenderedScript,
} from "@/hooks/useHostScripts";
import { useServers, type Server } from "@/hooks/useServers";

/**
 * The single execution screen (Marcelo, 2026-10-16: "tela única que eu possa
 * escolher as máquinas para execução dos scripts... posso agendar"): pick
 * machines (filters by client, group, OS, readiness), pick a library script
 * (or write an ad-hoc command), fill its parameters, then run now or
 * schedule (once / weekly). idle -> confirming -> submitting -> (done | error).
 */
export type WhenMode = "now" | "once" | "weekly";
export type SourceMode = "library" | "adhoc";

export interface MachineFilters {
  query: string;
  clientId: string; // "" = all, "none" = no client
  groupId: string;
  os: string; // "" | windows | linux | macos
  onlyReady: boolean;
}

export interface ExecutionComposerViewModel {
  status: "idle" | "confirming" | "submitting" | "error";
  // machines
  filters: MachineFilters;
  setFilters: (patch: Partial<MachineFilters>) => void;
  clients: { id: string; name: string }[];
  groups: { id: string; name: string }[];
  visibleMachines: Server[];
  readinessOf: (id: string) => HostReadiness | undefined;
  selected: Set<string>;
  toggleMachine: (id: string) => void;
  selectAllVisible: () => void;
  clearSelection: () => void;
  selectedMachines: Server[];
  // script
  source: SourceMode;
  setSource: (mode: SourceMode) => void;
  categories: { id: string; label: string }[];
  categoryFilter: string;
  setCategoryFilter: (id: string) => void;
  scripts: HostScript[];
  script: HostScript | null;
  selectScript: (id: string) => void;
  /** Selected machines this script can run on. */
  fitCount: number;
  paramValues: Record<string, string>;
  setParam: (name: string, value: string) => void;
  command: string;
  setCommand: (value: string) => void;
  shell: ExecShell;
  setShell: (value: ExecShell) => void;
  timeoutSeconds: number;
  setTimeoutSeconds: (value: number) => void;
  // when
  when: WhenMode;
  setWhen: (mode: WhenMode) => void;
  scheduleName: string;
  setScheduleName: (value: string) => void;
  runAt: string;
  setRunAt: (value: string) => void;
  weekdays: Set<number>;
  toggleWeekday: (day: number) => void;
  timeOfDay: string;
  setTimeOfDay: (value: string) => void;
  windowMinutes: number;
  setWindowMinutes: (value: number) => void;
  // flow
  /** Script with parameters filled, to paste through RustDesk on a machine
   * without SSH yet. */
  rendered: RenderedScript | null;
  rendering: boolean;
  renderError: string | null;
  renderForCopy: () => void;
  closeRendered: () => void;
  problems: string[];
  review: () => void;
  back: () => void;
  submit: () => void;
  error: string | null;
}

const TZ = "America/Sao_Paulo";

export function useExecutionComposerViewModel(handlers: {
  onRan: (execution: HostExecutionDetail) => void;
  onScheduled: (schedule: HostSchedule) => void;
  /** System script action to preselect ("tailscale_install", ...), from the
   * Machines tab buttons; the Windows/Linux variant follows the selection. */
  initialSystem?: string | null;
}): ExecutionComposerViewModel {
  const { data: servers } = useServers();
  const { data: hostGroups } = useHostGroups();
  const readiness = useHostReadiness();
  const { data: scriptList } = useHostScripts();
  const { data: categoryList } = useScriptCategories();
  const run = useCreateHostExecution();
  const render = useRenderHostScript();
  const schedule = useCreateHostSchedule();

  const [filters, setFiltersState] = useState<MachineFilters>({ query: "", clientId: "", groupId: "", os: "", onlyReady: false });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [source, setSource] = useState<SourceMode>("library");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [scriptId, setScriptId] = useState<string | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [command, setCommand] = useState("");
  const [shell, setShell] = useState<ExecShell>("powershell");
  const [timeoutSeconds, setTimeoutSeconds] = useState(300);
  const [when, setWhenState] = useState<WhenMode>("now");
  const [scheduleName, setScheduleName] = useState("");
  const [runAt, setRunAt] = useState("");
  const [weekdays, setWeekdays] = useState<Set<number>>(new Set());
  const [timeOfDay, setTimeOfDay] = useState("22:00");
  const [windowMinutes, setWindowMinutes] = useState(120);
  const [confirming, setConfirming] = useState(false);

  const readinessById = useMemo(
    () => new Map((readiness.data?.entries ?? []).map((e) => [e.server_id, e.readiness])),
    [readiness.data],
  );
  const machines = useMemo(() => [...(servers ?? [])].sort((a, b) => a.name.localeCompare(b.name)), [servers]);
  const groupMembers = useMemo(
    () => new Map((hostGroups ?? []).map((g) => [g.id, new Set(g.server_ids)])),
    [hostGroups],
  );

  const visibleMachines = useMemo(() => {
    const q = filters.query.trim().toLowerCase();
    return machines.filter((m) => {
      if (filters.clientId === "none" ? m.darckware_client_id : filters.clientId && m.darckware_client_id !== filters.clientId) return false;
      if (filters.groupId && !groupMembers.get(filters.groupId)?.has(m.id)) return false;
      if (filters.os && (m.os_family ?? "linux") !== filters.os) return false;
      if (filters.onlyReady && readinessById.get(m.id) !== "ready") return false;
      if (q && ![m.name, m.ip_address, m.location, m.darckware_client_name].some((v) => v?.toLowerCase().includes(q))) return false;
      return true;
    });
  }, [machines, filters, groupMembers, readinessById]);

  const clients = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of machines) if (m.darckware_client_id) map.set(m.darckware_client_id, m.darckware_client_name ?? m.darckware_client_id);
    return [...map].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [machines]);

  const selectedMachines = machines.filter((m) => selected.has(m.id));

  // A system action picks its variant from the selected machines' OS.
  const [systemAction] = useState(handlers.initialSystem ?? null);
  const selectionOs = selectedMachines.length > 0 && selectedMachines.every((m) => m.os_family !== "windows") ? "linux" : "windows";
  useEffect(() => {
    if (!systemAction || !scriptList) return;
    const variant = systemScriptFor(scriptList, systemAction, selectionOs);
    if (variant && variant.id !== scriptId) {
      setScriptId(variant.id);
      setTimeoutSeconds(variant.timeout_seconds);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [systemAction, scriptList, selectionOs]);
  const scripts = (scriptList ?? []).filter((s) => !categoryFilter || s.category_id === categoryFilter);
  const script = (scriptList ?? []).find((s) => s.id === scriptId) ?? null;
  const fitCount = script ? selectedMachines.filter((m) => scriptFits(script.platform, m.os_family)).length : selectedMachines.length;

  const problems: string[] = [];
  if (selectedMachines.length === 0) problems.push("noMachines");
  if (source === "library") {
    if (!script) problems.push("noScript");
    else {
      if (fitCount === 0 && selectedMachines.length > 0) problems.push("noCompatible");
      for (const p of script.parameters) if (p.required && !p.vault_secret && !(paramValues[p.name] ?? p.default ?? "").trim()) problems.push("missingParams");
    }
  } else if (!command.trim()) problems.push("noCommand");
  if (when !== "now") {
    if (source === "adhoc") problems.push("scheduleNeedsScript");
    if (!scheduleName.trim()) problems.push("noScheduleName");
    if (when === "once" && !runAt) problems.push("noRunAt");
    if (when === "weekly" && weekdays.size === 0) problems.push("noWeekdays");
  }

  const status = run.isPending || schedule.isPending ? "submitting" : run.isError || schedule.isError ? "error" : confirming ? "confirming" : "idle";

  const toggle = <T,>(set: Set<T>, value: T) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
  };

  return {
    status,
    filters,
    setFilters: (patch) => setFiltersState((cur) => ({ ...cur, ...patch })),
    clients,
    groups: (hostGroups ?? []).map((g) => ({ id: g.id, name: g.darckware_client_name ? `${g.name} · ${g.darckware_client_name}` : g.name })),
    visibleMachines,
    readinessOf: (id) => readinessById.get(id),
    selected,
    toggleMachine: (id) => setSelected((cur) => toggle(cur, id)),
    selectAllVisible: () => setSelected((cur) => new Set([...cur, ...visibleMachines.map((m) => m.id)])),
    clearSelection: () => setSelected(new Set()),
    selectedMachines,
    source,
    setSource,
    categories: (categoryList ?? []).map((c) => ({ id: c.id, label: c.label })),
    categoryFilter,
    setCategoryFilter,
    scripts,
    script,
    selectScript: (id) => {
      setScriptId(id || null);
      setParamValues({});
      const picked = (scriptList ?? []).find((s) => s.id === id);
      if (picked) setTimeoutSeconds(picked.timeout_seconds);
    },
    fitCount,
    paramValues,
    setParam: (name, value) => setParamValues((cur) => ({ ...cur, [name]: value })),
    command,
    setCommand,
    shell,
    setShell,
    timeoutSeconds,
    setTimeoutSeconds,
    when,
    setWhen: setWhenState,
    scheduleName,
    setScheduleName,
    runAt,
    setRunAt,
    weekdays,
    toggleWeekday: (day) => setWeekdays((cur) => toggle(cur, day)),
    timeOfDay,
    setTimeOfDay,
    windowMinutes,
    setWindowMinutes,
    rendered: render.data ?? null,
    rendering: render.isPending,
    renderError: render.error?.message ?? null,
    renderForCopy: () => {
      if (!script) return;
      const values = Object.fromEntries(Object.entries(paramValues).filter(([, v]) => v !== ""));
      render.mutate({ id: script.id, parameter_values: values });
    },
    closeRendered: () => render.reset(),
    problems,
    review: () => {
      run.reset();
      schedule.reset();
      setConfirming(true);
    },
    back: () => setConfirming(false),
    submit: () => {
      const serverIds = selectedMachines.map((m) => m.id);
      const values = Object.fromEntries(Object.entries(paramValues).filter(([, v]) => v !== ""));
      if (when === "now") {
        run.mutate(
          source === "library"
            ? { script_id: script!.id, parameter_values: values, server_ids: serverIds, group_ids: [], timeout_seconds: timeoutSeconds }
            : { command, shell, server_ids: serverIds, group_ids: [], timeout_seconds: timeoutSeconds },
          {
            onSuccess: (execution) => {
              setConfirming(false);
              handlers.onRan(execution);
            },
          },
        );
        return;
      }
      schedule.mutate(
        {
          name: scheduleName.trim(),
          script_id: script!.id,
          parameter_values: values,
          server_ids: serverIds,
          group_ids: [],
          kind: when,
          // datetime-local is wall-clock time in the client's timezone; the
          // backend interprets a naive value in `timezone`.
          run_at: when === "once" ? runAt : null,
          weekdays: when === "weekly" ? [...weekdays].sort() : null,
          time_of_day: when === "weekly" ? timeOfDay : null,
          timezone: TZ,
          window_minutes: windowMinutes,
        },
        {
          onSuccess: (created) => {
            setConfirming(false);
            handlers.onScheduled(created);
          },
        },
      );
    },
    error: run.error?.message ?? schedule.error?.message ?? null,
  };
}
