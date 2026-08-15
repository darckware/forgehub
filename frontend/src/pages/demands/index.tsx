import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Archive,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  ChevronsUpDown,
  Clock,
  Download,
  Inbox as InboxIcon,
  Loader2,
  RotateCw,
  Paperclip,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Send,
  Trash2,
  User,
  Workflow,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { DemandFormPanel } from "@/pages/demands/DemandFormPanel";
import { useAssistantContext } from "@/hooks/useAssistant";
import { InboxGroupTree } from "@/components/InboxGroupTree";
import { AgentDirectionTree, DEMAND_DRAG_MIME, NO_AGENT_ID, SimpleDemandGroup } from "@/components/AgentInboxTree";
import { AgentCommsGraph } from "@/components/AgentCommsGraph";
import { DemandsStatsPanel } from "@/components/DemandsStatsPanel";
import { DemandsControlPanel } from "@/components/DemandsControlPanel";
import { useAgents } from "@/hooks/useAgent";
import {
  computeInboxTotalCount,
  downloadDemandAttachment,
  isIncomingItem,
  canReprocess,
  DISPATCH_MAX_ATTEMPTS,
  useArchiveDemands,
  useCleanupArchived,
  useCleanupDemands,
  useDeleteDemand,
  useDeleteDemandAttachment,
  useDemandGroups,
  useDemands,
  useDispatchDemand,
  useDispatchStatus,
  useMoveDemand,
  useReprocessDemands,
  useUpdateDemand,
  useUpdateDemandStatus,
  type ConvertTarget,
  type Demand,
  type DemandStatus,
} from "@/hooks/useDemands";

const STATUS_BADGE: Record<DemandStatus, { variant: "default" | "secondary" | "success" | "outline"; label: string }> = {
  new: { variant: "default", label: "New" },
  read: { variant: "secondary", label: "Read" },
  converted: { variant: "success", label: "Converted" },
  archived: { variant: "outline", label: "Archived" },
};

const CONVERT_TARGET_LABELS: Record<ConvertTarget, string> = {
  task: "Task",
  doc: "Document",
  artifact: "Artifact",
  knowledge_base: "Knowledge Base",
  planning_item: "Planning Item",
  project_doc: "Project Document",
  quick_task: "Quick Task",
};

/** True for items that belong in Outbox: the original agent-forward case
 * (from_agent_id AND target_agent_id both set -- an agent forwarding
 * something onward) plus, since 2026-07-24, a human-composed item whose
 * Origin is Task (DemandFormPanel sends these with no from_agent_id, but
 * origin_type="task" alone is enough to count as "sent out" -- see that
 * file's docstring). Sub-classification by agent still keys off
 * from_agent_id, so a task-origin compose (no from_agent_id) naturally
 * falls under the "Admin" row.
 *
 * Excludes a terminal dispatch (2026-07-28, Marcelo: "executou move para
 * completed, não fica tendo da Outgoing") -- Outgoing is "still moving",
 * not a permanent sent-log; once resolved it lives only in
 * Completed/Failed, symmetric with how those two already work as their
 * own lifecycle-stage groups. Also excludes self-addressed items
 * (2026-08-15, Marcelo: "se o próprio agente que vai executar então ele
 * não tem saída e sim uma entrada") -- work a sender addressed to itself
 * is Incoming for that agent (isIncomingItem), never Outgoing. */
function isOutboxItem(d: Demand): boolean {
  const selfDirected = Boolean(d.target_agent_id) && d.target_agent_id === d.from_agent_id;
  return (
    (Boolean(d.from_agent_id && d.target_agent_id) || d.origin_type === "task") &&
    !selfDirected &&
    d.dispatch_status !== "completed" &&
    d.dispatch_status !== "failed"
  );
}

/** Backlog: o que foi classificado como Tipo=Backlog -- trabalho
 * estacionado, ainda não é tarefa e não dispara nada. Sai daqui pelo botão
 * Promover a Task, no painel de leitura.
 *
 * Duas correções empilhadas aqui, no mesmo dia. O grupo nasceu em
 * 2026-07-25 filtrando `dispatch_status === "pending"`, valor que o backend
 * **nunca grava** (ele só produz dispatched/running/completed/failed), o que
 * o deixava estruturalmente vazio. A causa de raiz, porém, era não existir
 * um Tipo "incubation": o grupo tinha sido criado sem o valor correspondente e
 * por isso precisou se definir por estado de despacho em vez de pelo que o
 * item é. Com o Tipo criado (2026-07-26), ele passa a filtrar pelo próprio
 * Tipo, que é o que o nome do grupo sempre prometeu. */
function isIncubationItem(d: Demand): boolean {
  return d.status !== "archived" && d.origin_type === "incubation";
}

/** Finalizado: o despacho terminou e produziu resposta (2026-07-26). Fecha o
 * ciclo que o sidebar já mostrava pela metade -- havia grupo para o que está
 * em execução e para o que falhou, mas o que deu certo simplesmente voltava
 * para Entrada/Saída sem lugar próprio, então "o que já terminou" era a única
 * pergunta do ciclo de vida sem resposta na árvore. */
function isCompletedItem(d: Demand): boolean {
  return d.status !== "archived" && d.dispatch_status === "completed";
}

/** Which folder the message list/reading pane are scoped to. Three
 * top-level groups (PROPOSTA-INBOX-DISPATCH §6, reorganized 2026-07-24 to
 * group by direction first, agent second):
 * - "inbox": agentId null = every non-archived message (the root "Incoming"
 *   view); NO_AGENT_ID = only messages with no target agent ("Admin"); a
 *   string = only messages dispatched TO that agent.
 * - "outbox": agentId null = every message counted by isOutboxItem;
 *   NO_AGENT_ID = same, but with no from_agent_id ("Admin", i.e. sent by
 *   the logged-in user or a Task-origin compose); a string = same, sent by
 *   that agent.
 * - "archived": the Archived tree, where groupId null means the Archived
 *   root (uncategorized) and a string means a specific user-created
 *   subfolder. Nothing lands here on creation any more -- archiving is
 *   always an explicit action (the Archive button or a drag onto a
 *   folder). Tipo=Nota used to file straight in here, and went away with
 *   the type itself (2026-07-26); the group was labelled "Anotações"
 *   because of it, and is now honestly named "Arquivadas".
 * - "incubation" / "running" / "failed": flat groups (SimpleDemandGroup, not
 *   AgentDirectionTree -- no per-agent breakdown) added 2026-07-25.
 *   "incubation" = Tipo=Backlog (see isIncubationItem), the one keyed off what
 *   the item *is* rather than off its dispatch state -- backlog work
 *   hasn't been dispatched because it isn't a task yet, not because it's
 *   queued. The other three are lifecycle, mirroring dispatch_status:
 *   "running" = "dispatched"/"running" (the aggregate view a single-item
 *   reading pane can't give you when several dispatches are in flight at
 *   once), "failed" = "failed", "completed" = "completed" (added
 *   2026-07-26 -- the tree had a home for in-flight and for broken work,
 *   but finished work fell back into Incoming/Outgoing with nowhere of its
 *   own). All four sit between Outgoing and Archived, which stays last.
 * Each row's messages render inline, directly under itself in the tree
 * (see AgentDirectionTree/InboxGroupTree) rather than in a separate pane. */
