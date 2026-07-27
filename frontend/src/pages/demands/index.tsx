import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Archive,
  CheckCircle2,
  Download,
  Inbox as InboxIcon,
  Loader2,
  Paperclip,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  User,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { DispatchMenu } from "@/components/DispatchMenu";
import { DemandFormPanel } from "@/pages/demands/DemandFormPanel";
import { useAssistantContext } from "@/hooks/useAssistant";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { InboxGroupTree } from "@/components/InboxGroupTree";
import { AgentDirectionTree, DEMAND_DRAG_MIME, NO_AGENT_ID } from "@/components/AgentInboxTree";
import {
  downloadDemandAttachment,
  useDeleteDemand,
  useDeleteDemandAttachment,
  useDemandGroups,
  useDemands,
  useDispatchDemand,
  useDispatchStatus,
  useMoveDemand,
  useNotifyTelegram,
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

/** Which folder the message list/reading pane are scoped to. Three
 * top-level groups (PROPOSTA-INBOX-DISPATCH §6, reorganized 2026-07-24 to
 * group by direction first, agent second):
 * - "inbox": agentId null = every non-archived message (the root "Incoming"
 *   view); NO_AGENT_ID = only messages with no target agent ("Admin"); a
 *   string = only messages dispatched TO that agent.
 * - "outbox": agentId null = every message this instance dispatched
 *   onward; NO_AGENT_ID = only messages dispatched by no agent ("Admin",
 *   i.e. by the logged-in user); a string = only messages dispatched BY
 *   that agent.
 * - "archived": the Archived tree, where groupId null means the Archived
 *   root (uncategorized) and a string means a specific user-created
 *   subfolder.
 * Each row's messages render inline, directly under itself in the tree
 * (see AgentDirectionTree/InboxGroupTree) rather than in a separate pane. */
type SelectedFolder =
  | { kind: "inbox"; agentId: string | null }
  | { kind: "outbox"; agentId: string | null }
  | { kind: "archived"; groupId: string | null };

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
    <div className="flex items-center justify-between gap-2 rounded-md bg-muted/30 px-2.5 py-1.5 text-xs">
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-1.5 text-left hover:underline"
        onClick={() => downloadDemandAttachment(demand.id, attachment)}
      >
        <Paperclip className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate">{attachment.filename}</span>
        <span className="shrink-0 text-muted-foreground">{formatBytes(attachment.size_bytes)}</span>
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

function ReadingPane({ demand, onEdit }: { demand: Demand; onEdit: () => void }) {
  const { t } = useTranslation("demands");
  const updateStatus = useUpdateDemandStatus();
  const deleteDemand = useDeleteDemand();
  const notifyTelegram = useNotifyTelegram();
  const dispatchDemand = useDispatchDemand();
  const dispatchStatus = useDispatchStatus(demand.id, Boolean(demand.dispatch_status));
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (demand.status === "new") {
      updateStatus.mutate({ id: demand.id, status: "read" });
    }
    notifyTelegram.reset();
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
          <Badge variant={STATUS_BADGE[demand.status].variant} className="shrink-0">
            {STATUS_BADGE[demand.status].label}
          </Badge>
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
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={notifyTelegram.isPending}
            onClick={() => notifyTelegram.mutate(demand.id)}
            title="Forward this message to your Telegram"
          >
            {notifyTelegram.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            Notify via Telegram
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5 text-destructive" onClick={() => setConfirmDelete(true)}>
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </Button>
        </div>
        {notifyTelegram.isSuccess && (
          <p className="mt-1.5 text-xs text-emerald-600">Sent to your Telegram.</p>
        )}
        {notifyTelegram.isError && (
          <p className="mt-1.5 text-xs text-destructive">
            {(notifyTelegram.error as Error)?.message ?? "Failed to send to Telegram"}
          </p>
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

        <DispatchMenu
          key={`dispatch-${demand.id}`}
          demand={demand}
          onDispatch={(payload) => dispatchDemand.mutate({ id: demand.id, payload })}
          isPending={dispatchDemand.isPending}
          error={(dispatchDemand.error as Error)?.message}
        />
      </div>
    </div>
  );
}

function DemandListRow({
  demand,
  selected,
  onSelect,
}: {
  demand: Demand;
  selected: boolean;
  onSelect: () => void;
}) {
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
        </span>
        <span className="shrink-0 text-[10px] text-muted-foreground">
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [folder, setFolder] = useState<SelectedFolder>({ kind: "inbox", agentId: null });
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

  function closeForm() {
    setFormMode(null);
    setEditingDemand(null);
  }

  const filtered = useMemo(() => {
    const all = demands ?? [];
    if (folder.kind === "inbox") {
      if (folder.agentId === null) return all.filter((d) => d.status !== "archived");
      if (folder.agentId === NO_AGENT_ID) return all.filter((d) => d.status !== "archived" && !d.target_agent_id);
      return all.filter((d) => d.target_agent_id === folder.agentId);
    }
    if (folder.kind === "outbox") {
      if (folder.agentId === null) return all.filter((d) => d.from_agent_id && d.target_agent_id);
      if (folder.agentId === NO_AGENT_ID) return all.filter((d) => !d.from_agent_id && d.target_agent_id);
      return all.filter((d) => d.from_agent_id === folder.agentId && d.target_agent_id !== null);
    }
    return all.filter((d) => d.status === "archived" && d.group_id === folder.groupId);
  }, [demands, folder]);

  const agentInboxCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of demands ?? []) {
      if (d.target_agent_id) counts[d.target_agent_id] = (counts[d.target_agent_id] ?? 0) + 1;
    }
    return counts;
  }, [demands]);
  const agentOutboxCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of demands ?? []) {
      if (d.from_agent_id && d.target_agent_id) counts[d.from_agent_id] = (counts[d.from_agent_id] ?? 0) + 1;
    }
    return counts;
  }, [demands]);
  const adminInboxCount = useMemo(
    () => (demands ?? []).filter((d) => d.status !== "archived" && !d.target_agent_id).length,
    [demands]
  );
  const adminOutboxCount = useMemo(
    () => (demands ?? []).filter((d) => !d.from_agent_id && d.target_agent_id).length,
    [demands]
  );
  const outboxTotalCount = useMemo(
    () => (demands ?? []).filter((d) => d.from_agent_id && d.target_agent_id).length,
    [demands]
  );

  const archivedCount = (demands ?? []).filter((d) => d.status === "archived").length;
  const archivedCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of demands ?? []) {
      if (d.status === "archived" && d.group_id) counts[d.group_id] = (counts[d.group_id] ?? 0) + 1;
    }
    return counts;
  }, [demands]);
  const unreadCount = (demands ?? []).filter((d) => d.status === "new").length;
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
      : "Nothing dispatched here yet.";

  function renderMessage(demand: Demand) {
    return (
      <DemandListRow
        key={demand.id}
        demand={demand}
        selected={selectedId === demand.id}
        onSelect={() => {
          setSelectedId(demand.id);
          closeForm();
        }}
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          {t("inboxTitle")}
          <InboxIcon className="h-5 w-5" />
          {unreadCount > 0 && <Badge variant="destructive">{unreadCount} {t("new")}</Badge>}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={() => refetch()}
            disabled={isFetching}
            title="Refresh inbox"
          >
            {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </Button>
          <Button size="sm" className="gap-1.5" onClick={openCompose}>
            <Plus className="h-4 w-4" /> {t("newNoteButton")}
          </Button>
          <AssistantToggleButton
            size="sm"
            openTitle="Open the assistant to help triage this message"
          />
        </div>
      </div>

      {isLoading && (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}
      {isError && (
        <div className="flex flex-1 items-center justify-center gap-3 p-6 text-destructive">
          <AlertCircle className="h-5 w-5" />
          <span>Failed to load the inbox: {(error as Error)?.message}</span>
        </div>
      )}

      {!isLoading && !isError && (
        <div className="flex min-h-0 flex-1">
          <div className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-border/60 p-2">
            <AgentDirectionTree
              direction="inbox"
              label={t("incomingFolder")}
              rootCount={unreadCount}
              adminCount={adminInboxCount}
              agentCounts={agentInboxCounts}
              selected={folder.kind === "inbox" ? { agentId: folder.agentId } : undefined}
              onSelectRoot={() => selectFolder({ kind: "inbox", agentId: null })}
              onSelectAgent={(agentId) => selectFolder({ kind: "inbox", agentId })}
              onDropDemand={(demandId) => moveDemand.mutate({ id: demandId, groupId: null, status: "read" })}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
            <AgentDirectionTree
              direction="outbox"
              label="Outbox"
              rootCount={outboxTotalCount}
              adminCount={adminOutboxCount}
              agentCounts={agentOutboxCounts}
              selected={folder.kind === "outbox" ? { agentId: folder.agentId } : undefined}
              onSelectRoot={() => selectFolder({ kind: "outbox", agentId: null })}
              onSelectAgent={(agentId) => selectFolder({ kind: "outbox", agentId })}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
            <InboxGroupTree
              label={t("archivedFolder")}
              groups={groups ?? []}
              selectedGroupId={folder.kind === "archived" ? folder.groupId : undefined}
              onSelectRoot={() => selectFolder({ kind: "archived", groupId: null })}
              onSelectGroup={(id) => selectFolder({ kind: "archived", groupId: id })}
              onDropDemand={(demandId, groupId) => moveDemand.mutate({ id: demandId, groupId, status: "archived" })}
              counts={archivedCounts}
              rootCount={archivedCount}
              messages={filtered}
              renderMessage={renderMessage}
              emptyMessage={emptyMessage}
            />
          </div>

          <div className="min-w-0 flex-1">
            {formMode ? (
              <DemandFormPanel
                demand={editingDemand ?? undefined}
                subject={composeSubject}
                onSubjectChange={setComposeSubject}
                body={composeBody}
                onBodyChange={setComposeBody}
                onClose={closeForm}
              />
            ) : selected ? (
              <ReadingPane demand={selected} onEdit={() => openEdit(selected)} />
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