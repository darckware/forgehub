import { useEffect, useMemo, useRef, useState } from "react";
import { useAgents } from "@/hooks/useAgent";
import { useDemands, type Demand } from "@/hooks/useDemands";
import { useForgeRouterActivity } from "@/hooks/useForgeRouterActivity";
import { useProjects } from "@/hooks/useProject";
import { NO_AGENT_ID } from "@/components/AgentInboxTree";

export interface ActivityNode {
  id: string;
  label: string;
  xPct: number;
  yPct: number;
  isSystem: boolean;
  isWorking: boolean;
  flash: "completed" | "failed" | null;
  /** What the agent is actually doing right now, straight from the demand
   * that's `running` for it -- null while idle. Never inferred/guessed: a
   * project name only shows when the dispatched message itself carries
   * `project_id`, a path only when `working_path` (or the resolved
   * project's `working_directory_path`) is set server-side. */
  currentProjectName: string | null;
  currentPath: string | null;
  /** Set when this agent has a fresh (last ~10s) ForgeRouter route_events
   * row and no richer Demand-driven project/path to show instead --
   * ForgeRouter doesn't log which tool a call used, only the routing
   * capability tier (text/code/tool_call/vision), so this is honestly
   * labeled as that, never guessed as "searching the web" or similar. */
  activityLabel: string | null;
  /** Short-lived speech-bubble text: the task subject while a message is
   * flying toward this agent, or a preview of its real dispatch_result once
   * resolved. Always real message content, never a fabricated status. */
  bubble: { text: string; tone: "incoming" | "completed" | "failed" } | null;
}

export interface FlightPacket {
  key: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
  status: "dispatched" | "running";
  subject: string;
}

export interface ActivityTask {
  id: string;
  number: number;
  subject: string;
  fromLabel: string;
  toLabel: string;
  status: Demand["dispatch_status"];
  updatedAt: string;
  resultPreview: string | null;
  projectName: string | null;
  workingPath: string | null;
}

const FLASH_MS = 1600;
const PACKET_MS = 1100;
const BUBBLE_MS = 3200;
const RING_RADIUS_PCT = 38;
const ACTIVE_TASK_STATUSES = new Set<Demand["dispatch_status"]>(["dispatched", "running", "completed", "failed"]);

/** All participants (including the NO_AGENT_ID "System" row) go on the ring
 * -- the center is reserved for the always-on ServerCore decoration
 * (AgentActivityStage.tsx), so a message-participant node placed there too
 * would overlap it. */