type SelectedFolder =
  | { kind: "inbox"; agentId: string | null }
  | { kind: "outbox"; agentId: string | null }
  | { kind: "archived"; groupId: string | null; agentId?: string | null }
  | { kind: "incubation" }
  | { kind: "running" }
  | { kind: "failed" }
  | { kind: "completed"; agentId: string | null };

/** What the cleanup confirm dialog is about to delete -- either an
 * age-based sweep (the toolbar's "Keep last N days"/"Clear all", days:
 * null = clear all) or every message currently in one of the top-level
 * groups (the sidebar's per-group cleanup icon). */
type CleanupTarget =
  | { kind: "age"; days: number | null }
  | { kind: "group"; scope: "inbox" | "outbox" | "incubation" | "running" | "failed" | "completed" | "notes" };

/** What the group archive icon (2026-07-27) is about to file under
 * Arquivadas -- only offered on groups where "I'm done looking at this" is
 * the common case. Unlike CleanupTarget there's no age-based sweep here:
 * bulk archive is only ever reached from a group's own hover icon. */
type ArchiveTarget = { scope: "completed" | "failed" };

function archiveTargetIds(target: ArchiveTarget, demands: Demand[]): string[] {
  if (target.scope === "completed") return demands.filter(isCompletedItem).map((d) => d.id);
  return demands.filter((d) => d.status !== "archived" && d.dispatch_status === "failed").map((d) => d.id);
}

function cleanupTargetIds(target: CleanupTarget, demands: Demand[]): string[] {
  if (target.kind === "age") {
    // Scoped to terminal/archived mail only (2026-08-15, Marcelo: "as
    // messages precisam ter um plano de limpeza" -- same boundary as the
    // automatic 60-day retention sweep, DEMAND_RETENTION_DAYS). An open
    // thread (Incoming/Outgoing/Incubation) or an in-flight dispatch
    // (Running) is never swept here no matter how old it is -- only how
    // it ended is. Before this, "Clear all" deleted literally every
    // demand in the table regardless of state, which is what wiped an
    // in-progress Incubation decision the one time it was used unscoped.
    const eligible = demands.filter(
      (d) => d.status === "archived" || d.dispatch_status === "completed" || d.dispatch_status === "failed"
    );
    if (target.days === null) return eligible.map((d) => d.id);
    const cutoffMs = Date.now() - target.days * 24 * 60 * 60 * 1000;
    return eligible.filter((d) => new Date(d.updated_at).getTime() < cutoffMs).map((d) => d.id);
  }
  if (target.scope === "inbox") return demands.filter((d) => d.status !== "archived").map((d) => d.id);
  if (target.scope === "outbox") return demands.filter((d) => d.status !== "archived" && isOutboxItem(d)).map((d) => d.id);
  if (target.scope === "incubation") return demands.filter(isIncubationItem).map((d) => d.id);
  if (target.scope === "running")
    return demands
      .filter((d) => d.status !== "archived" && (d.dispatch_status === "dispatched" || d.dispatch_status === "running"))
      .map((d) => d.id);
  if (target.scope === "failed")
    return demands.filter((d) => d.status !== "archived" && d.dispatch_status === "failed").map((d) => d.id);
  if (target.scope === "completed") return demands.filter(isCompletedItem).map((d) => d.id);
  return demands.filter((d) => d.status === "archived").map((d) => d.id);
}

