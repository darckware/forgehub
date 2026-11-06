import { Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useMaintenanceProposalsViewModel } from "@/hooks/useMaintenanceProposalsViewModel";

export function MaintenanceProposalsCard() {
  const {t, i18n} = useTranslation("remoteAccess");
  const vm = useMaintenanceProposalsViewModel();
  const p = vm.selected;
  return <Card className="min-w-0">
    <CardHeader className="flex flex-row items-center justify-between gap-3">
      <CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4" />{t("proposals.title")}</CardTitle>
      <Button size="sm" variant="ghost" onClick={vm.refresh} aria-label={t("refresh")}><RefreshCw className="h-4 w-4" /></Button>
    </CardHeader>
    <CardContent className="space-y-3">
      <p className="text-xs text-muted-foreground">{t("proposals.help")}</p>
      {vm.status === "loading" && <Loader2 className="h-4 w-4 motion-safe:animate-spin" role="status" aria-label={t("loading")} />}
      {vm.error && !p && <p role="alert" className="text-sm text-destructive">{vm.error}</p>}
      {!vm.proposals.length && vm.status === "idle" && <p className="text-sm text-muted-foreground">{t("proposals.empty")}</p>}
      <ul className="divide-y rounded-md border border-border">
        {vm.proposals.map(row => <li key={row.id} className="flex min-w-0 flex-wrap items-center gap-2 p-3 text-sm">
          <span className="min-w-0 flex-1 break-words">#{row.message_number} · {row.reason}</span>
          <Badge variant={row.status === "proposed" ? "warning" : "secondary"}>{t(`proposals.states.${row.status}`)}</Badge>
          <Button variant="outline" size="sm" onClick={() => vm.review(row,"approved")}>{t("proposals.review")}</Button>
        </li>)}
      </ul>
    </CardContent>
    <ConfirmDialog open={!!p} title={t("proposals.reviewTitle")} description={t("proposals.help")}
      readOnly={p?.status !== "proposed"} variant={vm.decision === "rejected" ? "destructive" : "default"}
      confirmLabel={t(vm.decision === "approved" ? "proposals.approve" : "proposals.reject")}
      loading={vm.status === "submitting"} dismissDisabled={vm.status === "submitting"}
      confirmDisabled={vm.decision === "rejected" && !vm.reason.trim()} error={vm.error}
      onConfirm={() => void vm.confirm()} onCancel={vm.close}>
      {p && <div className="min-w-0 space-y-3 text-sm">
        <dl className="space-y-2 break-words">
          <div><dt className="font-medium">{t("proposals.machines")}</dt><dd>{p.machines.map(m => m.name).join(", ")}</dd></div>
          <div><dt className="font-medium">{t("proposals.risk")}</dt><dd>{p.risk} · {p.shell} · {p.timeout_seconds}s</dd></div>
          <div><dt className="font-medium">{t("proposals.reason")}</dt><dd>{p.reason}</dd></div>
          <div><dt className="font-medium">{t("proposals.effect")}</dt><dd>{p.expected_effect}</dd></div>
          <div><dt className="font-medium">{t("proposals.rollback")}</dt><dd className="whitespace-pre-wrap">{p.rollback}</dd></div>
          <div><dt className="font-medium">SHA-256</dt><dd className="break-all font-mono text-xs">{p.content_hash}</dd></div>
        </dl>
        {p.requires_elevation && <p role="note" className="rounded border border-warning/40 bg-warning/10 p-3 font-medium">{t("proposals.elevation")}</p>}
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted p-3 font-mono text-xs">{p.content}</pre>
        {p.parameters.map(param => <p key={param.name} className="break-all font-mono text-xs">{param.name}: vault_secret={param.vault_secret}{param.vault_field ? ` (${param.vault_field})` : ""}</p>)}
        {p.expires_at && <p>{t("proposals.expires", {date: new Date(p.expires_at).toLocaleString(i18n.language)})}</p>}
        {p.decision_reason && <p className="break-words">{p.decision_reason}</p>}
        {p.status === "proposed" && <div className="space-y-2">
          <Button size="sm" variant="outline" disabled={vm.status === "submitting"}
            onClick={() => vm.review(p, vm.decision === "approved" ? "rejected" : "approved")}>
            {t(vm.decision === "approved" ? "proposals.reject" : "proposals.approve")}
          </Button>
          {vm.decision === "rejected" && <div><label htmlFor="proposal-rejection" className="block font-medium">{t("proposals.rejectionReason")}</label>
            <textarea id="proposal-rejection" className="mt-1 min-h-24 w-full resize-none rounded-md border border-border bg-background p-2 text-base"
              value={vm.reason} onChange={e => vm.setReason(e.target.value)} disabled={vm.status === "submitting"} />
          </div>}
        </div>}
      </div>}
    </ConfirmDialog>
  </Card>;
}
