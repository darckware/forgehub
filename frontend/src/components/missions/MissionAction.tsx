import { useEffect, useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { MissionExecutionsViewModel } from "@/hooks/useMissionExecutionsViewModel";

/** Modal policy (UX-CONTRACT.md "Overlays and feedback", 2026-11-02): the
 * input an action needs (reason, agent, time, decision) is typed in this
 * inline section of the page, never inside a modal. The modal below only
 * confirms. */

function useActionText(vm: MissionExecutionsViewModel) {
  const { t } = useTranslation("missions");
  const pending = vm.pending;
  const task = vm.pendingTask;
  const item = pending?.itemId ? vm.board?.planning?.pending_decisions.find((d) => d.item_id === pending.itemId) : undefined;
  const label = pending ? t(`actions.${pending.kind}`) : "";
  const description = task ? t("actions.confirmTask", { number: task.number, title: task.title })
    : item ? item.text : t("actions.confirmMission", { name: vm.board?.mission.name ?? "" });
  return { label, description };
}

/** The action's form, shown on the page while the action is `editing` (and
 * kept visible, read-only, while it is confirmed or submitted). */
export function MissionActionForm({ vm }: { vm: MissionExecutionsViewModel }) {
  const { t } = useTranslation("missions");
  const ref = useRef<HTMLElement>(null);
  const reasonId = useId();
  const agentId = useId();
  const whenId = useId();
  const decisionId = useId();
  const pending = vm.pending;
  const visible = Boolean(pending && vm.hasFields);
  const { label, description } = useActionText(vm);

  useEffect(() => {
    if (visible) ref.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [visible, pending?.kind, pending?.taskId, pending?.itemId]);

  if (!pending || !vm.hasFields) return null;
  const locked = vm.status !== "editing";
  const task = vm.pendingTask;
  const candidates = pending.kind === "assign" ? task?.executor_candidates ?? []
    : pending.kind === "request_review" ? (task?.reviewer_candidates ?? []).filter((c) => c.eligible) : [];

  return (
    <section ref={ref} aria-labelledby={`${reasonId}-title`} data-testid="mission-action-form"
      className="space-y-3 rounded-lg border border-primary/40 bg-muted/30 p-4 text-sm">
      <div>
        <h2 id={`${reasonId}-title`} className="font-semibold">{label}</h2>
        <p className="break-words text-xs text-muted-foreground">{description}</p>
      </div>
      <p className="text-xs text-muted-foreground">{t("actions.guardNote")}</p>
      {vm.needsAgent && (
        <label htmlFor={agentId} className="block space-y-1">
          <span>{t("actions.agent")}</span>
          {candidates.length === 0 ? <p className="text-xs text-red-600">{t("actions.noCandidates")}</p> : (
            <Select id={agentId} value={vm.agentId} disabled={locked} onChange={(e) => vm.setAgentId(e.target.value)} className="max-md:text-base">
              {candidates.map((c) => <option key={c.agent_id} value={c.agent_id}>{c.name}</option>)}
            </Select>
          )}
        </label>
      )}
      {pending.kind === "schedule" && (
        <label htmlFor={whenId} className="block space-y-1">
          <span>{t("actions.scheduledAt")}</span>
          <Input id={whenId} type="datetime-local" value={vm.scheduledAt} disabled={locked}
            onChange={(e) => vm.setScheduledAt(e.target.value)} className="max-md:text-base" />
        </label>
      )}
      {pending.kind === "decide_item" && (
        <label htmlFor={decisionId} className="block space-y-1">
          <span>{t("actions.decision")}</span>
          <Select id={decisionId} value={vm.decision} disabled={locked} onChange={(e) => vm.setDecision(e.target.value)} className="max-md:text-base">
            {["accept", "adjust", "reject"].map((d) => <option key={d} value={d}>{t(`actions.decisions.${d}`)}</option>)}
          </Select>
        </label>
      )}
      {vm.needsReason && (
        <label htmlFor={reasonId} className="block space-y-1">
          <span>{t("actions.reason")}</span>
          <Textarea id={reasonId} value={vm.reason} disabled={locked} onChange={(e) => vm.setReason(e.target.value)} rows={3} className="max-md:text-base" />
        </label>
      )}
      {vm.actionError && <p role="alert" className="break-words text-xs text-red-600">{vm.actionError}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" size="sm" variant="outline" disabled={vm.status === "submitting"} onClick={vm.cancelAction}>
          {t("actions.close")}
        </Button>
        <Button type="button" size="sm" variant={vm.destructive ? "destructive" : "default"}
          disabled={locked || !vm.canConfirm} onClick={vm.requestConfirm}>
          {vm.status === "submitting" && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
          {t("actions.review", { action: label })}
        </Button>
      </div>
    </section>
  );
}

/** The confirmation step every action passes (§7): names the action and
 * its target, spins while the guarded route answers and shows the backend's
 * refusal as is. No input here. */
export function MissionActionConfirm({ vm }: { vm: MissionExecutionsViewModel }) {
  const { t } = useTranslation("missions");
  const { label, description } = useActionText(vm);
  if (!vm.pending || (vm.status !== "confirming" && vm.status !== "submitting")) return null;
  return (
    <ConfirmDialog
      open
      title={t("actions.confirmTitle", { action: label })}
      description={description}
      confirmLabel={label}
      variant={vm.destructive ? "destructive" : "default"}
      icon={vm.destructive ? "warning" : "wrench"}
      loading={vm.status === "submitting"}
      confirmDisabled={!vm.canConfirm}
      dismissDisabled={vm.status === "submitting"}
      error={vm.actionError}
      onConfirm={() => void vm.confirmAction()}
      onCancel={vm.dismissConfirm}
    >
      {vm.needsReason && vm.reason.trim() && (
        <p className="break-words text-sm"><span className="text-muted-foreground">{t("actions.reason")}: </span>{vm.reason.trim()}</p>
      )}
      {!vm.hasFields && <p className="text-xs text-muted-foreground">{t("actions.guardNote")}</p>}
    </ConfirmDialog>
  );
}
