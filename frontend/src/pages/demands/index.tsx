import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Archive,
  BookOpen,
  CheckCheck,
  Download,
  FolderKanban,
  Inbox as InboxIcon,
  Layers,
  Loader2,
  Paperclip,
  Plus,
  Send,
  Trash2,
  User,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/Markdown";
import { ConvertMenu, convertResultMessage } from "@/components/ConvertMenu";
import { ComposeDemandDialog } from "@/pages/demands/ComposeDemandDialog";
import {
  downloadDemandAttachment,
  useConvertDemand,
  useDeleteDemand,
  useDeleteDemandAttachment,
  useDemands,
  useNotifyTelegram,
  useUpdateDemandStatus,
  type ConvertTarget,
  type Demand,
  type DemandStatus,
} from "@/hooks/useDemands";

const STATUS_BADGE: Record<DemandStatus, { variant: "default" | "secondary" | "success" | "outline"; label: string }> = {
  new: { variant: "default", label: "Nova" },
  read: { variant: "secondary", label: "Lida" },
  converted: { variant: "success", label: "Convertida" },
  archived: { variant: "outline", label: "Arquivada" },
};

// Native HTML5 drag-and-drop mime type carrying the dragged demand's id --
// scoped to this page only (not a shared app-wide DnD contract).
const DND_TYPE = "application/x-forgehub-demand-id";

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

/** Clusters demands sharing an identical subject into threads, preserving
 * the incoming (already created_at desc) order for both thread position
 * and the items within each thread -- "consolidando conceitos": the same
 * subject recurring over time is a thread, not unrelated rows. */
function groupBySubject(demands: Demand[]): { subject: string; items: Demand[] }[] {
  const order: string[] = [];
  const bySubject = new Map<string, Demand[]>();
  for (const d of demands) {
    if (!bySubject.has(d.subject)) {
      order.push(d.subject);
      bySubject.set(d.subject, []);
    }
    bySubject.get(d.subject)!.push(d);
  }
  return order.map((subject) => ({ subject, items: bySubject.get(subject)! }));
}