function layoutRing(ids: string[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  ids.forEach((id, i) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(ids.length, 1);
    positions.set(id, {
      x: 50 + RING_RADIUS_PCT * Math.cos(angle),
      y: 50 + RING_RADIUS_PCT * Math.sin(angle) * 0.82,
    });
  });
  return positions;
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** Drives the animated 2D "data center" board -- agents as analyst
 * workstations around a central server/DB core. Positions are a plain
 * derived layout; packets/flashes/bubbles are transient state seeded by
 * diffing each poll's `dispatch_status` against the previous one. The first
 * poll after mount only seeds the baseline (nothing "just changed" relative
 * to a page that hadn't loaded yet), so it must not fire a burst of
 * animations for every already-in-flight message on load. Every signal --
 * who's working, on which project/folder, the bubble text -- comes straight
 * from real Demand/Project rows; nothing here is simulated. */
const LLM_ACTIVITY_FRESH_MS = 10_000;

export function useAgentActivityViewModel() {
  const { data: demands = [] } = useDemands();
  const { data: agents = [] } = useAgents();
  const { data: projects = [] } = useProjects();
  const { data: forgeRouterActivity = [] } = useForgeRouterActivity();

  const agentNames = useMemo(() => new Map((agents ?? []).map((a) => [a.id, a.name])), [agents]);
  const nameToAgentId = useMemo(
    () => new Map((agents ?? []).map((a) => [a.name.toLowerCase(), a.id])),
    [agents]
  );
  const projectNames = useMemo(() => new Map((projects ?? []).map((p) => [p.id, p.name])), [projects]);
  const projectPaths = useMemo(
    () => new Map((projects ?? []).map((p) => [p.id, p.working_directory_path ?? null])),
    [projects]
  );

  /** Most recent fresh (< LLM_ACTIVITY_FRESH_MS old) route_events row per
   * resolved agent id -- agents ForgeRouter routes for but that never
   * showed up as a Demand participant (a cron run, a live chat/skill
   * session) still get a node this way, not just Messages-dispatched
   * agents. */
  const llmActiveByAgent = useMemo(() => {
    const now = Date.now();
    const map = new Map<string, { capability: string; preview: string | null; createdAt: number }>();
    for (const e of forgeRouterActivity) {
      if (!e.agent_name) continue;
      const agentId = nameToAgentId.get(e.agent_name.toLowerCase());
      if (!agentId) continue;
      const createdAt = new Date(e.created_at).getTime();
      if (now - createdAt > LLM_ACTIVITY_FRESH_MS) continue;
      const existing = map.get(agentId);
      if (!existing || createdAt > existing.createdAt) {
        map.set(agentId, { capability: e.required_capability, preview: e.prompt_preview, createdAt });
      }
    }
    return map;
  }, [forgeRouterActivity, nameToAgentId]);

  const participantIds = useMemo(() => {
    const ids = new Set<string>();
    for (const d of demands) {
      const from = d.from_agent_id ?? NO_AGENT_ID;
      const to = d.target_agent_id ?? NO_AGENT_ID;
      if (from === NO_AGENT_ID && to === NO_AGENT_ID) continue;
      ids.add(from);
      ids.add(to);
    }
    for (const id of llmActiveByAgent.keys()) ids.add(id);
    return [...ids].sort();
  }, [demands, llmActiveByAgent]);

  const participantKey = participantIds.join(",");
  const positions = useMemo(() => layoutRing(participantIds), [participantKey]);

  /** Latest `running` demand targeting each agent, if any -- source of the
   * workstation's "currently processing" readout (project/path). */
  const runningByAgent = useMemo(() => {
    const map = new Map<string, Demand>();
    for (const d of demands) {
      if (d.dispatch_status !== "running") continue;
      const agentId = d.target_agent_id ?? NO_AGENT_ID;
      const existing = map.get(agentId);
      if (!existing || d.updated_at > existing.updated_at) map.set(agentId, d);
    }
    return map;
  }, [demands]);

  const [flashes, setFlashes] = useState<Map<string, "completed" | "failed">>(new Map());
  const [bubbles, setBubbles] = useState<Map<string, { text: string; tone: "incoming" | "completed" | "failed" }>>(
    new Map()
  );
  const [packets, setPackets] = useState<FlightPacket[]>([]);
  const prevStatusRef = useRef<Map<string, Demand["dispatch_status"]> | null>(null);

  useEffect(() => {
    const prev = prevStatusRef.current;
    const next = new Map<string, Demand["dispatch_status"]>();
    const seededPackets: FlightPacket[] = [];
    const seededFlashes: Array<[string, "completed" | "failed"]> = [];
    const seededBubbles: Array<[string, { text: string; tone: "incoming" | "completed" | "failed" }]> = [];

    for (const d of demands) {
      const cur = d.dispatch_status;
      next.set(d.id, cur);
      if (prev === null) continue; // page just mounted: seed baseline only, no animation burst
      const before = prev.get(d.id); // undefined if this demand appeared since the last poll
      if (before === cur) continue;

      // A demand id absent from the previous poll is a message that came
      // into existence between polls -- indistinguishable from (and treated
      // the same as) a null -> dispatched transition, so a dispatch fired
      // from outside this tab (script, another agent, another browser tab)
      // still shows its packet the first time this tab sees it.
      if ((cur === "dispatched" || cur === "running") && (before == null || before === undefined)) {
        const from = positions.get(d.from_agent_id ?? NO_AGENT_ID);
        const to = positions.get(d.target_agent_id ?? NO_AGENT_ID);
        if (from && to) {
          seededPackets.push({ key: `${d.id}-${cur}`, from, to, status: cur, subject: d.subject });
        }
        const toId = d.target_agent_id ?? NO_AGENT_ID;
        seededBubbles.push([toId, { text: truncate(d.subject, 64), tone: "incoming" }]);
      }
      if (cur === "completed" || cur === "failed") {
        const toId = d.target_agent_id ?? NO_AGENT_ID;
        seededFlashes.push([toId, cur]);
        const preview = d.dispatch_result ? truncate(d.dispatch_result.replace(/\s+/g, " ").trim(), 90) : null;
        if (preview) seededBubbles.push([toId, { text: preview, tone: cur }]);
      }
    }
    prevStatusRef.current = next;

    if (seededPackets.length) {
      setPackets((p) => [...p, ...seededPackets]);
      seededPackets.forEach((pkt) => {
        setTimeout(() => setPackets((p) => p.filter((x) => x.key !== pkt.key)), PACKET_MS);
      });
    }
    if (seededFlashes.length) {
      setFlashes((f) => {
        const m = new Map(f);
        seededFlashes.forEach(([id, status]) => m.set(id, status));
        return m;
      });
      seededFlashes.forEach(([id]) => {
        setTimeout(() => setFlashes((f) => {
          const m = new Map(f);
          m.delete(id);
          return m;
        }), FLASH_MS);
      });
    }
    if (seededBubbles.length) {
      setBubbles((b) => {
        const m = new Map(b);
        seededBubbles.forEach(([id, bubble]) => m.set(id, bubble));
        return m;
      });
      seededBubbles.forEach(([id, bubble]) => {
        setTimeout(() => setBubbles((b) => {
          const cur = b.get(id);
          if (!cur || cur !== bubble) return b; // a newer bubble already replaced it
          const m = new Map(b);
          m.delete(id);
          return m;
        }), BUBBLE_MS);
      });
    }
  }, [demands, positions]);

  const nodes: ActivityNode[] = participantIds.map((id) => {
    const p = positions.get(id) ?? { x: 50, y: 50 };
    const running = runningByAgent.get(id);
    const projectName = running?.project_id ? projectNames.get(running.project_id) ?? null : null;
    const currentPath = running
      ? running.working_path ?? (running.project_id ? projectPaths.get(running.project_id) ?? null : null)
      : null;
    const llmActivity = llmActiveByAgent.get(id);
    const activityLabel =
      !projectName && llmActivity
        ? truncate(
            llmActivity.preview
              ? `${llmActivity.capability}: ${llmActivity.preview.replace(/\s+/g, " ").trim()}`
              : llmActivity.capability,
            60
          )
        : null;
    return {
      id,
      label: id === NO_AGENT_ID ? "System" : agentNames.get(id) ?? id,
      xPct: p.x,
      yPct: p.y,
      isSystem: id === NO_AGENT_ID,
      isWorking: runningByAgent.has(id) || llmActiveByAgent.has(id),
      flash: flashes.get(id) ?? null,
      currentProjectName: projectName,
      currentPath,
      activityLabel,
      bubble: bubbles.get(id) ?? null,
    };
  });

  const tasks: ActivityTask[] = demands
    .filter((d) => d.dispatch_status && ACTIVE_TASK_STATUSES.has(d.dispatch_status))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 40)
    .map((d) => ({
      id: d.id,
      number: d.number,
      subject: d.subject,
      fromLabel: d.from_agent_id ? agentNames.get(d.from_agent_id) ?? d.from_agent : d.from_agent,
      toLabel: d.target_agent_id ? agentNames.get(d.target_agent_id) ?? d.target_agent_id : "System",
      status: d.dispatch_status,
      updatedAt: d.updated_at,
      resultPreview: d.dispatch_result ? d.dispatch_result.slice(0, 280) : null,
      projectName: d.project_id ? projectNames.get(d.project_id) ?? null : null,
      workingPath: d.working_path ?? (d.project_id ? projectPaths.get(d.project_id) ?? null : null),
    }));

  const runningCount = tasks.filter((t) => t.status === "running" || t.status === "dispatched").length;

  return {
    nodes,
    packets,
    tasks,
    runningCount,
    anyRunning: runningByAgent.size > 0 || llmActiveByAgent.size > 0,
    isEmpty: participantIds.length === 0,
  };
}
