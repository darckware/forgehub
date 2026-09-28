import { useState } from "react";
import { useReducedMotion } from "framer-motion";
import {
  ArrowUpRight,
  Bot,
  Clock,
  Cpu,
  Mail,
  MessageCircle,
  Monitor,
  Send,
  SquareTerminal,
  User,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { AgentAvatar } from "@/components/AgentAvatar";
import type {
  ActivityAgent,
  ActivityLink,
  ActivityMessageEdge,
  AgentLiveSnapshotItem,
} from "@/hooks/useAgentActivity";
import { cn } from "@/lib/utils";
import {
  AGENT_RING,
  CENTER,
  OUTER_POINTS,
  VIEWBOX,
  layoutAgents,
  linkOpacity,
  linkPath,
  toPercent,
  type OuterNodeKind,
} from "./constellationLayout";
import { formatElapsed, LIVE_AVATAR_RING, describeLiveState, isLiveStateActive } from "./liveState";

const INFRA_STORAGE_KEY = "forgehub:agent-activity:infra:v1";

const CHANNEL_ICON: Record<string, LucideIcon> = {
  telegram: Send,
  whatsapp: MessageCircle,
  cli: SquareTerminal,
  tui: SquareTerminal,
  acp: SquareTerminal,
  workspace: Monitor,
  cron: Clock,
  messages: Mail,
  kanban: Workflow,
  subagent: Bot,
};

const OUTER_ICON: Record<OuterNodeKind, LucideIcon> = {
  owner: User,
  human: Users,
  system: Workflow,
  forgerouter: Cpu,
};

/** Stroke colour per interaction: you, outside contacts, the system, agent-to-agent. */
const LINK_STROKE: Record<string, string> = {
  owner: "stroke-emerald-500",
  human: "stroke-sky-500",
  system: "stroke-slate-400",
  agent: "stroke-violet-500",
  forgerouter: "stroke-amber-500",
};
const LINK_DOT: Record<string, string> = {
  owner: "bg-emerald-500",
  human: "bg-sky-500",
  system: "bg-slate-400",
  agent: "bg-violet-500",
  forgerouter: "bg-amber-500",
};
const PARTICLE_FILL: Record<string, string> = {
  owner: "fill-emerald-400",
  human: "fill-sky-400",
  system: "fill-slate-300",
  agent: "fill-violet-400",
  forgerouter: "fill-amber-400",
};

function readInfra(): boolean {
  try {
    return window.localStorage.getItem(INFRA_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Live constellation of the agents: who is talking to whom right now.
 *
 * Only real interactions are drawn (snapshot `links`, last 5 min): an active one carries a
 * particle travelling source -> agent, and fades to a faint trace once it ends. With no
 * activity the picture is deliberately calm -- nodes, no lines. Infrastructure (ForgeRouter)
 * is an opt-in layer, tied to the agents that used an LLM in the last hour.
 */
export function AgentConstellation({
  agents,
  snapshotByAgent,
  links,
  messageEdges,
  selectedAgentId,
  onSelectAgent,
  now,
}: {
  agents: ActivityAgent[];
  snapshotByAgent: Map<string, AgentLiveSnapshotItem>;
  links: ActivityLink[];
  messageEdges: ActivityMessageEdge[];
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string) => void;
  now: number;
}) {
  const { t } = useTranslation("agentActivity");
  const reduceMotion = useReducedMotion();
  const [showInfra, setShowInfra] = useState(readInfra);
  const positions = layoutAgents(agents);
  const agentById = new Map(agents.map((agent) => [agent.id, agent]));

  const toggleInfra = () => {
    const next = !showInfra;
    try {
      window.localStorage.setItem(INFRA_STORAGE_KEY, next ? "1" : "0");
    } catch {
      // storage blocked: the choice just isn't remembered
    }
    setShowInfra(next);
  };

  const drawn = links
    .map((link) => {
      const to = positions.get(link.target_agent_id);
      const from =
        link.source_type === "agent"
          ? link.source_agent_id
            ? positions.get(link.source_agent_id)
            : undefined
          : OUTER_POINTS[link.source_type];
      if (!from || !to) return null;
      return { link, ...linkPath(from, to, link.source_type === "agent"), opacity: linkOpacity(link.active, link.last_at, now) };
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);

  const infraLinks = showInfra
    ? agents
        .map((agent) => ({ agent, tokens: snapshotByAgent.get(agent.id)?.tokens_last_hour ?? 0 }))
        .filter(({ tokens }) => tokens > 0)
        .map(({ agent, tokens }) => {
          const from = positions.get(agent.id)!;
          return { agent, tokens, ...linkPath(from, OUTER_POINTS.forgerouter, false) };
        })
    : [];
  const maxTokens = Math.max(1, ...infraLinks.map((item) => item.tokens));

  const outerKinds: OuterNodeKind[] = showInfra ? ["owner", "human", "system", "forgerouter"] : ["owner", "human", "system"];
  const outerActive = new Set<string>(drawn.filter((item) => item.link.active).map((item) => item.link.source_type));
  const outerUsed = new Set<string>(drawn.map((item) => item.link.source_type));

  return (
    <section
      role="region"
      aria-label={t("constellation.title")}
      className="overflow-hidden rounded-lg border border-border bg-card"
      data-testid="agent-constellation"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-3 py-2">
        <h2 className="text-sm font-medium">{t("constellation.title")}</h2>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground" aria-label={t("constellation.legend")}>
          {(["owner", "human", "system", "agent"] as const).map((kind) => (
            <li key={kind} className="inline-flex items-center gap-1">
              <span className={cn("h-0.5 w-4 rounded", LINK_DOT[kind])} aria-hidden="true" />
              {t(`constellation.source.${kind}`)}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={toggleInfra}
          aria-pressed={showInfra}
          className={cn(
            "ml-auto inline-flex min-h-7 cursor-pointer items-center gap-1.5 rounded-md border border-border px-2 text-[11px] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            showInfra && "bg-muted text-foreground",
          )}
        >
          <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
          {t("constellation.showInfra")}
        </button>
      </div>

      {agents.length === 0 ? (
        <p className="px-4 py-16 text-center text-sm text-muted-foreground">{t("states.empty")}</p>
      ) : (
        <div className="relative w-full" style={{ aspectRatio: `${VIEWBOX.width} / ${VIEWBOX.height}` }}>
          <svg
            viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`}
            className="absolute inset-0 h-full w-full"
            aria-hidden="true"
          >
            <ellipse cx={CENTER.x} cy={CENTER.y} rx={AGENT_RING.rx} ry={AGENT_RING.ry} className="fill-none stroke-border" strokeDasharray="2 6" />
            {infraLinks.map((item) => (
              <path
                key={`infra:${item.agent.id}`}
                d={item.d}
                className="fill-none stroke-amber-500/50"
                strokeWidth={1 + (item.tokens / maxTokens) * 4}
                strokeDasharray="4 6"
              />
            ))}
            {drawn.map(({ link, d, opacity }) => (
              <g key={link.key} style={{ opacity }}>
                <path
                  d={d}
                  className={cn("fill-none transition-[stroke-width]", LINK_STROKE[link.source_type])}
                  strokeWidth={link.active ? 2.5 : 1.25}
                  strokeLinecap="round"
                  strokeDasharray={link.active ? undefined : "3 5"}
                />
                {link.active && !reduceMotion && (
                  <>
                    <circle r={5} className={PARTICLE_FILL[link.source_type]} data-testid="constellation-particle">
                      <animateMotion dur="1.8s" repeatCount="indefinite" path={d} />
                    </circle>
                    <circle r={3} className={PARTICLE_FILL[link.source_type]} opacity={0.6}>
                      <animateMotion dur="1.8s" begin="0.9s" repeatCount="indefinite" path={d} />
                    </circle>
                  </>
                )}
              </g>
            ))}
          </svg>

          {drawn
            .filter(({ link }) => link.channel && CHANNEL_ICON[link.channel])
            .map(({ link, badge, opacity }) => {
              const Icon = CHANNEL_ICON[link.channel!];
              return (
                <span
                  key={`badge:${link.key}`}
                  className="pointer-events-none absolute flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm"
                  style={{ ...toPercent(badge), opacity }}
                  aria-hidden="true"
                >
                  <Icon className="h-3 w-3" />
                </span>
              );
            })}

          {outerKinds.map((kind) => {
            const Icon = OUTER_ICON[kind];
            const active = outerActive.has(kind);
            const used = kind === "forgerouter" ? infraLinks.length > 0 : outerUsed.has(kind);
            return (
              <div
                key={kind}
                className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-0.5"
                style={toPercent(OUTER_POINTS[kind])}
              >
                <span
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full border bg-card md:h-10 md:w-10",
                    used ? "border-foreground/30 text-foreground" : "border-border text-muted-foreground/60",
                    active && "motion-safe:animate-pulse",
                  )}
                >
                  <Icon className="h-4 w-4 md:h-5 md:w-5" aria-hidden="true" />
                </span>
                <span className={cn("hidden text-[10px] sm:block", used ? "text-foreground" : "text-muted-foreground")}>
                  {t(`constellation.source.${kind}`)}
                </span>
              </div>
            );
          })}

          {agents.map((agent) => {
            const point = positions.get(agent.id)!;
            const live = agent.live ?? null;
            const active = isLiveStateActive(live);
            const selected = agent.id === selectedAgentId;
            const text = live ? describeLiveState(live, t, now) : null;
            return (
              <button
                key={agent.id}
                type="button"
                onClick={() => onSelectAgent(agent.id)}
                aria-pressed={selected}
                aria-label={`${agent.name}${text ? ` — ${text.headline}` : ""}`}
                className={cn(
                  "group absolute flex w-20 -translate-x-1/2 -translate-y-1/2 cursor-pointer flex-col items-center gap-0.5 rounded-md p-1 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:w-24",
                  selected && "bg-primary/10",
                  !live && "opacity-60",
                )}
                style={toPercent(point)}
              >
                <AgentAvatar
                  name={agent.name}
                  avatarDataUrl={agent.avatar_data_url}
                  size="sm"
                  className={cn(
                    "h-7 w-7 transition-transform group-hover:scale-110 md:h-10 md:w-10",
                    live && LIVE_AVATAR_RING[live.state],
                    active && "motion-safe:animate-pulse",
                  )}
                />
                <span className="hidden max-w-full truncate text-[11px] font-semibold sm:block">{agent.name}</span>
                <span className="hidden max-w-full truncate text-[9px] text-muted-foreground md:block">
                  {text?.headline ?? t("live.noSignal")}
                </span>
              </button>
            );
          })}

          {drawn.length === 0 && (
            <p className="pointer-events-none absolute inset-x-0 bottom-2 text-center text-[11px] text-muted-foreground">
              {t("constellation.calm")}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 border-t border-border px-3 py-2.5 md:grid-cols-2">
        <div>
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {t("constellation.recent")}
          </p>
          {drawn.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("constellation.noInteractions")}</p>
          ) : (
            <ul className="space-y-1 text-[11px]" aria-label={t("constellation.recent")}>
              {drawn.slice(0, 8).map(({ link }) => {
                const target = agentById.get(link.target_agent_id)?.name ?? t("topology.unknownAgent");
                const source =
                  link.source_type === "agent"
                    ? agentById.get(link.source_agent_id ?? "")?.name ?? t("topology.unknownAgent")
                    : t(`constellation.source.${link.source_type}`);
                const channel = link.channel ? t(`live.platform.${link.channel}`, { defaultValue: link.channel }) : null;
                return (
                  <li key={link.key} className="flex items-center gap-2">
                    <span
                      className={cn(
                        "h-1.5 w-1.5 shrink-0 rounded-full",
                        link.active ? LINK_DOT[link.source_type] : "bg-muted-foreground/30",
                      )}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 truncate">
                      {source} → {target}
                      {channel ? ` · ${channel}` : ""}
                      {link.message_number ? ` · #${link.message_number}` : ""}
                    </span>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">
                      {link.active ? t("constellation.now") : formatElapsed(link.last_at, now)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div>
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {t("topology.messageRecords")}
          </p>
          {messageEdges.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("topology.noMessages")}</p>
          ) : (
            <ul className="flex flex-wrap gap-2" aria-label={t("topology.messageRecords")}>
              {messageEdges.map((edge) => (
                <li key={edge.message_id}>
                  <a
                    href={edge.canonical_path}
                    aria-label={t("topology.openMessage", {
                      from: edge.from_agent_name ?? t("topology.unknownAgent"),
                      to: edge.target_agent_name ?? t("topology.unknownAgent"),
                      subject: edge.subject ?? t("topology.noSubject"),
                    })}
                    className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-border px-2 py-1 font-mono text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {edge.from_agent_name ?? "—"} → {edge.target_agent_name ?? "—"}
                    <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