function formatTimestamp(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

function AttachmentRow({ demand, attachment }: { demand: Demand; attachment: Demand["attachments"][number] }) {
  const deleteAttachment = useDeleteDemandAttachment();
  return (
    <div className="flex items-start justify-between gap-2 rounded-md bg-muted/30 px-2.5 py-1.5 text-xs">
      <button
        type="button"
        className="min-w-0 flex-1 text-left"
        onClick={() => downloadDemandAttachment(demand.id, attachment)}
      >
        <span className="flex items-center gap-1.5 hover:underline">
          <Paperclip className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{attachment.filename}</span>
          <span className="shrink-0 text-muted-foreground">{formatBytes(attachment.size_bytes)}</span>
        </span>
        {/* The caption sits under the filename rather than beside it: it is
            free text and would otherwise squeeze the name out of view. */}
        {attachment.description && (
          <span className="mt-0.5 block pl-5 text-[11px] text-muted-foreground">
            {attachment.description}
          </span>
        )}
      </button>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground"
          onClick={() => downloadDemandAttachment(demand.id, attachment)}
          title="Download"
        >
          <Download className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => deleteAttachment.mutate({ demandId: demand.id, attachmentId: attachment.id })}
          title="Remove attachment"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

/** Inline form revealed by ReadingPane's "Send to Outgoing" button: picks a
 * target agent and an instruction, then dispatches this item's content (+
 * the instruction) to that agent's CLI via useDispatchDemand -- the backend
 * (build_thread_prompt) is what actually concatenates the received content
 * with the instruction into the final prompt. */
function SendToOutgoingForm({ demand, onDone }: { demand: Demand; onDone: () => void }) {
  const { t } = useTranslation("demands");
  const { data: agents, isLoading: agentsLoading } = useAgents();
  const dispatchDemand = useDispatchDemand();
  const dispatchable = (agents ?? []).filter((a) => a.runtime_type);
  const [targetAgentId, setTargetAgentId] = useState("");
  const [instructions, setInstructions] = useState("");
  /** Backlog is parked work nobody has taken on: without a registered sender
   *  a run would have no agent on the record to answer for it, and a reply
   *  would have nowhere to route back to. The backend refuses it (400) --
   *  saying so here means the operator learns it before clicking, and learns
   *  what to do about it. */
  const blockedIncubation = demand.origin_type === "incubation" && !demand.from_agent_id;

  function handleSend() {
    if (!targetAgentId || blockedIncubation) return;
    dispatchDemand.mutate(
      { id: demand.id, payload: { targetAgentId, commandText: instructions.trim() || undefined } },
      { onSuccess: onDone }
    );
  }

  return (
    <div className="mt-3 space-y-2 rounded-md border border-border bg-muted/20 p-3">
      {blockedIncubation && (
        <p className="flex items-start gap-1.5 text-xs text-amber-500">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {t("sendToOutgoing.backlogNeedsSender")}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        <Select
          value={targetAgentId}
          className="h-8 w-56 text-xs"
          disabled={agentsLoading || blockedIncubation}
          onChange={(e) => setTargetAgentId(e.target.value)}
        >
          <option value="">{agentsLoading ? t("sendToOutgoing.loading") : t("sendToOutgoing.selectAgent")}</option>
          {dispatchable.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </Select>
        <Button
          size="sm"
          disabled={!targetAgentId || blockedIncubation || dispatchDemand.isPending}
          onClick={handleSend}
        >
          {dispatchDemand.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t("sendToOutgoing.submit")}
        </Button>
      </div>
      <Textarea
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
        placeholder={t("sendToOutgoing.instructionsPlaceholder")}
        className="min-h-16 text-xs"
      />
      {dispatchDemand.isError && (
        <p className="text-xs text-destructive">{(dispatchDemand.error as Error)?.message}</p>
      )}
    </div>
  );
}

function ReadingPane({
  demand,
  onEdit,
  awaitingResponse,
  canSendToOutgoing,
}: {
  demand: Demand;
  onEdit: () => void;
  /** requires_response=true and no reply has landed yet -- see
   * DemandsPage's answeredOriginIds/AR_TITLE for how this is derived. */
  awaitingResponse: boolean;
  /** True while browsing an Incoming folder -- gates the "Send to Outgoing"
   * control (forwards this item's content, plus an instruction, to a
   * target agent). Not shown from Outgoing/Notes: there's nothing incoming
   * left to relay onward from those views. */
  canSendToOutgoing: boolean;
}) {
  const { t } = useTranslation("demands");
  const updateStatus = useUpdateDemandStatus();
  const promoteToTask = useUpdateDemand();
  const reprocessOne = useReprocessDemands();
  const deleteDemand = useDeleteDemand();
  // agent_run_id, not just dispatch_status, is what the backend requires --
  // a scheduled dispatch that fails before ever starting (e.g. the target
  // agent has no runtime_type, see run_scheduled_dispatch_pass) sets
  // dispatch_status="failed" with no agent_run_id, since it never got that
  // far. Polling anyway 400s ("This item has not been dispatched").
  const dispatchStatus = useDispatchStatus(demand.id, Boolean(demand.dispatch_status) && Boolean(demand.agent_run_id));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [sendToOutgoingOpen, setSendToOutgoingOpen] = useState(false);

  useEffect(() => {
    if (demand.status === "new") {
      updateStatus.mutate({ id: demand.id, status: "read" });
    }
    setSendToOutgoingOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demand.id]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ConfirmDialog
        open={confirmDelete}
        title={`Delete "${demand.subject}"`}
        description="Permanently removes the message from the inbox."
        loading={deleteDemand.isPending}
        onConfirm={() => deleteDemand.mutate(demand.id, { onSuccess: () => setConfirmDelete(false) })}
        onCancel={() => setConfirmDelete(false)}
      />
      <div className="shrink-0 border-b border-border/60 px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold leading-tight">
            <span className="mr-1.5 text-muted-foreground">#{demand.number}</span>
            {demand.subject}
          </h2>
          <span className="flex shrink-0 items-center gap-1.5">
            {awaitingResponse && (
              <Badge variant="warning" title={t("pending.tooltip")}>
                {t("pending.sigla")}
              </Badge>
            )}
            <Badge variant={STATUS_BADGE[demand.status].variant}>{STATUS_BADGE[demand.status].label}</Badge>
          </span>
        </div>
        <div className="mt-1.5 flex items-center gap-1.5 text-sm text-muted-foreground">
          <User className="h-3.5 w-3.5" />
          <span className="font-medium text-foreground">{demand.from_agent}</span>
          <span>· {formatTimestamp(demand.created_at)}</span>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <Button size="sm" variant="outline" className="gap-1.5" onClick={onEdit}>
            <Pencil className="h-3.5 w-3.5" /> {t("editButton")}
          </Button>
          {/* Promover Backlog -> Task: tirar do estacionamento é o único
              caminho para o item virar executável. Task nunca fica sem
              agente (2026-07-27, regra do backend em _require_task_target),
              então esta promoção já manda um destinatário -- o que já
              estiver em To, senão De (mesma convenção "To em branco = para
              o próprio remetente" da composição). Sem nenhum dos dois, não
              tem para quem executar: o botão fica desabilitado até o
              operador definir De na edição. O horário de disparo o backend
              agenda sozinho (auto-schedule em update_demand); o formulário
              continua aberto em seguida para revisar antes de rodar. */}
          {demand.origin_type === "incubation" && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              disabled={promoteToTask.isPending || !(demand.target_agent_id || demand.from_agent_id)}
              title={
                demand.target_agent_id || demand.from_agent_id
                  ? undefined
                  : t("promoteToTaskNeedsAgent")
              }
              onClick={() =>
                promoteToTask.mutate(
                  {
                    id: demand.id,
                    originType: "task",
                    targetAgentId: demand.target_agent_id ?? demand.from_agent_id,
                  },
                  { onSuccess: onEdit }
                )
              }
            >
              {promoteToTask.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ArrowUpRight className="h-3.5 w-3.5" />
              )}
              {t("promoteToTask")}
            </Button>
          )}
          {/* Reprocessar esta falha (2026-08-13). Só aparece enquanto restam
              tentativas: esgotadas, insistir sem corrigir a causa apenas
              repete a mesma falha, e o backend recusa com 409. */}
          {canReprocess(demand) && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              disabled={reprocessOne.isPending}
              title={t("reprocess.itemTitle", {
                attempts: demand.dispatch_attempts,
                max: DISPATCH_MAX_ATTEMPTS,
              })}
              onClick={() => reprocessOne.mutate([demand.id])}
            >
              {reprocessOne.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCw className="h-3.5 w-3.5" />
              )}
              {t("reprocess.itemButton")}
            </Button>
          )}
          {demand.status !== "archived" && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => updateStatus.mutate({ id: demand.id, status: "archived" })}
            >
              <Archive className="h-3.5 w-3.5" /> Archive
            </Button>
          )}
          {canSendToOutgoing && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => setSendToOutgoingOpen((v) => !v)}
            >
              <Send className="h-3.5 w-3.5" /> {t("sendToOutgoing.button")}
            </Button>
          )}
          <Button size="sm" variant="outline" className="gap-1.5 text-destructive" onClick={() => setConfirmDelete(true)}>
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </Button>
        </div>
        {canSendToOutgoing && sendToOutgoingOpen && (
          <SendToOutgoingForm demand={demand} onDone={() => setSendToOutgoingOpen(false)} />
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
        <Markdown content={demand.body} />

        {demand.attachments.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase text-muted-foreground">Attachments</p>
            {demand.attachments.map((a) => (
              <AttachmentRow key={a.id} demand={demand} attachment={a} />
            ))}
          </div>
        )}

        {demand.status === "converted" && demand.converted_reference && (
          <div className="flex items-start gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            <span>
              Done — converted to <strong>{CONVERT_TARGET_LABELS[demand.converted_entity_type as ConvertTarget]}</strong>: {demand.converted_reference}
            </span>
          </div>
        )}

        {demand.dispatch_status && (
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/20 p-3 text-sm">
            {(demand.dispatch_status === "dispatched" || demand.dispatch_status === "running") && (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />
            )}
            {demand.dispatch_status === "completed" && (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
            )}
            {demand.dispatch_status === "failed" && (
              <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
            )}
            <span>
              {t(`dispatch.status.${demand.dispatch_status}`)}
              {dispatchStatus.data?.reply_demand_id && ` — ${t("dispatch.replyArrived")}`}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function DemandListRow({
  demand,
  selected,
  onSelect,
  awaitingResponse,
}: {
  demand: Demand;
  selected: boolean;
  onSelect: () => void;
  /** requires_response=true and no reply has landed yet. */
  awaitingResponse: boolean;
}) {
  const { t } = useTranslation("demands");
  return (
    <button
      type="button"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData(DEMAND_DRAG_MIME, demand.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={onSelect}
      className={cn(
        "flex w-full flex-col gap-0.5 border-b border-border/50 px-3 py-2.5 text-left transition-colors",
        selected ? "bg-accent" : "hover:bg-accent/40"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          {demand.status === "new" && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />}
          <span className={cn("truncate text-sm", demand.status === "new" ? "font-semibold" : "font-medium")}>
            {demand.from_agent}
          </span>
          {awaitingResponse && (
            <Badge variant="warning" title={t("pending.tooltip")} className="shrink-0 px-1.5 py-0 text-[10px]">
              {t("pending.sigla")}
            </Badge>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[10px] text-muted-foreground">
          {/* Small live cue for a message actively dispatching (2026-07-28,
              Marcelo: "quando estiver processando gere pequenas animações
              nas messages em execução") -- distinct from the unread dot
              above, which is about status=new, not dispatch_status. Paired
              with useDemands' faster polling while anything is in flight,
              so this doesn't just animate forever on stale data. */}
          {(demand.dispatch_status === "dispatched" || demand.dispatch_status === "running") && (
            <span title={t(`dispatch.status.${demand.dispatch_status}`)}>
              <Loader2 className="h-3 w-3 shrink-0 animate-spin text-amber-500" />
            </span>
          )}
          {new Date(demand.created_at).toLocaleDateString()}
        </span>
      </div>
      <span className="truncate text-xs text-muted-foreground">
        <span className="text-muted-foreground/70">#{demand.number}</span> {demand.subject}
      </span>
      {demand.attachments.length > 0 && (
        <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
          <Paperclip className="h-3 w-3" /> {demand.attachments.length}
        </span>
      )}
    </button>
  );
}

export default function DemandsPage() {
  const { t } = useTranslation("demands");
  const { data: demands, isLoading, isError, error, refetch, isFetching } = useDemands();
  const { data: groups } = useDemandGroups();
  const moveDemand = useMoveDemand();
  const cleanupDemands = useCleanupDemands();
  const [cleanupConfirm, setCleanupConfirm] = useState<CleanupTarget | null>(null);
  const archiveDemands = useArchiveDemands();
  const reprocessDemands = useReprocessDemands();
  const cleanupArchived = useCleanupArchived();
  const [archiveConfirm, setArchiveConfirm] = useState<ArchiveTarget | null>(null);
  /** Reprocessar em massa passa por confirmação como toda ação em lote:
   * devolve N mensagens à fila de despacho de uma vez, e o operador precisa
   * ver quantas antes de confirmar. */
  const [reprocessConfirm, setReprocessConfirm] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [folder, setFolder] = useState<SelectedFolder>({ kind: "inbox", agentId: null });
  // Busca e filtro da barra de ferramentas -- ver searchMatches/typeMatches.
  const [search, setSearch] = useState("");
  // Tipo é obrigatório e só tem dois valores desde 2026-07-28 (nunca
  // null/"demand") -- "Todos os tipos" continua existindo como o estado
  // sem filtro, não como um terceiro Tipo.
  const [typeFilter, setTypeFilter] = useState<"all" | "task" | "incubation">("all");
  // Which top-level sidebar groups are expanded -- lifted out of each
  // group component (2026-07-25) so the toolbar's expand/collapse-all
  // toggle can drive all six at once; missing key = collapsed (matches
  // the previous per-component default). Only top-level rows -- nested
  // Notes subfolders keep their own independent local state.
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const GROUP_KEYS = ["inbox", "outbox", "incubation", "running", "failed", "completed", "notes"] as const;
  const allGroupsExpanded = GROUP_KEYS.every((key) => expandedGroups[key]);
  function toggleGroup(key: string) {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  }
  function toggleAllGroups() {
    const next = !allGroupsExpanded;
    setExpandedGroups(Object.fromEntries(GROUP_KEYS.map((key) => [key, next])));
  }
  // Top-level view: "messages" is the existing three-pane mailbox, unchanged;
  // "overview"/"stats"/"control" are read-only lenses over the same demands
  // list (see AgentCommsGraph/DemandsStatsPanel/DemandsControlPanel) added
  // 2026-07-25 so the module reads as a proper communications console, not
  // just an inbox.
  const [activeTab, setActiveTab] = useState<"messages" | "overview" | "stats" | "control">("messages");
  // Side panel state (DemandFormPanel) -- "create" for New note, "edit" for
  // the Alterar button on an existing message. Not a modal: it renders
  // inline in the reading-pane slot (see the panel-vs-ReadingPane branch
  // below), per Marcelo's mailbox/internal-email framing.
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [editingDemand, setEditingDemand] = useState<Demand | null>(null);
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");

  function openCompose() {
    setEditingDemand(null);
    setComposeSubject("");
    setComposeBody("");
    setFormMode("create");
  }

  function openEdit(demand: Demand) {
    setEditingDemand(demand);
    setComposeSubject(demand.subject);
    setComposeBody(demand.body);
    setFormMode("edit");
  }

  // "AR" (Aguardando Retorno / Awaiting Reply) -- a reply is any other
  // demand whose reply_to_id points back at this one (2026-07-28, see
  // _finalize_dispatch's reply creation). Derived, not stored: storing a
  // separate "answered" flag would need to be kept in sync by hand and
  // would drift; this is always correct as long as the reply itself
  // carries the right reply_to_id.
  const answeredOriginIds = useMemo(() => {
    const ids = new Set<string>();
    for (const d of demands ?? []) {
      if (d.reply_to_id) ids.add(d.reply_to_id);
    }
    return ids;
  }, [demands]);
  const isAwaitingResponse = (d: Demand) => d.requires_response && !answeredOriginIds.has(d.id);

  function closeForm() {
    setFormMode(null);
    setEditingDemand(null);
  }

  /** Busca livre + filtro por Tipo, aplicados *depois* do recorte de pasta
   * (`folderScoped` abaixo) e não no lugar dele: a árvore continua sendo a
   * navegação por direção/agente, e estes dois só estreitam o que já está
   * em vista. Complementam a árvore em vez de duplicá-la -- direção, agente
   * e arquivadas ela já resolve; Tipo (Task/Nota) e texto livre não tinham
   * como ser alcançados de jeito nenhum antes disso (2026-07-26). */
  const searchMatches = (d: Demand, termo: string) => {
    const q = termo.trim().toLowerCase();
    if (!q) return true;
    // "#613" e "613" acham a mensagem pelo número exibido na lista.
    const semCerquilha = q.startsWith("#") ? q.slice(1) : q;
    if (String(d.number) === semCerquilha) return true;
    return (
      d.subject.toLowerCase().includes(q) ||
      d.body.toLowerCase().includes(q) ||
      d.from_agent.toLowerCase().includes(q)
    );
  };

  const typeMatches = (d: Demand) => typeFilter === "all" || d.origin_type === typeFilter;

  /** Every message the current filters admit, before the folder cut. This is
   * the base for the whole screen -- the folder tree's counters, the other
   * tabs, and `filtered` below -- so a filter narrows what the page *is*,
   * not just the list in the middle. Counters that ignored it used to
   * advertise messages the user could no longer reach. */
  const visible = useMemo(
    () => (demands ?? []).filter((d) => typeMatches(d) && searchMatches(d, search)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [demands, search, typeFilter],
  );

  const filtered = useMemo(() => {
    const all = visible;
    if (folder.kind === "inbox") {
      // System (NO_AGENT_ID) is untouched by the "letter" rule below: an
      // item addressed to nobody never enters dispatch at all
      // (dispatch_status stays NULL forever, target_agent_id required to
      // fire), so gating it the same way would make System permanently
      // empty instead of the human-note catch-all it actually is. Requires
      // no from_agent_id too (2026-08-15, Marcelo: "não existe anônima")
      // -- a no-target row with a sender is an Incubation item someone
      // already owns (incubation_owner_id falls back to from_agent_id),
      // not a System note; counting it here too would double it into a
      // badge it doesn't belong to.
      if (folder.agentId === null)
        return all.filter(
          (d) => d.status !== "archived" && ((!d.target_agent_id && !d.from_agent_id) || isIncomingItem(d, d.target_agent_id ?? ""))
        );
      if (folder.agentId === NO_AGENT_ID)
        return all.filter((d) => d.status !== "archived" && !d.target_agent_id && !d.from_agent_id);
      return all.filter((d) => isIncomingItem(d, folder.agentId!));
    }
    if (folder.kind === "outbox") {
      if (folder.agentId === null) return all.filter((d) => d.status !== "archived" && isOutboxItem(d));
      if (folder.agentId === NO_AGENT_ID)
        return all.filter((d) => d.status !== "archived" && isOutboxItem(d) && !d.from_agent_id);
      return all.filter((d) => d.status !== "archived" && isOutboxItem(d) && d.from_agent_id === folder.agentId);
    }
    if (folder.kind === "incubation") return all.filter(isIncubationItem);
    if (folder.kind === "running")
      return all.filter((d) => d.status !== "archived" && (d.dispatch_status === "dispatched" || d.dispatch_status === "running"));
    if (folder.kind === "failed") return all.filter((d) => d.status !== "archived" && d.dispatch_status === "failed");
    if (folder.kind === "completed") {
      const completed = all.filter(isCompletedItem);
      // Grouped by target_agent_id -- the agent actually dispatched to run
      // the work, i.e. the one who finished it (2026-07-27, Marcelo: tasks
      // executadas com sucesso devem ser transferidas para completed por
      // agente). Same key AgentDirectionTree's Inbox tree already uses.
      if (folder.agentId === null) return completed;
      if (folder.agentId === NO_AGENT_ID) return completed.filter((d) => !d.target_agent_id);
      return completed.filter((d) => d.target_agent_id === folder.agentId);
    }
    // Root-level (uncategorized, group_id null) breaks down by agent, same
    // as Incoming/Outgoing/Completed (2026-07-28, Marcelo: "tem que agrupo
    // por agentes igual ao Incoming") -- a real subfolder stays a flat
    // list, that axis is user-organized, not agent-organized. Keyed off
    // from_agent_id, not target_agent_id like Completed -- a return message
    // (from=executor, to=original sender) grouped by target_agent_id put
    // Atlas/Vector/etc.'s replies inside "Athos", showing another agent's
    // name in bold on every row (Marcelo: "estão entrando outros agente no
    // grupo do Athos"). from_agent_id matches the bold name DemandListRow
    // shows on each row (demand.from_agent), so "Athos" only ever holds
    // what Athos itself sent.
    if (folder.groupId === null && folder.agentId !== undefined) {
      const root = all.filter((d) => d.status === "archived" && d.group_id === null);
      if (folder.agentId === null) return root;
      if (folder.agentId === NO_AGENT_ID) return root.filter((d) => !d.from_agent_id);
      return root.filter((d) => d.from_agent_id === folder.agentId);
    }
    return all.filter((d) => d.status === "archived" && d.group_id === folder.groupId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, folder]);

  const agentInboxCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of visible) {
      if (d.target_agent_id && isIncomingItem(d, d.target_agent_id))
        counts[d.target_agent_id] = (counts[d.target_agent_id] ?? 0) + 1;
    }
    return counts;
  }, [visible]);
  const agentOutboxCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of visible) {
      if (d.status !== "archived" && isOutboxItem(d) && d.from_agent_id)
        counts[d.from_agent_id] = (counts[d.from_agent_id] ?? 0) + 1;
    }
    return counts;
  }, [visible]);
  const adminInboxCount = useMemo(
    () => visible.filter((d) => d.status !== "archived" && !d.target_agent_id && !d.from_agent_id).length,
    [visible]
  );
  /** Root badge for the Incoming tree -- must match exactly what selecting
   * the root row itself shows (`filtered` above, folder.agentId === null):
   * System's count plus every agent's *arrived* count (isIncomingItem),
   * never a broader "everything non-archived" -- that mismatch is what
   * made the root badge disagree with its own System sub-row before
   * (2026-07-27) and would immediately recur here if this stopped tracking
   * `filtered`'s own composition one edit later. Distinct from
   * `unreadCount`, which counts only status="new" for the header's "X
   * Novo" pill, a different concept entirely. */
  // A MESMA função do título e do badge da sidebar (2026-08-13, Marcelo:
  // "use a mesma função para calcular o total não lido"). Antes esta soma
  // reimplementava a lógica de computeInboxTotalCount somando as contagens
  // por agente -- duas fórmulas para o mesmo conceito, que divergiam sozinhas.
  // Somar por agente também perdia qualquer mensagem cujo target_agent_id não
  // tivesse linha renderizada na árvore: entrava no total do título e em
  // nenhuma linha visível. A única diferença que resta é a lista: aqui
  // `visible` (filtrado, para bater com o que a pasta mostra), no título
  // `demands` (sem filtro, para uma busca não encolher só o pill).
  const inboxTotalCount = useMemo(() => computeInboxTotalCount(visible), [visible]);
  const adminOutboxCount = useMemo(
    () => visible.filter((d) => d.status !== "archived" && isOutboxItem(d) && !d.from_agent_id).length,
    [visible]
  );
  const outboxTotalCount = useMemo(
    () => visible.filter((d) => d.status !== "archived" && isOutboxItem(d)).length,
    [visible]
  );
  const incubationCount = useMemo(() => visible.filter(isIncubationItem).length, [visible]);
  const runningCount = useMemo(
    () =>
      visible.filter(
        (d) => d.status !== "archived" && (d.dispatch_status === "dispatched" || d.dispatch_status === "running")
      ).length,
    [visible]
  );
  const failedCount = useMemo(
    () => visible.filter((d) => d.status !== "archived" && d.dispatch_status === "failed").length,
    [visible]
  );

  const completedCount = useMemo(() => visible.filter(isCompletedItem).length, [visible]);
  const agentCompletedCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of visible) {
      if (isCompletedItem(d) && d.target_agent_id) counts[d.target_agent_id] = (counts[d.target_agent_id] ?? 0) + 1;
    }
    return counts;
  }, [visible]);
  const adminCompletedCount = useMemo(
    () => visible.filter((d) => isCompletedItem(d) && !d.target_agent_id).length,
    [visible]
  );

  const archivedCount = visible.filter((d) => d.status === "archived").length;
  const archivedCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of visible) {
      if (d.status === "archived" && d.group_id) counts[d.group_id] = (counts[d.group_id] ?? 0) + 1;
    }
    return counts;
  }, [visible]);
  // Agent breakdown for the Archived root's *uncategorized* items only
  // (group_id null) -- a real user-created subfolder is organized by theme,
  // not by agent, so it stays a flat list (2026-07-28, Marcelo: "tem que
  // agrupo por agentes igual ao Incoming"). Keyed off from_agent_id -- see
  // `filtered`'s archived branch for why (matches the bold sender name each
  // row shows, so "Athos" never displays another agent's replies).
  const archivedRootAdminCount = useMemo(
    () => visible.filter((d) => d.status === "archived" && d.group_id === null && !d.from_agent_id).length,
    [visible]
  );
  const archivedRootAgentCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of visible) {
      if (d.status === "archived" && d.group_id === null && d.from_agent_id)
        counts[d.from_agent_id] = (counts[d.from_agent_id] ?? 0) + 1;
    }
    return counts;
  }, [visible]);
  // Global total, independent of the search/type filter -- must always
  // match the sidebar nav badge (Sidebar.tsx's `unreadDemandsCount`) and
  // the Incoming tree's own root badge (2026-07-28, Marcelo: "os todas tem
  // que obedecer o total do grupo de entrada... tem que haver sync") --
  // all three now read the same computeInboxTotalCount, the header/sidebar
  // against the unfiltered `demands` (so an active search doesn't shrink
  // just this pill) and the tree's own `inboxTotalCount` below against the
  // filtered `visible` (so it matches what the folder actually shows).
  const unreadCount = computeInboxTotalCount(demands ?? []);
  const selected = (demands ?? []).find((d) => d.id === selectedId) ?? null;

  useAssistantContext({
    label: "Use current message",
    build: () => {
      if (!selected) return null;
      return [
        `I'm looking at an Inbox message from ${selected.from_agent}.`,
        `Subject: ${selected.subject}`,
        "",
        "Content:",
        "```markdown",
        selected.body,
        "```",
      ].join("\n");
    },
    form: formMode
      ? {
          description: formMode === "edit" ? "Edit Inbox message" : "New Inbox note",
          fields: [
            { name: "subject", label: "Subject", hint: "required, max 255 characters" },
            { name: "body", label: "Body", hint: "required, markdown" },
          ],
          onFill: (values) => {
            if (typeof values.subject === "string") setComposeSubject(values.subject);
            if (typeof values.body === "string") setComposeBody(values.body);
          },
        }
      : undefined,
  });

  /** Jumps from the Controle tab straight to this item in Mensagens --
   * lands on the Incoming root (unfiltered) rather than trying to
   * reconstruct which exact folder the item lives in (archived items,
   * outbox forwards, etc. would each need their own SelectedFolder logic
   * just for this one jump). */
  function openFromControl(demand: Demand) {
    setActiveTab("messages");
    setFolder({ kind: "inbox", agentId: null });
    setSelectedId(demand.id);
    closeForm();
  }

  function selectFolder(next: SelectedFolder) {
    setFolder(next);
    setSelectedId(null);
    closeForm();
  }

  const emptyMessage =
    folder.kind === "inbox" && folder.agentId === null
      ? 'Nothing here yet. Agents submit via /demands/submit, or click "New message".'
      : folder.kind === "archived"
      ? "No archived messages here yet. Drag a message from Incoming into this folder."
      : folder.kind === "incubation"
      ? t("emptyBacklogMessage")
      : folder.kind === "running"
      ? t("emptyRunningMessage")
      : folder.kind === "failed"
      ? t("emptyFailedMessage")
      : folder.kind === "completed"
      ? t("emptyCompletedMessage")
      : "Nothing dispatched here yet.";

  function renderMessage(demand: Demand) {
    return (
      <DemandListRow
        key={demand.id}
        demand={demand}
        selected={selectedId === demand.id}
        awaitingResponse={isAwaitingResponse(demand)}
        onSelect={() => {
          setSelectedId(demand.id);
          closeForm();
        }}
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <ConfirmDialog
        open={cleanupConfirm !== null}
        title={t("cleanup.confirmTitle")}
        description={
          cleanupConfirm === null
            ? ""
            : cleanupConfirm.kind === "group"
              ? t("cleanup.confirmGroupDescription", {
                  group:
                    cleanupConfirm.scope === "inbox"
                      ? t("incomingFolder")
                      : cleanupConfirm.scope === "outbox"
                        ? t("outgoingFolder")
                        : cleanupConfirm.scope === "incubation"
                          ? t("backlogFolder")
                          : cleanupConfirm.scope === "running"
                            ? t("runningFolder")
                            : cleanupConfirm.scope === "failed"
                              ? t("failedFolder")
                              : cleanupConfirm.scope === "completed"
                                ? t("completedFolder")
                                : t("archivedFolder"),
                })
              : cleanupConfirm.days === null
                ? t("cleanup.confirmClearAllDescription")
                : t("cleanup.confirmKeepDescription", { days: cleanupConfirm.days })
        }
        loading={cleanupDemands.isPending || cleanupArchived.isPending}
        onConfirm={() => {
          if (!cleanupConfirm) return;
          // Arquivadas é o único grupo que também mostra pastas, então
          // limpá-lo tem de levar as pastas junto -- só apagar mensagens
          // deixava a árvore igual e o clique parecia não funcionar.
          if (cleanupConfirm.kind === "group" && cleanupConfirm.scope === "notes") {
            cleanupArchived.mutate(
              {
                demandIds: cleanupTargetIds(cleanupConfirm, demands ?? []),
                // Só as raízes: as subpastas caem por cascade, e pedir a
                // exclusão de uma já removida daria 404.
                rootGroupIds: (groups ?? []).filter((g) => !g.parent_id).map((g) => g.id),
              },
              { onSuccess: () => setCleanupConfirm(null) }
            );
            return;
          }
          cleanupDemands.mutate(cleanupTargetIds(cleanupConfirm, demands ?? []), {
            onSuccess: () => setCleanupConfirm(null),
          });
        }}
        onCancel={() => setCleanupConfirm(null)}
      />
      <ConfirmDialog
        open={archiveConfirm !== null}
        variant="default"
        title={t("archive.confirmTitle")}
        description={
          archiveConfirm === null
            ? ""
            : t("archive.confirmGroupDescription", {
                group: archiveConfirm.scope === "completed" ? t("completedFolder") : t("failedFolder"),
              })
        }
        confirmLabel={t("archive.confirmButton")}
        loading={archiveDemands.isPending}
        onConfirm={() => {
          if (!archiveConfirm) return;
          archiveDemands.mutate(archiveTargetIds(archiveConfirm, demands ?? []), {
            onSuccess: () => setArchiveConfirm(null),
          });
        }}
        onCancel={() => setArchiveConfirm(null)}
      />
      <ConfirmDialog
        open={reprocessConfirm}
        variant="default"
        title={t("reprocess.confirmTitle")}
        description={t("reprocess.confirmDescription", {
          count: (demands ?? []).filter(canReprocess).length,
        })}
        confirmLabel={t("reprocess.confirmButton")}
        loading={reprocessDemands.isPending}
        onConfirm={() => {
          // Só o que ainda pode ser reprocessado: uma falha que já esgotou
          // as tentativas seria recusada pelo backend (409), e mandá-la
          // junto só produziria erro no meio do lote.
          reprocessDemands.mutate(
            (demands ?? []).filter(canReprocess).map((d) => d.id),
            { onSuccess: () => setReprocessConfirm(false) }
          );
        }}
        onCancel={() => setReprocessConfirm(false)}
      />
      {/* Header on the same two columns as the content below it: the title
          column is exactly the folder tree's width (w-80), so the filters
          start where the reading pane starts instead of floating over the
          split. Filters live here, not in the message action bar, because
          they are global -- every tab renders the same filtered set. */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border/60 py-3 pr-4">
        <h1 className="flex w-80 shrink-0 items-center gap-2 pl-4 text-xl font-semibold">
          {t("inboxTitle")}
          <InboxIcon className="h-5 w-5" />
          {unreadCount > 0 && <Badge variant="destructive">{unreadCount} {t("new")}</Badge>}
        </h1>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          <div className="relative min-w-0 flex-1 max-w-md">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("filter.searchPlaceholder")}
              className="h-8 py-0 pl-8 pr-8"
            />
            {search && (
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => setSearch("")}
                title={t("filter.clearSearch")}
              >
                <XCircle className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          {/* py-0 é obrigatório junto com h-8: o primitivo Select traz
              h-10 com py-2, e 0.5rem+0.5rem de padding mais a altura da
              linha passam de 2rem -- o texto da opção sai cortado por
              baixo se só a altura for reduzida. */}
          <Select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)}
            className="h-8 w-40 py-0"
            title={t("filter.typeLabel")}
          >
            <option value="all">{t("filter.typeAll")}</option>
            <option value="task">{t("filter.typeTask")}</option>
            <option value="incubation">{t("filter.typeBacklog")}</option>
          </Select>
          <Tabs
            value={activeTab}
            onValueChange={(v) => setActiveTab(v as typeof activeTab)}
            className="ml-auto"
          >
            <TabsList>
              <TabsTrigger value="messages" title={t("tabs.messages")}>
                <InboxIcon className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger value="overview" title={t("tabs.overview")}>
                <Workflow className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger value="stats" title={t("tabs.stats")}>
                <BarChart3 className="h-4 w-4" />
              </TabsTrigger>
              <TabsTrigger value="control" title={t("tabs.control")}>
                <User className="h-4 w-4" />
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {/* Icon-only action bar for the Mensagens tab -- moved off the page
          header (2026-07-25) so the header stays just title+tabs, and these
          message-management actions sit directly above the folder tree they
          act on. */}
      {activeTab === "messages" && (
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-border/60 px-4 py-2">
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-auto gap-1 px-2"
            disabled={cleanupDemands.isPending}
            onClick={() => setCleanupConfirm({ kind: "age", days: 30 })}
            title={t("cleanup.keep30")}
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="text-xs">30d</span>
          </Button>
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-auto gap-1 px-2"
            disabled={cleanupDemands.isPending}
            onClick={() => setCleanupConfirm({ kind: "age", days: 15 })}
            title={t("cleanup.keep15")}
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="text-xs">15d</span>
          </Button>
          <Button
            size="icon"
            variant="destructive"
            className="h-8 w-8"
            disabled={cleanupDemands.isPending}
            onClick={() => setCleanupConfirm({ kind: "age", days: null })}
            title={t("cleanup.clearAll")}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-8"
            onClick={() => refetch()}
            disabled={isFetching}
            title="Refresh inbox"
          >
            {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </Button>
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-8"
            onClick={toggleAllGroups}
            title={allGroupsExpanded ? t("collapseAllGroups") : t("expandAllGroups")}
          >
            <ChevronsUpDown className="h-4 w-4" />
          </Button>
          <Button size="icon" className="h-8 w-8" onClick={openCompose} title={t("newNoteButton")}>
            <Plus className="h-4 w-4" />
          </Button>

        </div>
      )}

      {activeTab === "overview" && (
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <AgentCommsGraph demands={visible} />
        </div>
      )}
      {activeTab === "stats" && (
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <DemandsStatsPanel demands={visible} />
        </div>
      )}
      {activeTab === "control" && (
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <DemandsControlPanel demands={visible} onOpenDemand={openFromControl} />
        </div>
      )}

      {activeTab === "messages" && isLoading && (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}
      {activeTab === "messages" && isError && (
        <div className="flex flex-1 items-center justify-center gap-3 p-6 text-destructive">
          <AlertCircle className="h-5 w-5" />
          <span>Failed to load the inbox: {(error as Error)?.message}</span>
        </div>
      )}

      {activeTab === "messages" && !isLoading && !isError && (
        <div className="flex min-h-0 flex-1">
          <div className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-border/60 p-2">
            <AgentDirectionTree
              direction="inbox"
              label={t("incomingFolder")}
              noAgentLabel={t("systemLabel")}
              rootCount={inboxTotalCount}
              adminCount={adminInboxCount}
              agentCounts={agentInboxCounts}
              selected={folder.kind === "inbox" ? { agentId: folder.agentId } : undefined}
              expanded={Boolean(expandedGroups.inbox)}
              onToggleExpanded={() => toggleGroup("inbox")}
              onSelectRoot={() => selectFolder({ kind: "inbox", agentId: null })}
              onSelectAgent={(agentId) => selectFolder({ kind: "inbox", agentId })}
              onDropDemand={(demandId) => moveDemand.mutate({ id: demandId, groupId: null, status: "read" })}
              onCleanup={() => setCleanupConfirm({ kind: "group", scope: "inbox" })}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
            <AgentDirectionTree
              direction="outbox"
              label={t("outgoingFolder")}
              noAgentLabel={t("systemLabel")}
              rootCount={outboxTotalCount}
              adminCount={adminOutboxCount}
              agentCounts={agentOutboxCounts}
              selected={folder.kind === "outbox" ? { agentId: folder.agentId } : undefined}
              expanded={Boolean(expandedGroups.outbox)}
              onToggleExpanded={() => toggleGroup("outbox")}
              onSelectRoot={() => selectFolder({ kind: "outbox", agentId: null })}
              onSelectAgent={(agentId) => selectFolder({ kind: "outbox", agentId })}
              onCleanup={() => setCleanupConfirm({ kind: "group", scope: "outbox" })}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
            <SimpleDemandGroup
              icon={Clock}
              label={t("backlogFolder")}
              count={incubationCount}
              active={folder.kind === "incubation"}
              expanded={Boolean(expandedGroups.backlog)}
              onToggleExpanded={() => toggleGroup("incubation")}
              onSelect={() => selectFolder({ kind: "incubation" })}
              onCleanup={() => setCleanupConfirm({ kind: "group", scope: "incubation" })}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
            <SimpleDemandGroup
              icon={Loader2}
              label={t("runningFolder")}
              count={runningCount}
              active={folder.kind === "running"}
              expanded={Boolean(expandedGroups.running)}
              onToggleExpanded={() => toggleGroup("running")}
              onSelect={() => selectFolder({ kind: "running" })}
              onCleanup={() => setCleanupConfirm({ kind: "group", scope: "running" })}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
            <SimpleDemandGroup
              icon={XCircle}
              label={t("failedFolder")}
              count={failedCount}
              active={folder.kind === "failed"}
              expanded={Boolean(expandedGroups.failed)}
              onToggleExpanded={() => toggleGroup("failed")}
              onSelect={() => selectFolder({ kind: "failed" })}
              onCleanup={() => setCleanupConfirm({ kind: "group", scope: "failed" })}
              onArchive={() => setArchiveConfirm({ scope: "failed" })}
              onReprocess={() => setReprocessConfirm(true)}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
            {/* Grouped by agent like Incoming/Outgoing (2026-07-27) --
                finished work is read per agent, not as one flat pile.
                Keyed by target_agent_id: whoever was actually dispatched
                to run it, i.e. whoever finished it. */}
            <AgentDirectionTree
              direction="completed"
              label={t("completedFolder")}
              noAgentLabel={t("systemLabel")}
              rootCount={completedCount}
              adminCount={adminCompletedCount}
              agentCounts={agentCompletedCounts}
              selected={folder.kind === "completed" ? { agentId: folder.agentId } : undefined}
              expanded={Boolean(expandedGroups.completed)}
              onToggleExpanded={() => toggleGroup("completed")}
              onSelectRoot={() => selectFolder({ kind: "completed", agentId: null })}
              onSelectAgent={(agentId) => selectFolder({ kind: "completed", agentId })}
              onCleanup={() => setCleanupConfirm({ kind: "group", scope: "completed" })}
              onArchive={() => setArchiveConfirm({ scope: "completed" })}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
            <InboxGroupTree
              label={t("archivedFolder")}
              groups={groups ?? []}
              selectedGroupId={folder.kind === "archived" ? folder.groupId : undefined}
              expanded={Boolean(expandedGroups.notes)}
              onToggleExpanded={() => toggleGroup("notes")}
              onSelectRoot={() => selectFolder({ kind: "archived", groupId: null, agentId: null })}
              onSelectGroup={(id) => selectFolder({ kind: "archived", groupId: id })}
              onDropDemand={(demandId, groupId) => moveDemand.mutate({ id: demandId, groupId, status: "archived" })}
              onCleanup={() => setCleanupConfirm({ kind: "group", scope: "notes" })}
              counts={archivedCounts}
              rootCount={archivedCount}
              noAgentLabel={t("systemLabel")}
              adminCount={archivedRootAdminCount}
              agentCounts={archivedRootAgentCounts}
              selectedAgentId={
                folder.kind === "archived" && folder.groupId === null && folder.agentId != null
                  ? folder.agentId
                  : undefined
              }
              onSelectAgent={(agentId) => selectFolder({ kind: "archived", groupId: null, agentId })}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
          </div>

          <div className="min-w-0 flex-1">
            {formMode ? (
              <DemandFormPanel
                // Forces a fresh mount (and fresh useState initializers --
                // Tipo, To/From agent, Retorno, Send at, etc.) whenever
                // the edited demand's identity changes; without this,
                // React reuses the same component instance across
                // different `demand` prop values and every field that
                // seeds its initial state from `demand` (e.g. Tipo not
                // reflecting the newly-opened item's own origin_type)
                // keeps showing the previous edit's stale state until the
                // user manually touches each field.
                key={editingDemand?.id ?? "compose"}
                demand={editingDemand ?? undefined}
                subject={composeSubject}
                onSubjectChange={setComposeSubject}
                body={composeBody}
                onBodyChange={setComposeBody}
                onClose={closeForm}
              />
            ) : selected ? (
              <ReadingPane
                demand={selected}
                onEdit={() => openEdit(selected)}
                awaitingResponse={isAwaitingResponse(selected)}
                canSendToOutgoing={folder.kind === "inbox"}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {t("selectMessagePrompt")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
