import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Textarea } from "@/components/ui/textarea";
import { decisionKey, useMissionDecisionsViewModel } from "@/hooks/useMissionDecisionsViewModel";
import { useAuthStore } from "@/store/authStore";

/** "Decisões de missão": plan approvals and phases awaiting Marcelo, on top of
 * Pessoal → Tarefas dos agentes. Hidden while nothing is pending. */
export function MissionDecisionsCard() {
  const { t, i18n } = useTranslation("personal");
  const isAdmin = useAuthStore((s) => s.user?.is_admin ?? false);
  const vm = useMissionDecisionsViewModel(isAdmin);
  if (!isAdmin || !vm.visible) return null;
  const date = (value: string | null) => value
    ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
  const pending = vm.pending;
  const rejectLabel = (kind: string) => t(kind === "plan_approval" ? "missionDecisions.reject" : "missionDecisions.return");

  return <section aria-label={t("missionDecisions.title")} className="space-y-3 rounded-md border border-amber-500/40 p-4">
    <h3 className="font-semibold">{vm.loadFailed && !vm.items.length ? t("missionDecisions.title") : t("missionDecisions.heading", { count: vm.items.length })}</h3>
    <p className="text-sm text-muted-foreground">{t("missionDecisions.description")}</p>
    {vm.loadFailed && <div role="alert" className="flex flex-wrap items-center gap-2 text-sm text-destructive">
      <span>{t("missionDecisions.loadError")}</span>
      <Button size="sm" variant="outline" onClick={vm.retry}>{t("missionDecisions.retry")}</Button>
    </div>}
    <ul className="space-y-3">
      {vm.items.map((item) => <li key={decisionKey(item)} className="space-y-2 rounded-md border p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="warning">{t(`missionDecisions.kinds.${item.kind}`)}</Badge>
          <span className="break-words font-medium">{item.title}</span>
        </div>
        <p className="break-words text-sm text-muted-foreground">
          {item.mission_name} · {date(item.requested_at)}{item.requested_by ? ` · ${item.requested_by}` : ""}
        </p>
        {item.summary && <p className="whitespace-pre-wrap break-words text-sm">{item.summary}</p>}
        {item.homologation_evidence.length > 0 && <ul className="list-disc pl-5 text-xs text-muted-foreground">
          {item.homologation_evidence.map((ref) => <li key={ref} className="break-all">{ref}</li>)}
        </ul>}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => vm.ask(item, "approve")}>{t("missionDecisions.approve")}</Button>
          <Button size="sm" variant="outline" onClick={() => vm.ask(item, "reject")}>{rejectLabel(item.kind)}</Button>
          <Link className="text-sm text-primary underline" to={item.link}>{t("missionDecisions.openMission")}</Link>
        </div>
      </li>)}
    </ul>
    <ConfirmDialog open={Boolean(pending)} variant={pending?.choice === "reject" ? "destructive" : "default"}
      icon="warning"
      title={pending ? (pending.choice === "approve" ? t("missionDecisions.approve") : rejectLabel(pending.item.kind)) : ""}
      description={pending ? `${pending.item.mission_name} · ${pending.item.title}` : undefined}
      confirmLabel={pending ? (pending.choice === "approve" ? t("missionDecisions.approve") : rejectLabel(pending.item.kind)) : undefined}
      loading={vm.status === "submitting"} error={vm.errorMessage}
      confirmDisabled={vm.reasonRequired && !vm.reason.trim()}
      onConfirm={vm.confirm} onCancel={vm.cancel}>
      <label className="block space-y-1 text-sm">
        {t(vm.reasonRequired ? "missionDecisions.reasonRequired" : "missionDecisions.reasonOptional")}
        <Textarea className="resize-none max-md:text-base" value={vm.reason} onChange={(e) => vm.setReason(e.target.value)} />
      </label>
    </ConfirmDialog>
  </section>;
}
