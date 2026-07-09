import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Archive,
  Bot,
  CheckCheck,
  CheckCircle2,
  Download,
  Inbox as InboxIcon,
  Loader2,
  Paperclip,
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
import { ConvertMenu } from "@/components/ConvertMenu";
import { ComposeDemandDialog } from "@/pages/demands/ComposeDemandDialog";
import { useAssistantContext } from "@/hooks/useAssistant";
import { useAssistantStore } from "@/store/assistantStore";
import { DEMAND_DRAG_MIME, InboxGroupTree } from "@/components/InboxGroupTree";
import {
  CONVERT_TARGET_LABELS,
  downloadDemandAttachment,
  useConvertDemand,
  useDeleteDemand,
  useDeleteDemandAttachment,
  useDemandGroups,
  useDemands,
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

/** Which folder the message list/reading pane are scoped to -- "inbox" is
 * Incoming (everything not archived); "archived" is the Archived tree,
 * where groupId null means the Archived root (uncategorized) and a
 * string means a specific user-created subfolder. */
type SelectedFolder = { kind: "inbox" } | { kind: "archived"; groupId: string | null };

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

function ReadingPane({ demand }: { demand: Demand }) {
  const updateStatus = useUpdateDemandStatus();
  const deleteDemand = useDeleteDemand();
  const convertDemand = useConvertDemand();
  const notifyTelegram = useNotifyTelegram();
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
          <h2 className="text-lg font-semibold leading-tight">{demand.subject}</h2>
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

        {demand.status !== "converted" && (
          <ConvertMenu
            key={demand.id}
            defaultTitle={demand.subject}
            onConvert={(payload) => convertDemand.mutate({ id: demand.id, payload })}
            isPending={convertDemand.isPending}
            error={(convertDemand.error as Error)?.message}
          />
        )}
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
      <span className="truncate text-xs text-muted-foreground">{demand.subject}</span>
      {demand.attachments.length > 0 && (
        <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
          <Paperclip className="h-3 w-3" /> {demand.attachments.length}
        </span>
      )}
    </button>
  );
}

export default function DemandsPage() {
  const { data: demands, isLoading, isError, error, refetch, isFetching } = useDemands();
  const { data: groups } = useDemandGroups();
  const updateStatus = useUpdateDemandStatus();
  const moveDemand = useMoveDemand();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [folder, setFolder] = useState<SelectedFolder>({ kind: "inbox" });
  const [composeOpen, setComposeOpen] = useState(false);
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [inboxDragOver, setInboxDragOver] = useState(false);
  const assistantOpen = useAssistantStore((s) => s.open);
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);

  const filtered = useMemo(() => {
    const all = demands ?? [];
    if (folder.kind === "inbox") {
      return all.filter((d) => d.status !== "archived" && (filter === "all" || d.status === "new"));
    }
    return all.filter((d) => d.status === "archived" && d.group_id === folder.groupId);
  }, [demands, folder, filter]);

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
    form: composeOpen
      ? {
          description: "New Inbox note",
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
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <ComposeDemandDialog
        open={composeOpen}
        onClose={() => setComposeOpen(false)}
        subject={composeSubject}
        onSubjectChange={setComposeSubject}
        body={composeBody}
        onBodyChange={setComposeBody}
      />

      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <InboxIcon className="h-5 w-5" /> Inbox
          {unreadCount > 0 && <Badge variant="destructive">{unreadCount} new</Badge>}
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
          <Button size="sm" className="gap-1.5" onClick={() => setComposeOpen(true)}>
            <Plus className="h-4 w-4" /> New note
          </Button>
          <Button
            size="sm"
            variant={assistantOpen ? "secondary" : "outline"}
            className="gap-1.5"
            title={assistantOpen ? "Close assistant" : "Open the assistant to help triage this message"}
            onClick={() => setAssistantOpen(!assistantOpen)}
          >
            <Bot className="h-4 w-4" /> Assistant
          </Button>
        </div>
      </div>

      {folder.kind === "inbox" && (
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-2">
          <div className="flex items-center gap-1">
            <Button size="sm" variant={filter === "all" ? "secondary" : "ghost"} onClick={() => setFilter("all")}>
              All
            </Button>
            <Button size="sm" variant={filter === "unread" ? "secondary" : "ghost"} onClick={() => setFilter("unread")}>
              Unread
            </Button>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={unreadCount === 0}
            onClick={() => {
              (demands ?? [])
                .filter((d) => d.status === "new")
                .forEach((d) => updateStatus.mutate({ id: d.id, status: "read" }));
            }}
          >
            <CheckCheck className="h-4 w-4" /> Mark all as read
          </Button>
        </div>
      )}

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
          <div className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-border/60">
            <div className="shrink-0 border-b border-border/60 p-2">
              <button
                type="button"
                onClick={() => selectFolder({ kind: "inbox" })}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                }}
                onDragEnter={(e) => {
                  e.preventDefault();
                  setInboxDragOver(true);
                }}
                onDragLeave={() => setInboxDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setInboxDragOver(false);
                  const demandId = e.dataTransfer.getData(DEMAND_DRAG_MIME);
                  if (demandId) moveDemand.mutate({ id: demandId, groupId: null, status: "read" });
                }}
                className={cn(
                  "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm font-medium",
                  inboxDragOver
                    ? "bg-accent ring-1 ring-inset ring-primary"
                    : folder.kind === "inbox"
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <InboxIcon className="h-3.5 w-3.5 shrink-0" />
                <span className="flex-1">Incoming</span>
                {unreadCount > 0 && <span className="text-[10px] text-muted-foreground">{unreadCount}</span>}
              </button>
              <InboxGroupTree
                groups={groups ?? []}
                selectedGroupId={folder.kind === "archived" ? folder.groupId : undefined}
                onSelectRoot={() => selectFolder({ kind: "archived", groupId: null })}
                onSelectGroup={(id) => selectFolder({ kind: "archived", groupId: id })}
                onDropDemand={(demandId, groupId) => moveDemand.mutate({ id: demandId, groupId, status: "archived" })}
                counts={archivedCounts}
              />
              {archivedCount > 0 && folder.kind !== "archived" && (
                <p className="px-2 pt-1 text-[10px] text-muted-foreground">{archivedCount} archived in total</p>
              )}
            </div>

            <div className="min-h-0 flex-1">
              {filtered.length === 0 && (
                <p className="p-6 text-center text-sm italic text-muted-foreground">
                  {folder.kind === "inbox"
                    ? 'Nothing here yet. Agents submit via /demands/submit, or click "New note".'
                    : "No archived messages here yet. Drag a message from Incoming into this folder."}
                </p>
              )}
              {filtered.map((demand) => (
                <DemandListRow
                  key={demand.id}
                  demand={demand}
                  selected={selectedId === demand.id}
                  onSelect={() => setSelectedId(demand.id)}
                />
              ))}
            </div>
          </div>

          <div className="min-w-0 flex-1">
            {selected ? (
              <ReadingPane demand={selected} />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Select a message to read.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
