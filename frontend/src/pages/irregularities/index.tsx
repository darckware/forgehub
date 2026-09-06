import { useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  useIrregularities,
  useUpdateIrregularityStatus,
  type Irregularity,
} from "@/hooks/useIrregularities";

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "open", label: "Open" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
];

const SEVERITY_OPTIONS: { value: string; label: string }[] = [
  { value: "all", label: "All severities" },
  { value: "critical", label: "Critical" },
  { value: "warning", label: "Warning" },
  { value: "info", label: "Info" },
];

function severityBadgeVariant(severity: Irregularity["severity"]) {
  if (severity === "critical") return "destructive" as const;
  if (severity === "warning") return "default" as const;
  return "secondary" as const;
}

export default function IrregularitiesPage() {
  const [statusFilter, setStatusFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [resolveTarget, setResolveTarget] = useState<Irregularity | null>(null);

  const { data: irregularities, isLoading } = useIrregularities({
    status_filter: statusFilter === "all" ? undefined : statusFilter,
    severity: severityFilter === "all" ? undefined : severityFilter,
  });
  const updateStatus = useUpdateIrregularityStatus();

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <AlertTriangle className="h-5 w-5" />
            Irregularities
          </h1>
          <p className="text-sm text-muted-foreground">
            Client workstation monitoring findings requiring review.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-4">
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-auto"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <Select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="w-auto"
        >
          {SEVERITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Severity</th>
              <th className="px-4 py-2">Detail</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Detected at</th>
              <th className="px-4 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                </td>
              </tr>
            )}
            {!isLoading && (irregularities ?? []).length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center italic text-muted-foreground">
                  No irregularities found.
                </td>
              </tr>
            )}
            {(irregularities ?? []).map((irregularity) => (
              <tr key={irregularity.id} className="hover:bg-accent/30">
                <td className="px-4 py-2">
                  <Badge variant={severityBadgeVariant(irregularity.severity)} className="capitalize">
                    {irregularity.severity}
                  </Badge>
                </td>
                <td className="max-w-md px-4 py-2 text-muted-foreground" title={irregularity.detail}>
                  {irregularity.detail}
                </td>
                <td className="px-4 py-2">
                  <Badge variant="outline" className="capitalize">
                    {irregularity.status}
                  </Badge>
                </td>
                <td className="px-4 py-2 font-mono text-xs text-muted-foreground">
                  {new Date(irregularity.detected_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-emerald-600 hover:text-emerald-500"
                    onClick={() => setResolveTarget(irregularity)}
                    disabled={irregularity.status === "resolved" || updateStatus.isPending}
                    title="Marcar como tratada"
                  >
                    {updateStatus.isPending && resolveTarget?.id === irregularity.id ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    Marcar como tratada
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={resolveTarget !== null}
        variant="default"
        icon="warning"
        title="Marcar como tratada"
        description={resolveTarget ? `Marcar "${resolveTarget.detail}" como resolvida?` : ""}
        loading={updateStatus.isPending}
        onConfirm={() => {
          if (!resolveTarget) return;
          updateStatus.mutate(
            { id: resolveTarget.id, status: "resolved" },
            { onSuccess: () => setResolveTarget(null) }
          );
        }}
        onCancel={() => setResolveTarget(null)}
      />
    </div>
  );
}
