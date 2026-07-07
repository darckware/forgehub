import { useEffect, useState } from "react";
import { AlertCircle, Archive, CheckCheck, Inbox, Loader2, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Markdown } from "@/components/Markdown";
import { ConvertMenu, convertResultMessage } from "@/components/ConvertMenu";
import {
  useConvertDemand,
  useDeleteDemand,
  useDemands,
  useUpdateDemandStatus,
  type Demand,
  type DemandStatus,
} from "@/hooks/useDemands";

const STATUS_BADGE: Record<DemandStatus, { variant: "default" | "secondary" | "success" | "outline"; label: string }> = {
  new: { variant: "default", label: "📬 Nova" },
  read: { variant: "secondary", label: "👁 Lida" },
  converted: { variant: "success", label: "✅ Convertida" },
  archived: { variant: "outline", label: "🗄 Arquivada" },
};

function formatTimestamp(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function DemandRow({ demand, onOpen, open }: { demand: Demand; onOpen: () => void; open: boolean }) {
  const updateStatus = useUpdateDemandStatus();
  const deleteDemand = useDeleteDemand();
  const convertDemand = useConvertDemand();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [convertMessage, setConvertMessage] = useState<string | null>(null);

  useEffect(() => {
    if (open && demand.status === "new") {
      updateStatus.mutate({ id: demand.id, status: "read" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <div className={open ? "bg-accent/40" : undefined}>
      <ConfirmDialog
        open={confirmDelete}
        title={`Excluir "${demand.subject}"`}
        description="Remove a demanda do inbox permanentemente."
        loading={deleteDemand.isPending}
        onConfirm={() => deleteDemand.mutate(demand.id, { onSuccess: () => setConfirmDelete(false) })}
        onCancel={() => setConfirmDelete(false)}
      />
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-accent/30"
      >
        <div className="min-w-0">
          <p className={demand.status === "new" ? "truncate font-semibold" : "truncate font-medium"}>
            {demand.subject}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            de {demand.from_agent} · {formatTimestamp(demand.created_at)}
          </p>
        </div>
        <Badge variant={STATUS_BADGE[demand.status].variant} className="shrink-0">
          {STATUS_BADGE[demand.status].label}
        </Badge>
      </button>
      {open && (
        <div className="space-y-3 border-t border-border/60 px-4 py-3">
          <Markdown content={demand.body} />

          {demand.status === "converted" && demand.converted_reference && (
            <p className="text-xs text-muted-foreground">
              Convertida em <strong>{demand.converted_entity_type}</strong> — {demand.converted_reference}
            </p>
          )}

          {demand.status !== "converted" && (
            <ConvertMenu
              defaultTitle={demand.subject}
              onConvert={(payload) => {
                setConvertMessage(null);
                convertDemand.mutate(
                  { id: demand.id, payload },
                  { onSuccess: (result) => setConvertMessage(convertResultMessage(result)) }
                );
              }}
              isPending={convertDemand.isPending}
              error={(convertDemand.error as Error)?.message}
            />
          )}
          {convertMessage && <p className="text-xs text-emerald-600">{convertMessage}</p>}

          <div className="flex items-center gap-1.5">
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
              className="gap-1.5 text-destructive"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 className="h-3.5 w-3.5" /> Excluir
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DemandsPage() {
  const { data: demands, isLoading, isError, error } = useDemands();
  const updateStatus = useUpdateDemandStatus();
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "unread">("all");

  const filtered = (demands ?? []).filter((d) => filter === "all" || d.status === "new");
  const unreadCount = (demands ?? []).filter((d) => d.status === "new").length;

  return (
    <div className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Inbox className="h-5 w-5" /> Demandas
          {unreadCount > 0 && <Badge variant="destructive">{unreadCount} novas</Badge>}
        </h1>
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

      <div className="flex items-center gap-1">
        <Button size="sm" variant={filter === "all" ? "secondary" : "ghost"} onClick={() => setFilter("all")}>
          Todas
        </Button>
        <Button size="sm" variant={filter === "unread" ? "secondary" : "ghost"} onClick={() => setFilter("unread")}>
          Não lidas
        </Button>
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}
      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Falha ao carregar demandas: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}
      {!isLoading && !isError && filtered.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
            Nenhuma demanda por aqui. Agentes enviam via POST /api/v1/demands/submit.
          </CardContent>
        </Card>
      )}
      {filtered.length > 0 && (
        <Card className="min-h-0 flex-1 overflow-hidden">
          <CardContent className="h-full divide-y divide-border/50 overflow-y-auto p-0">
            {filtered.map((demand) => (
              <DemandRow
                key={demand.id}
                demand={demand}
                open={openId === demand.id}
                onOpen={() => setOpenId(openId === demand.id ? null : demand.id)}
              />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
