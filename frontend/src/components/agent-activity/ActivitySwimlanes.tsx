import { useMemo, useRef, type KeyboardEvent, type MouseEvent } from "react";
import { ArrowUpRight, History, Loader2, Pause, Play, Radio, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { AgentAvatar } from "@/components/AgentAvatar";
import { Button } from "@/components/ui/button";
import type { ActivityAgent } from "@/hooks/useAgentActivity";
import type { TimelineBlock } from "@/hooks/useAgentActivityTimeline";
import type { ActivityTraceViewModel, TracePreset } from "@/hooks/useActivityTraceViewModel";
import { cn } from "@/lib/utils";
import { axisTicks, formatDuration, spanInWindow, timeToPercent } from "./swimlaneLayout";

const LANE_HEIGHT = 44;
const PRESETS: TracePreset[] = ["1h", "2h", "6h", "24h", "custom"];

/** Block colour: who the work was for -- same palette as the constellation. */
const BLOCK_TONE: Record<string, string> = {
  owner: "bg-emerald-500/70 border-emerald-600",
  human: "bg-sky-500/70 border-sky-600",
  system: "bg-slate-400/70 border-slate-500",
  agent: "bg-violet-500/70 border-violet-600",
};

function blockTone(block: TimelineBlock): string {
  if (block.status === "failed" || block.status === "abandoned") return "bg-destructive/60 border-destructive";
  return BLOCK_TONE[block.counterpart_kind ?? "system"] ?? BLOCK_TONE.system;
}

function useTimeFormat() {
  const { i18n } = useTranslation();
  return useMemo(() => {
    const short = new Intl.DateTimeFormat(i18n.language, { hour: "2-digit", minute: "2-digit" });
    const long = new Intl.DateTimeFormat(i18n.language, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const dated = new Intl.DateTimeFormat(i18n.language, {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    return { short: (ms: number) => short.format(ms), long: (ms: number) => long.format(ms), dated: (ms: number) => dated.format(ms) };
  }, [i18n.language]);
}

export function useBlockLabel() {
  const { t } = useTranslation("agentActivity");
  return (block: TimelineBlock, agentName: (id: string | null) => string | null) => {
    const channel = block.platform ? t(`live.platform.${block.platform}`, { defaultValue: block.platform }) : null;
    if (block.kind === "dispatch") {
      return t("trace.block.dispatch", { number: block.message_number ?? "?", from: agentName(block.counterpart_agent_id) ?? t(`live.counterpart.${block.counterpart_kind ?? "system"}`, { ref: "" }) });
    }
    if (block.kind === "workspace") return t("trace.block.workspace");
    const who =
      block.counterpart_kind === "human"
        ? block.counterpart_ref
          ? t("live.counterpart.human", { ref: block.counterpart_ref })
          : t("live.counterpart.humanNoRef")
        : t(`live.counterpart.${block.counterpart_kind ?? "system"}`);
    return channel ? t("trace.block.turn", { who, channel }) : who;
  };
}

/**
 * Lanes: one row per agent over the chosen window -- runtime and Workspace turns on top,
 * Messages dispatches on a thin track below, tool calls as ticks, messages between agents
 * as arrows across lanes. Clicking a lane moves the replay cursor there; clicking a block
 * opens its detail (with the link to its canonical record).
 */
export function ActivitySwimlanes({
  trace,
  agents,
  selectedAgentId,
  onClearAgent,
  onOpenRecord,
}: {
  trace: ActivityTraceViewModel;
  agents: ActivityAgent[];
  selectedAgentId: string | null;
  onClearAgent: () => void;
  onOpenRecord: (path: string) => void;
}) {
  const { t } = useTranslation("agentActivity");
  const time = useTimeFormat();
  const blockLabel = useBlockLabel();
  const trackRef = useRef<HTMLDivElement>(null);
  const agentsById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);
  const agentName = (id: string | null) => (id ? agentsById.get(id)?.name ?? null : null);

  const timeline = trace.timeline;
  const startMs = trace.windowStartMs;
  const endMs = trace.windowEndMs;
  const nowMs = Date.now();
  const lanes = useMemo(() => {
    const all = timeline?.lanes ?? [];
    return selectedAgentId ? all.filter((lane) => lane.agent_id === selectedAgentId) : all;
  }, [timeline, selectedAgentId]);
  const laneIndex = new Map(lanes.map((lane, index) => [lane.agent_id, index]));
  const messages = (timeline?.messages ?? []).filter(
    (message) => laneIndex.has(message.from_agent_id) && laneIndex.has(message.target_agent_id),
  );
  const ticks = startMs !== null && endMs !== null ? axisTicks(startMs, endMs) : [];

  const cursorFromPointer = (event: MouseEvent<HTMLDivElement>) => {
    if (startMs === null || endMs === null || !trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    trace.setCursor(startMs + Math.min(1, Math.max(0, ratio)) * (endMs - startMs));
  };
  const nudgeCursor = (event: KeyboardEvent<HTMLDivElement>) => {
    if (startMs === null || endMs === null) return;
    const step = event.shiftKey ? 5 * 60_000 : 60_000;
    const base = trace.cursor ?? Math.min(endMs, nowMs);
    if (event.key === "ArrowLeft") trace.setCursor(base - step);
    else if (event.key === "ArrowRight") trace.setCursor(base + step);
    else return;
    event.preventDefault();
  };

  const selected = trace.selectedBlock;

  return (
    <section aria-label={t("trace.title")} className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex flex-col gap-2 border-b border-border px-3 py-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <History className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <h2 className="text-sm font-medium">{t("trace.title")}</h2>
          {selectedAgentId && (
            <button
              type="button"
              onClick={onClearAgent}
              className="inline-flex min-h-7 items-center gap-1 rounded-md border border-border px-2 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {t("trace.onlyAgent", { name: agentName(selectedAgentId) ?? "?" })}
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
          {trace.isFetching && <Loader2 className="h-3.5 w-3.5 text-muted-foreground motion-safe:animate-spin" aria-hidden="true" />}
          <div role="radiogroup" aria-label={t("trace.window")} className="inline-flex flex-wrap rounded-md border border-border p-0.5">
            {PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                role="radio"
                aria-checked={trace.preset === preset}
                onClick={() => trace.setPreset(preset)}
                className={cn(
                  "min-h-7 rounded px-2 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  trace.preset === preset && "bg-muted text-foreground shadow-sm",
                )}
              >
                {t(`trace.preset.${preset}`)}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={trace.togglePlay} disabled={!timeline}>
            {trace.playing ? <Pause className="h-3.5 w-3.5" aria-hidden="true" /> : <Play className="h-3.5 w-3.5" aria-hidden="true" />}
            {trace.playing ? t("trace.pause") : t("trace.play")}
          </Button>
          <Button
            variant={trace.cursor === null ? "secondary" : "outline"}
            size="sm"
            className="h-8 gap-1.5 text-xs"
            onClick={trace.backToLive}
            disabled={trace.cursor === null}
          >
            <Radio className="h-3.5 w-3.5" aria-hidden="true" />
            {t("trace.live")}
          </Button>
        </div>
      </div>

      {trace.preset === "custom" && (
        <div className="flex flex-wrap items-end gap-3 border-b border-border px-3 py-2">
          {(["start", "end"] as const).map((edge) => (
            <label key={edge} className="grid gap-1 text-xs text-muted-foreground">
              {t(`trace.${edge}`)}
              <input
                type="datetime-local"
                value={trace.customRange[edge]}
                onChange={(event) => trace.setCustomRange({ ...trace.customRange, [edge]: event.target.value })}
                className="h-8 rounded-md border border-input bg-background px-2 text-base text-foreground md:text-xs"
              />
            </label>
          ))}
          {trace.rangeError && (
            <p role="alert" className="text-xs text-destructive">{t(`trace.rangeError.${trace.rangeError}`)}</p>
          )}
        </div>
      )}

      {trace.status === "error" ? (
        <p role="alert" className="px-3 py-8 text-center text-sm text-destructive">{t("states.requestFailed")}</p>
      ) : trace.status === "loading" || startMs === null || endMs === null ? (
        <p className="inline-flex w-full items-center justify-center gap-2 px-3 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          {t("states.loading")}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <div className="min-w-[44rem] px-3 pb-3 pt-2">
            <div className="flex">
              <div className="w-36 shrink-0" />
              <div className="relative h-5 flex-1 text-[10px] text-muted-foreground">
                {ticks.map((tick) => (
                  <span key={tick} className="absolute -translate-x-1/2 font-mono" style={{ left: `${timeToPercent(tick, startMs, endMs)}%` }}>
                    {time.short(tick)}
                  </span>
                ))}
              </div>
            </div>

            {lanes.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">{t("trace.empty")}</p>
            ) : (
              <div className="flex">
                <ul className="w-36 shrink-0" aria-hidden="true">
                  {lanes.map((lane) => {
                    const agent = agentsById.get(lane.agent_id);
                    return (
                      <li key={lane.agent_id} className="flex items-center gap-2 pr-2" style={{ height: LANE_HEIGHT }}>
                        <AgentAvatar name={agent?.name ?? "?"} avatarDataUrl={agent?.avatar_data_url} size="sm" />
                        <span className="truncate text-xs font-medium">{agent?.name ?? lane.agent_id.slice(0, 8)}</span>
                      </li>
                    );
                  })}
                </ul>
                <div
                  ref={trackRef}
                  role="slider"
                  tabIndex={0}
                  aria-label={t("trace.cursorLabel")}
                  aria-valuemin={startMs}
                  aria-valuemax={endMs}
                  aria-valuenow={trace.cursor ?? Math.min(endMs, nowMs)}
                  aria-valuetext={trace.cursor === null ? t("trace.live") : time.dated(trace.cursor)}
                  onClick={cursorFromPointer}
                  onKeyDown={nudgeCursor}
                  className="relative flex-1 cursor-crosshair focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  style={{ height: lanes.length * LANE_HEIGHT }}
                >
                  {ticks.map((tick) => (
                    <span key={tick} aria-hidden="true" className="absolute inset-y-0 w-px bg-border/60" style={{ left: `${timeToPercent(tick, startMs, endMs)}%` }} />
                  ))}
                  {lanes.map((lane, index) => (
                    <div
                      key={lane.agent_id}
                      className="absolute inset-x-0 border-b border-border/50"
                      style={{ top: index * LANE_HEIGHT, height: LANE_HEIGHT }}
                    >
                      {lane.blocks.map((block) => {
                        const span = spanInWindow(block.start, block.end, startMs, endMs, nowMs);
                        if (!span) return null;
                        const dispatch = block.kind === "dispatch";
                        const isSelected = selected?.block.key === block.key;
                        const duration = (block.end ? Date.parse(block.end) : Math.min(nowMs, endMs)) - Date.parse(block.start);
                        const label = `${blockLabel(block, agentName)} · ${time.long(Date.parse(block.start))} · ${formatDuration(duration)}`;
                        return (
                          <button
                            key={block.key}
                            type="button"
                            title={label}
                            aria-label={label}
                            onClick={(event) => {
                              event.stopPropagation();
                              trace.selectBlock(lane.agent_id, isSelected ? null : block);
                            }}
                            className={cn(
                              "absolute overflow-hidden rounded-sm border text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                              blockTone(block),
                              dispatch ? "bottom-1 h-2" : "top-1.5 h-6",
                              block.end === null && "motion-safe:animate-pulse",
                              span.clippedStart && "rounded-l-none border-l-0",
                              span.clippedEnd && "rounded-r-none border-r-0",
                              isSelected && "ring-2 ring-foreground",
                            )}
                            style={{ left: `${span.left}%`, width: `${span.width}%` }}
                          >
                            {!dispatch &&
                              block.tools.map((tool, toolIndex) => {
                                const toolSpan = spanInWindow(tool.start, tool.end, startMs, endMs, nowMs);
                                if (!toolSpan) return null;
                                const relative = ((toolSpan.left - span.left) / span.width) * 100;
                                return (
                                  <span
                                    key={`${tool.start}-${toolIndex}`}
                                    aria-hidden="true"
                                    className={cn(
                                      "absolute bottom-0 h-1.5 min-w-[2px] bg-foreground/70",
                                      tool.status === "error" && "bg-destructive",
                                    )}
                                    style={{ left: `${Math.max(0, relative)}%`, width: `${(toolSpan.width / span.width) * 100}%` }}
                                  />
                                );
                              })}
                          </button>
                        );
                      })}
                    </div>
                  ))}
                  {messages.map((message) => {
                    const from = laneIndex.get(message.from_agent_id)!;
                    const to = laneIndex.get(message.target_agent_id)!;
                    const top = Math.min(from, to) * LANE_HEIGHT + LANE_HEIGHT / 2;
                    const height = Math.abs(to - from) * LANE_HEIGHT;
                    const down = to > from;
                    const label = t("trace.message", {
                      number: message.number ?? "?",
                      from: agentName(message.from_agent_id) ?? "?",
                      to: agentName(message.target_agent_id) ?? "?",
                    });
                    return (
                      <button
                        key={message.id}
                        type="button"
                        title={message.subject ? `${label} — ${message.subject}` : label}
                        aria-label={label}
                        onClick={(event) => {
                          event.stopPropagation();
                          onOpenRecord(message.canonical_path);
                        }}
                        className="absolute w-2 -translate-x-1/2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        style={{ left: `${timeToPercent(Date.parse(message.at), startMs, endMs)}%`, top, height }}
                      >
                        <span aria-hidden="true" className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-violet-500" />
                        <span
                          aria-hidden="true"
                          className={cn(
                            "absolute left-1/2 h-0 w-0 -translate-x-1/2 border-x-4 border-x-transparent",
                            down ? "bottom-0 border-t-[6px] border-t-violet-500" : "top-0 border-b-[6px] border-b-violet-500",
                          )}
                        />
                      </button>
                    );
                  })}
                  {trace.cursor !== null && (
                    <span
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-y-0 w-0.5 bg-amber-500"
                      style={{ left: `${timeToPercent(trace.cursor, startMs, endMs)}%` }}
                    >
                      <span className="absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-amber-500 px-1 font-mono text-[10px] text-white">
                        {time.long(trace.cursor)}
                      </span>
                    </span>
                  )}
                </div>
              </div>
            )}

            <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground" aria-label={t("trace.legend")}>
              {(["owner", "human", "system", "agent"] as const).map((kind) => (
                <li key={kind} className="inline-flex items-center gap-1.5">
                  <span className={cn("h-2.5 w-4 rounded-sm border", BLOCK_TONE[kind])} aria-hidden="true" />
                  {t(`constellation.source.${kind}`)}
                </li>
              ))}
              <li className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-4 rounded-sm border border-destructive bg-destructive/60" aria-hidden="true" />
                {t("trace.legendFailed")}
              </li>
              <li className="inline-flex items-center gap-1.5">
                <span className="h-1.5 w-4 bg-foreground/70" aria-hidden="true" />
                {t("trace.legendTool")}
              </li>
              <li className="inline-flex items-center gap-1.5">
                <span className="h-2 w-4 rounded-sm bg-violet-500/70" aria-hidden="true" />
                {t("trace.legendDispatch")}
              </li>
            </ul>
          </div>
        </div>
      )}

      {selected && (
        <TraceBlockDetail
          block={selected.block}
          agentName={agentsById.get(selected.agentId)?.name ?? null}
          resolveAgent={agentName}
          onClose={() => trace.selectBlock(selected.agentId, null)}
          onReplay={() => trace.setCursor(Date.parse(selected.block.start))}
          onOpenRecord={onOpenRecord}
        />
      )}
    </section>
  );
}

function TraceBlockDetail({
  block,
  agentName,
  resolveAgent,
  onClose,
  onReplay,
  onOpenRecord,
}: {
  block: TimelineBlock;
  agentName: string | null;
  resolveAgent: (id: string | null) => string | null;
  onClose: () => void;
  onReplay: () => void;
  onOpenRecord: (path: string) => void;
}) {
  const { t } = useTranslation("agentActivity");
  const time = useTimeFormat();
  const blockLabel = useBlockLabel();
  const start = Date.parse(block.start);
  const end = block.end ? Date.parse(block.end) : null;
  const rows: [string, string | null][] = [
    [t("trace.detail.kind"), t(`trace.kind.${block.kind}`)],
    [t("trace.detail.start"), time.dated(start)],
    [t("trace.detail.end"), end !== null ? time.dated(end) : t("trace.detail.open")],
    [t("trace.detail.duration"), formatDuration((end ?? Date.now()) - start)],
    [t("trace.detail.status"), block.status ? t(`trace.status.${block.status}`, { defaultValue: block.status }) : null],
    [t("trace.detail.error"), block.error_type],
    [t("live.model"), block.model],
    [t("trace.detail.session"), block.session_id],
  ];
  return (
    <div className="border-t border-border px-3 py-3" role="region" aria-label={t("trace.detail.title")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{agentName}</p>
          <h3 className="break-words text-sm font-medium">{blockLabel(block, resolveAgent)}</h3>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onClose} aria-label={t("trace.detail.close")}>
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
      <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        {rows
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <div key={label} className="flex min-w-0 gap-2">
              <dt className="shrink-0 text-muted-foreground">{label}</dt>
              <dd className="min-w-0 break-all font-mono">{value}</dd>
            </div>
          ))}
      </dl>
      {block.tools.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium">{t("trace.detail.tools", { count: block.tools.length })}</p>
          <ol className="mt-1 space-y-0.5 text-xs">
            {block.tools.map((tool, index) => (
              <li key={`${tool.start}-${index}`} className="flex flex-wrap gap-x-2 font-mono">
                <span className="text-muted-foreground">{time.long(Date.parse(tool.start))}</span>
                <span className={cn(tool.status === "error" && "text-destructive")}>{tool.tool_name ?? "?"}</span>
                {tool.end && (
                  <span className="text-muted-foreground">
                    {formatDuration(tool.duration_ms ?? Date.parse(tool.end) - Date.parse(tool.start))}
                  </span>
                )}
                {tool.status === "error" && <span className="text-destructive">{t("trace.status.error")}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={onReplay}>
          <History className="h-3.5 w-3.5" aria-hidden="true" />
          {t("trace.replayFromHere")}
        </Button>
        {block.canonical_path && (
          <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs" onClick={() => onOpenRecord(block.canonical_path!)}>
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
            {t(block.kind === "dispatch" ? "trace.openMessage" : block.kind === "workspace" ? "trace.openWorkspace" : "trace.openAgent")}
          </Button>
        )}
      </div>
    </div>
  );
}
