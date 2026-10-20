import type { WorkItemDetail, WorkItemStage } from "@/hooks/useClientOps";

/**
 * One chronological story for a client ticket/demand (2026-10-05, Marcelo: the
 * detail showed history, hours and e-mails as three separate blocks and raw
 * notes like "status aberto → em_andamento").
 *
 * Built from what Darckware already returns -- its notes, the time entries and
 * the e-mail queue -- so there is no second record to drift. Notes Darckware
 * writes *about* an hour entry or an e-mail are dropped: the entry/e-mail
 * itself is already in the timeline, richer.
 */
export type TimelineEntry =
  | { kind: "opened"; at: string; source?: string | null }
  | { kind: "status"; at: string; actor: string; from?: WorkItemStage; to: WorkItemStage; note?: string }
  | { kind: "hours"; at: string; actor: string; hours: number; description: string; start?: string; end?: string }
  | { kind: "email"; at: string; event: "queued" | "sent" | "rejected" | "failed" | "cancelled"; subject: string }
  | { kind: "client"; at: string; actor: string; text: string }
  | { kind: "note"; at: string; actor: string; text: string };

/** Darckware's two status vocabularies -> the stage the screen shows. */
const RAW_TO_STAGE: Record<string, WorkItemStage> = {
  aberto: "novo",
  aberta: "novo",
  reaberta: "novo",
  em_andamento: "em_andamento",
  em_atendimento: "em_andamento",
  encaminhada: "em_andamento",
  aguardando_cliente: "aguardando_cliente",
  resolvido: "resolvido",
  resolvida: "resolvido",
  fechado: "fechado",
  fechada: "fechado",
  arquivada: "fechado",
};

/** "forgehub:marcelodarck" -> "marcelodarck"; "cliente:Ana" -> "Ana". */
export function displayActor(actor: string): string {
  return actor.replace(/^(forgehub|cliente|admin):/, "");
}

// Ticket notes: "status aberto → em_andamento"; demand notes: "status→resolvida".
const TICKET_STATUS = /status (\w+) → (\w+)/;
const DEMAND_STATUS = /status→(\w+)/;
/** Notes that only restate an hour entry or an e-mail already in the timeline. */
const DUPLICATE_NOTE = /^(E-mail enviado ao cliente|E-mail '.*' enviado para|[\d.,]+ h apontadas:)/;
const DUPLICATE_EVENT_TYPES = new Set(["horas_apontadas", "email_enviado", "email_aguardando_aprovacao"]);

export function buildTimeline(detail: WorkItemDetail): TimelineEntry[] {
  const entries: TimelineEntry[] = [];
  if (detail.created_at) entries.push({ kind: "opened", at: detail.created_at, source: detail.source });

  for (const ev of detail.timeline) {
    const note = (ev.note ?? "").trim();
    if (DUPLICATE_EVENT_TYPES.has(ev.type) || DUPLICATE_NOTE.test(note)) continue;
    if (/^Chamado aberto por /.test(note)) continue; // the "opened" entry already says it
    const actor = displayActor(ev.actor);
    if (ev.type === "cliente" || ev.type === "mensagem_cliente") {
      entries.push({ kind: "client", at: ev.at, actor, text: note });
      continue;
    }
    const ticketMatch = note.match(TICKET_STATUS);
    const demandMatch = note.match(DEMAND_STATUS);
    if (ticketMatch && RAW_TO_STAGE[ticketMatch[2]]) {
      // Anything written after the status line (a reason, the resolution) stays with it.
      const rest = note.replace(TICKET_STATUS, "").replace(/^[;\s]+/, "").trim();
      entries.push({
        kind: "status",
        at: ev.at,
        actor,
        from: RAW_TO_STAGE[ticketMatch[1]],
        to: RAW_TO_STAGE[ticketMatch[2]],
        note: rest || undefined,
      });
      continue;
    }
    if (demandMatch && RAW_TO_STAGE[demandMatch[1]]) {
      entries.push({ kind: "status", at: ev.at, actor, to: RAW_TO_STAGE[demandMatch[1]] });
      continue;
    }
    if (note) entries.push({ kind: "note", at: ev.at, actor, text: note });
  }

  for (const e of detail.time_entries) {
    entries.push({
      kind: "hours",
      at: e.start_time ?? detail.updated_at ?? "",
      actor: displayActor(e.recorded_by ?? ""),
      hours: e.billable_hours,
      description: e.description,
      start: e.start_time,
      end: (e as { end_time?: string }).end_time,
    });
  }

  for (const m of detail.emails) {
    if (m.created_at) entries.push({ kind: "email", at: m.created_at, event: "queued", subject: m.subject });
    if (m.status === "enviado" && m.sent_at) entries.push({ kind: "email", at: m.sent_at, event: "sent", subject: m.subject });
    else if (m.status === "rejeitado" || m.status === "falhou" || m.status === "envio_incerto" || m.status === "cancelado")
      entries.push({
        kind: "email",
        at: m.updated_at ?? m.created_at ?? "",
        event: m.status === "rejeitado" ? "rejected" : m.status === "cancelado" ? "cancelled" : "failed",
        subject: m.subject,
      });
  }

  // Newest first: what happened last is what the operator needs to see.
  return entries.filter((e) => e.at).sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

/** The stages a ticket/demand walks through, in order, for the progress line. */
export const STAGE_FLOW: WorkItemStage[] = ["novo", "em_andamento", "aguardando_cliente", "resolvido", "fechado"];

/** Billable hours for a period, as Darckware rounds them: 30-minute blocks, rounded up. */
export function billableHours(minutes: number): number {
  return minutes <= 0 ? 0 : Math.ceil(minutes / 30) * 0.5;
}
