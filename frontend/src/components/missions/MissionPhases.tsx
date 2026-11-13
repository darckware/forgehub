import { ArrowDown, ArrowUp, CheckCircle2, ChevronDown, ChevronRight, Loader2, Pencil, Trash2, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { MissionPhase } from "@/hooks/useMissions";
import { useMissionPhasesViewModel, type MissionPhasesViewModel } from "@/hooks/useMissionPhasesViewModel";

type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning";
const STATUS_VARIANT: Record<string, BadgeVariant> = {
  planned: "outline", in_progress: "secondary", homologating: "warning", awaiting_approval: "warning",
  approved: "success", returned: "destructive",
};

function PhaseBody({ vm, phase }: { vm: MissionPhasesViewModel; phase: MissionPhase }) {
  const { t } = useTranslation("missions");
  const busy = vm.status === "submitting";
  const editing = vm.editingId === phase.phase_id;
  return <div className="space-y-3 border-t p-3 text-sm">
    {editing ? <div className="space-y-2">
      <label className="block space-y-1"><span>{t("phases.name")}</span>
        <Input className="max-md:text-base" maxLength={120} value={vm.editName}
          onChange={(e) => vm.setEditName(e.target.value)} /></label>
      <label className="block space-y-1"><span>{t("phases.objective")}</span>
        <Textarea className="max-md:text-base" maxLength={20000} value={vm.editObjective}
          onChange={(e) => vm.setEditObjective(e.target.value)} /></label>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={vm.saveEdit} disabled={busy || !vm.editName.trim()}>
          {busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}{t("phases.save")}</Button>
        <Button size="sm" variant="outline" onClick={vm.cancelEdit} disabled={busy}>{t("phases.cancel")}</Button>
      </div>
    </div> : <p className="whitespace-pre-wrap break-words text-muted-foreground">
      {phase.objective || t("phases.noObjective")}</p>}

    {phase.planning_items.length === 0 ? <p className="text-muted-foreground">{t("phases.noPlanning")}</p>
      : <ol className="space-y-2">{phase.planning_items.map((item) => <li key={item.planning_item_id}
        className="rounded-md border p-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium break-words">{item.title}</span>
          {!item.sequenced && <Badge variant="warning">{t("phases.notSequenced")}</Badge>}
        </div>
        <ol className="mt-1 space-y-1">{item.tasks.map((task) => <li key={task.task_id}
          className="flex flex-wrap items-baseline gap-x-2 text-xs">
          <span className="text-muted-foreground">{task.position ?? "–"}.</span>
          <span className="break-words">{task.number != null ? `#${task.number} ` : ""}{task.title}</span>
          <Badge variant="outline">{task.status}</Badge>
          {task.assignee_name && <span className="text-muted-foreground">{task.assignee_name}</span>}
        </li>)}</ol>
      </li>)}</ol>}

    {phase.homologation_summary && <div className="space-y-1 rounded-md border bg-muted/40 p-2"
      data-testid={`phase-homologation-${phase.phase_id}`}>
      <p className="font-medium">{t("phases.homologation", {
        agent: phase.homologator?.name ?? "—",
        verdict: t(`phases.verdict.${phase.homologation_verdict ?? "none"}`) })}</p>
      <p className="whitespace-pre-wrap break-words">{phase.homologation_summary}</p>
      {phase.homologation_evidence && <p className="whitespace-pre-wrap break-all text-xs text-muted-foreground">
        {t("phases.evidence")}: {phase.homologation_evidence}</p>}
    </div>}
    {phase.decision_reason && phase.phase_status === "returned" && <p className="text-xs text-destructive">
      {t("phases.returnedBecause", { reason: phase.decision_reason })}</p>}

    {vm.canDecide && phase.phase_status === "awaiting_approval" && <div className="flex flex-wrap gap-2">
      <Button size="sm" onClick={() => vm.approve(phase)} disabled={busy} className="max-md:h-auto max-md:whitespace-normal">
        {busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-1 h-4 w-4" />}
        {t("phases.approve")}</Button>
      <Button size="sm" variant="outline" onClick={() => vm.askReturn(phase)} disabled={busy}
        className="max-md:h-auto max-md:whitespace-normal">
        <Undo2 className="mr-1 h-4 w-4" />{t("phases.return")}</Button>
    </div>}
  </div>;
}

/** Mission phases strip (docs/architecture/MISSION_PHASES_PLAN.md): numbered
 * phases with their status; each expands to its planning items and tasks. */
export function MissionPhases({ projectId, phases, canEdit, canDecide }: {
  projectId: string; phases: MissionPhase[]; canEdit: boolean; canDecide: boolean;
}) {
  const { t } = useTranslation("missions");
  const vm = useMissionPhasesViewModel({ projectId, phases, canEdit, canDecide });
  const busy = vm.status === "submitting";
  return <section className="space-y-3 rounded-lg border bg-card p-4" aria-labelledby="mission-phases-title">
    <div>
      <h2 id="mission-phases-title" className="font-semibold">{t("phases.title")}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{t("phases.description")}</p>
    </div>
    {vm.phases.length === 0 ? <p className="text-sm text-muted-foreground">{t("phases.empty")}</p>
      : <ol className="space-y-2">{vm.phases.map((phase, index) => {
        const open = vm.expanded.has(phase.phase_id);
        return <li key={phase.phase_id} className="rounded-md border" data-testid={`phase-${phase.position}`}>
          <div className="flex flex-wrap items-center gap-2 p-2">
            <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left max-md:basis-full"
              aria-expanded={open} onClick={() => vm.toggle(phase.phase_id)}>
              {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                {phase.position}</span>
              <span className="min-w-0 break-words font-medium">{phase.name}</span>
            </button>
            <Badge variant={STATUS_VARIANT[phase.phase_status] ?? "outline"}>
              {t(`phases.status.${phase.phase_status}`, { defaultValue: phase.phase_status })}</Badge>
            {vm.canEdit && <div className="flex gap-1">
              <Button size="icon" variant="ghost" aria-label={t("phases.moveUp")} disabled={busy || index === 0}
                onClick={() => vm.move(phase, -1)}><ArrowUp className="h-4 w-4" /></Button>
              <Button size="icon" variant="ghost" aria-label={t("phases.moveDown")}
                disabled={busy || index === vm.phases.length - 1} onClick={() => vm.move(phase, 1)}>
                <ArrowDown className="h-4 w-4" /></Button>
              <Button size="icon" variant="ghost" aria-label={t("phases.edit")} disabled={busy}
                onClick={() => { vm.startEdit(phase); if (!open) vm.toggle(phase.phase_id); }}>
                <Pencil className="h-4 w-4" /></Button>
              <Button size="icon" variant="ghost" aria-label={t("phases.delete")} disabled={busy}
                onClick={() => vm.askDelete(phase)}><Trash2 className="h-4 w-4" /></Button>
            </div>}
          </div>
          {open && <PhaseBody vm={vm} phase={phase} />}
        </li>;
      })}</ol>}

    {vm.canEdit && <form className="space-y-2 border-t pt-3" onSubmit={(e) => { e.preventDefault(); vm.addPhase(); }}>
      <h3 className="text-sm font-semibold">{t("phases.add")}</h3>
      <label className="block space-y-1 text-sm"><span>{t("phases.name")}</span>
        <Input className="max-md:text-base" maxLength={120} value={vm.draftName}
          onChange={(e) => vm.setDraftName(e.target.value)} /></label>
      <label className="block space-y-1 text-sm"><span>{t("phases.objective")}</span>
        <Textarea className="max-md:text-base" maxLength={20000} placeholder={t("phases.objectiveHint")}
          value={vm.draftObjective} onChange={(e) => vm.setDraftObjective(e.target.value)} /></label>
      <Button type="submit" size="sm" disabled={busy || !vm.draftName.trim()}>
        {busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}{t("phases.addButton")}</Button>
    </form>}

    {vm.errorMessage && <p role="alert" className="break-words text-sm text-destructive">{vm.errorMessage}</p>}

    <ConfirmDialog open={vm.pendingDelete != null} title={t("phases.deleteTitle")}
      description={t("phases.deleteBody", { name: vm.pendingDelete?.name ?? "" })}
      confirmLabel={t("phases.delete")} loading={busy}
      onConfirm={vm.confirmDelete} onCancel={vm.cancelDelete} />
    <ConfirmDialog open={vm.returning != null} variant="default" icon="warning" title={t("phases.returnTitle")}
      description={t("phases.returnBody", { name: vm.returning?.name ?? "" })} confirmLabel={t("phases.return")}
      loading={busy} confirmDisabled={!vm.returnReason.trim()} onConfirm={vm.confirmReturn} onCancel={vm.cancelReturn}>
      <label className="block space-y-1 text-sm"><span>{t("phases.returnReason")}</span>
        <Textarea className="max-md:text-base" maxLength={4000} value={vm.returnReason}
          onChange={(e) => vm.setReturnReason(e.target.value)} /></label>
    </ConfirmDialog>
  </section>;
}
