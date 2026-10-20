/**
 * Subagents launched inside one chat turn (2026-09-26, Marcelo: "preciso
 * visualizar as tarefas dos subagentes caso eu queira trocar o display na
 * tela. Tem que aparecer as listas dos agentes em execução").
 *
 * The host-bridge tags Claude Code's subagent activity (see `_claude_events`
 * in host-bridge/app.py): the launching `tool_start` carries `subagent`, the
 * subagent's own steps carry `parentId`, its text arrives as
 * `subagent_delta`, and `subagent_status` reports start/progress/finish.
 * These helpers fold those events into a turn -- pure, so the rules are
 * testable without rendering ChatPane.
 */

export type SubagentStatus = "running" | "completed" | "failed" | "stopped";

/** Structurally the same as ChatPane's ChatQueueStep, so its trail renderer
 * can draw a subagent's steps unchanged. */
export interface SubagentStep {
  id: string;
  name: string;
  label: string;
  detail?: string;
  done: boolean;
}

export interface ChatSubagent {
  /** The launching Agent/Task tool call id -- what the subagent's steps and
   * text point back to as `parentId`. */
  id: string;
  description: string;
  subagentType: string;
  status: SubagentStatus;
  /** The subagent's own streamed output, kept apart from the main reply. */
  text: string;
  /** Tool calls the subagent itself made -- kept here rather than in the
   * turn's trail, so the main trail shows only the launch and the panel can
   * still show them after the turn ends. */
  steps: SubagentStep[];
  lastTool?: string;
  summary?: string;
  /** A backgrounded subagent keeps running after its launch returns, so the
   * launch's completion must not mark it done -- only its task status can. */
  backgrounded?: boolean;
}

export type SubagentMap = Record<string, ChatSubagent>;

function normalizeStatus(value: string | undefined): SubagentStatus {
  if (value === "completed" || value === "failed" || value === "stopped") return value;
  if (value === "error" || value === "killed") return "failed";
  return "running";
}

function upsert(map: SubagentMap, id: string, patch: Partial<ChatSubagent>): SubagentMap {
  const current: ChatSubagent = map[id] ?? { id, description: "", subagentType: "", status: "running", text: "", steps: [] };
  return { ...map, [id]: { ...current, ...patch } };
}

/** A tool_start that launched a subagent. */
export function onSubagentLaunched(
  map: SubagentMap | undefined,
  toolId: string,
  info: { description?: string; subagentType?: string }
): SubagentMap {
  return upsert(map ?? {}, toolId, {
    description: info.description ?? "",
    subagentType: info.subagentType ?? "",
  });
}

/** A tool call made by a subagent (a tool_start carrying parentId). */
export function onSubagentStep(map: SubagentMap | undefined, parentId: string, step: SubagentStep): SubagentMap {
  const base = map ?? {};
  return upsert(base, parentId, { steps: [...(base[parentId]?.steps ?? []), step] });
}

/** That call finishing (a tool_complete carrying parentId). */
export function onSubagentStepDone(map: SubagentMap | undefined, parentId: string, stepId: string): SubagentMap {
  const current = map?.[parentId];
  if (!map || !current) return map ?? {};
  return upsert(map, parentId, { steps: current.steps.map((s) => (s.id === stepId ? { ...s, done: true } : s)) });
}

/** A tool_complete. For a foreground subagent, its launch returning is the
 * subagent finishing; a backgrounded one only finishes via its task status. */
export function onToolCompleted(map: SubagentMap | undefined, toolId: string, isError?: boolean): SubagentMap {
  const current = map?.[toolId];
  if (!map || !current || current.backgrounded || current.status !== "running") return map ?? {};
  return upsert(map, toolId, { status: isError ? "failed" : "completed" });
}

export function onSubagentText(map: SubagentMap | undefined, parentId: string, text: string): SubagentMap {
  const base = map ?? {};
  return upsert(base, parentId, { text: (base[parentId]?.text ?? "") + text });
}

export function onSubagentStatus(
  map: SubagentMap | undefined,
  event: { toolId: string; status?: string; description?: string; subagentType?: string; lastTool?: string; summary?: string; backgrounded?: boolean }
): SubagentMap {
  const patch: Partial<ChatSubagent> = { status: normalizeStatus(event.status) };
  if (event.description) patch.description = event.description;
  if (event.subagentType) patch.subagentType = event.subagentType;
  if (event.lastTool) patch.lastTool = event.lastTool;
  if (event.summary) patch.summary = event.summary;
  if (event.backgrounded !== undefined) patch.backgrounded = event.backgrounded;
  return upsert(map ?? {}, event.toolId, patch);
}

/** When the whole turn ends, nothing it launched can still be running --
 * the bridge's process (and every subagent in it) is gone. */
export function settleSubagents(map: SubagentMap | undefined, outcome: "completed" | "stopped"): SubagentMap {
  // Same object back when nothing is running, so a caller settling on every
  // queue change doesn't re-render for nothing.
  if (!map || !Object.values(map).some((sub) => sub.status === "running")) return map ?? {};
  const out: SubagentMap = {};
  for (const [id, sub] of Object.entries(map ?? {})) {
    out[id] = sub.status === "running" ? { ...sub, status: outcome } : sub;
  }
  return out;
}