function DropTarget({
  icon: Icon,
  label,
  onDropDemand,
}: {
  icon: typeof FolderKanban;
  label: string;
  onDropDemand: (demandId: string) => void;
}) {
  const [active, setActive] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setActive(true);
      }}
      onDragLeave={() => setActive(false)}
      onDrop={(e) => {
        e.preventDefault();
        setActive(false);
        const id = e.dataTransfer.getData(DND_TYPE);
        if (id) onDropDemand(id);
      }}
      className={cn(
        "flex items-center gap-1.5 rounded-md border border-dashed px-2.5 py-1.5 text-xs text-muted-foreground transition-colors",
        active ? "border-primary bg-primary/10 text-foreground" : "border-border"
      )}
      title={`Arraste uma mensagem aqui para: ${label}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </div>
  );
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
          title="Baixar"
        >
          <Download className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => deleteAttachment.mutate({ demandId: demand.id, attachmentId: attachment.id })}
          title="Remover anexo"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

function ReadingPane({
  demand,
  pendingConvertTarget,
  onConsumeConvertTarget,
}: {
  demand: Demand;
  pendingConvertTarget: ConvertTarget | null;
  onConsumeConvertTarget: () => void;
}) {
  const updateStatus = useUpdateDemandStatus();
  const deleteDemand = useDeleteDemand();
  const convertDemand = useConvertDemand();
  const notifyTelegram = useNotifyTelegram();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [convertMessage, setConvertMessage] = useState<string | null>(null);

  useEffect(() => {
    if (demand.status === "new") {
      updateStatus.mutate({ id: demand.id, status: "read" });
    }
    setConvertMessage(null);
    notifyTelegram.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demand.id]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ConfirmDialog
        open={confirmDelete}
        title={`Excluir "${demand.subject}"`}
        description="Remove a mensagem do inbox permanentemente."
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
        <div className="mt-3 flex items-center gap-1.5">
          {demand.status !== "archived" && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => updateStatus.mutate({ id: demand.id, status: "archived" })}
            >
              <Archive className="h-3.5 w-3.5" /> Arquivar
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={notifyTelegram.isPending}
            onClick={() => notifyTelegram.mutate(demand.id)}
            title="Encaminha esta mensagem para o seu Telegram"
          >
            {notifyTelegram.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Send className="h-3.5 w-3.5" />
            )}
            Avisar no Telegram
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5 text-destructive" onClick={() => setConfirmDelete(true)}>
            <Trash2 className="h-3.5 w-3.5" /> Excluir
          </Button>
        </div>
        {notifyTelegram.isSuccess && (
          <p className="mt-1.5 text-xs text-emerald-600">Enviado para o seu Telegram.</p>
        )}
        {notifyTelegram.isError && (
          <p className="mt-1.5 text-xs text-destructive">
            {(notifyTelegram.error as Error)?.message ?? "Falha ao enviar para o Telegram"}
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
        <Markdown content={demand.body} />

        {demand.attachments.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase text-muted-foreground">Anexos</p>
            {demand.attachments.map((a) => (
              <AttachmentRow key={a.id} demand={demand} attachment={a} />
            ))}
          </div>
        )}

        {demand.status === "converted" && demand.converted_reference && (
          <p className="text-xs text-muted-foreground">
            Convertida em <strong>{demand.converted_entity_type}</strong> — {demand.converted_reference}
          </p>
        )}

        {demand.status !== "converted" && (
          <ConvertMenu
            key={`${demand.id}-${pendingConvertTarget ?? ""}`}
            defaultTitle={demand.subject}
            initialTarget={pendingConvertTarget ?? undefined}
            onConvert={(payload) => {
              setConvertMessage(null);
              convertDemand.mutate(
                { id: demand.id, payload },
                { onSuccess: (result) => setConvertMessage(convertResultMessage(result)) }
              );
              onConsumeConvertTarget();
            }}
            isPending={convertDemand.isPending}
            error={(convertDemand.error as Error)?.message}
          />
        )}
        {convertMessage && <p className="text-xs text-emerald-600">{convertMessage}</p>}
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
        e.dataTransfer.setData(DND_TYPE, demand.id);
        e.dataTransfer.effectAllowed = "copy";
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
  const { data: demands, isLoading, isError, error } = useDemands();
  const updateStatus = useUpdateDemandStatus();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [grouped, setGrouped] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [pendingConvertTarget, setPendingConvertTarget] = useState<ConvertTarget | null>(null);

  const filtered = useMemo(
    () => (demands ?? []).filter((d) => filter === "all" || d.status === "new"),
    [demands, filter]
  );
  const groups = useMemo(() => (grouped ? groupBySubject(filtered) : null), [grouped, filtered]);
  const unreadCount = (demands ?? []).filter((d) => d.status === "new").length;
  const selected = (demands ?? []).find((d) => d.id === selectedId) ?? null;

  function handleDrop(demandId: string, target: ConvertTarget) {
    setSelectedId(demandId);
    setPendingConvertTarget(target);
  }

  const renderRow = (demand: Demand) => (
    <DemandListRow
      key={demand.id}
      demand={demand}
      selected={selectedId === demand.id}
      onSelect={() => {
        setSelectedId(demand.id);
        setPendingConvertTarget(null);
      }}
    />
  );

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <ComposeDemandDialog open={composeOpen} onClose={() => setComposeOpen(false)} />

      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <InboxIcon className="h-5 w-5" /> Inbox
          {unreadCount > 0 && <Badge variant="destructive">{unreadCount} novas</Badge>}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <DropTarget icon={BookOpen} label="Base de Conhecimento" onDropDemand={(id) => handleDrop(id, "knowledge_base")} />
          <DropTarget icon={FolderKanban} label="Projeto" onDropDemand={(id) => handleDrop(id, "project_doc")} />
          <Button size="sm" className="gap-1.5" onClick={() => setComposeOpen(true)}>
            <Plus className="h-4 w-4" /> Nova nota
          </Button>
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-2">
        <div className="flex items-center gap-1">
          <Button size="sm" variant={filter === "all" ? "secondary" : "ghost"} onClick={() => setFilter("all")}>
            Todas
          </Button>
          <Button size="sm" variant={filter === "unread" ? "secondary" : "ghost"} onClick={() => setFilter("unread")}>
            Não lidas
          </Button>
          <Button
            size="sm"
            variant={grouped ? "secondary" : "ghost"}
            className="gap-1.5"
            onClick={() => setGrouped((v) => !v)}
          >
            <Layers className="h-3.5 w-3.5" /> Agrupar por assunto
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
          <CheckCheck className="h-4 w-4" /> Marcar todas como lidas
        </Button>
      </div>

      {isLoading && (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}
      {isError && (
        <div className="flex flex-1 items-center justify-center gap-3 p-6 text-destructive">
          <AlertCircle className="h-5 w-5" />
          <span>Falha ao carregar o inbox: {(error as Error)?.message}</span>
        </div>
      )}

      {!isLoading && !isError && (
        <div className="flex min-h-0 flex-1">
          <div className="w-80 shrink-0 overflow-y-auto border-r border-border/60">
            {filtered.length === 0 && (
              <p className="p-6 text-center text-sm italic text-muted-foreground">
                Nada por aqui. Agentes enviam via /demands/submit, ou clique em "Nova nota".
              </p>
            )}
            {groups
              ? groups.map((group) => (
                  <div key={group.subject}>
                    <div className="flex items-center justify-between bg-muted/40 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                      <span className="truncate">{group.subject}</span>
                      <span>{group.items.length}</span>
                    </div>
                    {group.items.map(renderRow)}
                  </div>
                ))
              : filtered.map(renderRow)}
          </div>

          <div className="min-w-0 flex-1">
            {selected ? (
              <ReadingPane
                demand={selected}
                pendingConvertTarget={pendingConvertTarget}
                onConsumeConvertTarget={() => setPendingConvertTarget(null)}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Selecione uma mensagem para ler.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
