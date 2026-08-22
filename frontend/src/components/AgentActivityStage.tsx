import { AnimatePresence, motion } from "framer-motion";
import { Database, Folder, MonitorSmartphone, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ActivityNode, FlightPacket } from "@/hooks/useAgentActivityViewModel";

const PACKET_COLOR: Record<FlightPacket["status"], string> = {
  dispatched: "bg-sky-500",
  running: "bg-amber-500",
};

const AVATAR_PALETTE = [
  "bg-violet-500", "bg-sky-500", "bg-emerald-500", "bg-amber-500",
  "bg-rose-500", "bg-cyan-500", "bg-fuchsia-500", "bg-lime-600",
];

function paletteFor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

function initials(label: string): string {
  return label.slice(0, 2).toUpperCase();
}

/** The animated 2D "CPD" (data center) board: a server/database core sits
 * in the middle of the room, agents are analyst workstations arranged
 * around it, and transient packets fly between them when a message
 * dispatches. Every signal is seeded by real Demand rows from
 * useAgentActivityViewModel -- the project name/working folder under a
 * working agent, the speech-bubble text, all come straight from the actual
 * message/project data, nothing here is a simulated loop. `anyRunning`
 * only drives the decorative server-core blink (that pillar represents the
 * always-on Postgres/backend infra, not a message participant). */
export function AgentActivityStage({
  nodes,
  packets,
  anyRunning,
}: {
  nodes: ActivityNode[];
  packets: FlightPacket[];
  anyRunning: boolean;
}) {
  return (
    <div className="relative aspect-[16/10] w-full overflow-hidden rounded-xl border border-border/60 bg-[radial-gradient(circle_at_50%_45%,theme(colors.muted.DEFAULT/40%),transparent_70%)]">
      <div
        className="absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "linear-gradient(to right, currentColor 1px, transparent 1px), linear-gradient(to bottom, currentColor 1px, transparent 1px)",
          backgroundSize: "28px 28px",
        }}
      />

      <ServerCore active={anyRunning} />

      {nodes.map((node) => (
        <div
          key={node.id}
          className="absolute -translate-x-1/2 -translate-y-1/2"
          style={{ left: `${node.xPct}%`, top: `${node.yPct}%` }}
        >
          <div className="relative flex flex-col items-center gap-1.5">
            <AnimatePresence>
              {node.bubble && (
                <motion.div
                  className={cn(
                    "absolute bottom-full mb-2 w-44 -translate-x-1/2 rounded-lg border px-2.5 py-1.5 text-[11px] leading-snug shadow-md",
                    node.bubble.tone === "incoming" && "border-sky-400/60 bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100",
                    node.bubble.tone === "completed" && "border-emerald-400/60 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100",
                    node.bubble.tone === "failed" && "border-red-400/60 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-100"
                  )}
                  style={{ left: "50%" }}
                  initial={{ opacity: 0, y: 6, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.25 }}
                >
                  {node.bubble.text}
                </motion.div>
              )}
            </AnimatePresence>

            {node.isWorking && (
              <motion.span
                className="absolute inset-0 -m-1.5 rounded-full bg-amber-400/40"
                animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
                transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
              />
            )}
            <AnimatePresence>
              {node.flash && (
                <motion.span
                  className={cn(
                    "absolute inset-0 -m-1.5 rounded-full",
                    node.flash === "completed" ? "bg-emerald-400/60" : "bg-red-500/60"
                  )}
                  initial={{ scale: 0.7, opacity: 0.9 }}
                  animate={{ scale: 2.4, opacity: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 1.1, ease: "easeOut" }}
                />
              )}
            </AnimatePresence>

            <motion.div
              animate={node.isWorking ? { scale: [1, 1.08, 1] } : { scale: 1 }}
              transition={node.isWorking ? { repeat: Infinity, duration: 1.2 } : undefined}
              className={cn(
                "relative flex h-12 w-12 items-center justify-center rounded-full border-2 text-sm font-bold text-white shadow-md",
                node.isSystem ? "border-primary bg-slate-600" : cn("border-white/40", paletteFor(node.id)),
                node.isWorking && "ring-2 ring-amber-400"
              )}
              title={node.label}
            >
              {node.isSystem ? <Server className="h-5 w-5" /> : initials(node.label)}
            </motion.div>

            <span className="max-w-[7rem] truncate rounded bg-background/80 px-1.5 py-0.5 text-[11px] font-medium text-foreground shadow-sm">
              {node.label}
            </span>

            {node.isWorking ? (
              <div className="flex max-w-[9rem] flex-col items-center gap-0.5 text-center">
                <span className="flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400">
                  <MonitorSmartphone className="h-3 w-3 animate-pulse" />
                  {node.currentProjectName ?? node.activityLabel ?? "processando"}
                </span>
                {node.currentPath && (
                  <span className="flex max-w-full items-center gap-1 truncate rounded bg-background/70 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                    <Folder className="h-2.5 w-2.5 shrink-0" />
                    <span className="truncate">{node.currentPath}</span>
                  </span>
                )}
              </div>
            ) : null}
          </div>
        </div>
      ))}

      <PacketLayer packets={packets} />
    </div>
  );
}

function ServerCore({ active }: { active: boolean }) {
  return (
    <div
      className="pointer-events-none absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1"
      aria-hidden
    >
      <div className="relative flex h-14 w-14 items-center justify-center rounded-md border-2 border-slate-500 bg-slate-800 text-slate-200 shadow-lg">
        <Database className="h-6 w-6" />
        <span
          className={cn(
            "absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full",
            active ? "animate-pulse bg-emerald-400" : "bg-slate-500"
          )}
        />
      </div>
      <span className="rounded bg-background/80 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground shadow-sm">
        company_postgres
      </span>
    </div>
  );
}

function PacketLayer({ packets }: { packets: FlightPacket[] }) {
  return (
    <AnimatePresence>
      {packets.map((packet) => (
        <motion.div
          key={packet.key}
          className={cn("pointer-events-none absolute z-10 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full shadow", PACKET_COLOR[packet.status])}
          initial={{ left: `${packet.from.x}%`, top: `${packet.from.y}%`, opacity: 0, scale: 0.4 }}
          animate={{ left: `${packet.to.x}%`, top: `${packet.to.y}%`, opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.4 }}
          transition={{ duration: 1.05, ease: "easeInOut" }}
          title={packet.subject}
        />
      ))}
    </AnimatePresence>
  );
}

export function AgentActivityLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full bg-sky-500" /> Mensagem despachada
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-amber-500" /> Agente executando
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> Concluído
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full bg-red-500" /> Falhou
      </span>
      <span className="flex items-center gap-1.5">
        <Database className="h-3.5 w-3.5" /> Servidor/Banco de dados
      </span>
    </div>
  );
}
