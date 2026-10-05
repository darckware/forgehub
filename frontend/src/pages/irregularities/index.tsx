import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { useWorkstations } from "@/hooks/useWorkstations";
import { useClients } from "@/hooks/useClients";

const STATUS_OPTIONS = ["all", "open", "acknowledged", "resolved"] as const;

const SEVERITY_OPTIONS = ["all", "critical", "warning", "info"] as const;

// No dedicated enum-listing endpoint for this -- mirrors the fixed
// IRREGULARITY_RULE_KEYS tuple in backend/app/db/models/client.py.
const RULE_KEY_OPTIONS = ["all", "disk_space_low", "backup_stale", "unauthorized_remote_tool", "critical_service_down", "collection_failed", "agent_unreachable"] as const;

function severityBadgeVariant(severity: Irregularity["severity"]) {
  if (severity === "critical") return "destructive" as const;
  if (severity === "warning") return "default" as const;
  return "secondary" as const;
}

export default function IrregularitiesPage() {
  const { t, i18n } = useTranslation("irregularities");
  const [statusFilter, setStatusFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [ruleKeyFilter, setRuleKeyFilter] = useState("all");
  const [resolveTarget, setResolveTarget] = useState<Irregularity | null>(null);

  const { data: irregularities, isLoading } = useIrregularities({
    status_filter: statusFilter === "all" ? undefined : statusFilter,
    severity: severityFilter === "all" ? undefined : severityFilter,
  });
  const updateStatus = useUpdateIrregularityStatus();

  // Simple client-side join for workstation/client context -- no dedicated
  // backend join endpoint for this screen.
  const { data: workstations } = useWorkstations();
  const { data: clients } = useClients();

  const workstationById = useMemo(() => {
    const map = new Map<string, NonNullable<typeof workstations>[number]>();
    for (const workstation of workstations ?? []) {
      map.set(workstation.id, workstation);
    }
    return map;
  }, [workstations]);

  const clientById = useMemo(() => {
    const map = new Map<string, NonNullable<typeof clients>[number]>();
    for (const client of clients ?? []) {
      map.set(client.id, client);
    }
    return map;
  }, [clients]);

  const visibleIrregularities = useMemo(
    () =>
      (irregularities ?? []).filter(
        (irregularity) => ruleKeyFilter === "all" || irregularity.rule_key === ruleKeyFilter
      ),
    [irregularities, ruleKeyFilter]
  );

  return (
    <div className="space-y-6 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <AlertTriangle className="h-5 w-5" />
            {t("title")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("description")}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-4">
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-auto"
        >
          {STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {t(`filters.status.${status}`)}
            </option>
          ))}
        </Select>
        <Select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="w-auto"
        >
          {SEVERITY_OPTIONS.map((severity) => (
            <option key={severity} value={severity}>
              {t(`filters.severity.${severity}`)}
            </option>
          ))}
        </Select>
        <Select
          value={ruleKeyFilter}
          onChange={(e) => setRuleKeyFilter(e.target.value)}
          className="w-auto"
        >
          {RULE_KEY_OPTIONS.map((rule) => (
            <option key={rule} value={rule}>
              {t(`filters.rule.${rule}`)}
            </option>
          ))}
        </Select>
      </div>

      {/* overflow-x-auto, not hidden: on a phone the columns past the first
          two were cut off with no way to reach them. */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-2">{t("table.workstationClient")}</th>
              <th className="px-4 py-2">{t("table.rule")}</th>
              <th className="px-4 py-2">{t("table.severity")}</th>
              <th className="px-4 py-2">{t("table.detail")}</th>
              <th className="px-4 py-2">{t("table.status")}</th>
              <th className="px-4 py-2">{t("table.detectedAt")}</th>
              <th className="px-4 py-2 text-right">{t("table.actions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-muted-foreground">
                  <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                </td>
              </tr>
            )}
            {!isLoading && visibleIrregularities.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center italic text-muted-foreground">
                  {t("empty")}
                </td>
              </tr>
            )}
            {visibleIrregularities.map((irregularity) => {
              const workstation = workstationById.get(irregularity.workstation_id);
              const client = workstation ? clientById.get(workstation.client_id) : undefined;
              return (
              <tr key={irregularity.id} className="hover:bg-accent/30">
                <td className="px-4 py-2">
                  <div className="font-medium">{workstation?.hostname ?? irregularity.workstation_id}</div>
                  <div className="text-xs text-muted-foreground">{client?.name ?? "—"}</div>
                </td>
                <td className="px-4 py-2 text-xs text-muted-foreground">{t(`filters.rule.${irregularity.rule_key}`, { defaultValue: irregularity.rule_key })}</td>
                <td className="px-4 py-2">
                  <Badge variant={severityBadgeVariant(irregularity.severity)} className="capitalize">
                    {t(`filters.severity.${irregularity.severity}`, { defaultValue: irregularity.severity })}
                  </Badge>
                </td>
                <td className="max-w-md px-4 py-2 text-muted-foreground" title={irregularity.detail}>
                  {irregularity.detail}
                </td>
                <td className="px-4 py-2">
                  <Badge variant="outline" className="capitalize">
                    {t(`filters.status.${irregularity.status}`, { defaultValue: irregularity.status })}
                  </Badge>
                </td>
                <td className="px-4 py-2 font-mono text-xs text-muted-foreground">
                  {new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(irregularity.detected_at))}
                </td>
                <td className="px-4 py-2 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-emerald-600 hover:text-emerald-500"
                    onClick={() => setResolveTarget(irregularity)}
                    disabled={irregularity.status === "resolved" || updateStatus.isPending}
                    title={t("resolve")}
                  >
                    {updateStatus.isPending && resolveTarget?.id === irregularity.id ? (
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                    )}
                    {t("resolve")}
                  </Button>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={resolveTarget !== null}
        variant="default"
        icon="warning"
        title={t("resolve")}
        description={resolveTarget ? t("confirmResolve", { detail: resolveTarget.detail }) : ""}
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
