import { useId } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { MissionExecutionsViewModel } from "@/hooks/useMissionExecutionsViewModel";

/** The one confirmation step every action passes (§7): reason where
 * required, the agent to pick, the time to schedule; the confirm button
 * spins while the guarded route answers and the backend's refusal is shown
 * as is. */
export function MissionActionDialog({ vm }: { vm: MissionExecutionsViewModel }) {
  const { t } = useTranslation("missions");
  const reasonId = useId();
  const agentId = useId();
  const whenId = useId();
  const decisionId = useId();
  const pending = vm.pending;
  if (!pending) return null;
  const label = t(`actions.${pending.kind}`);
  const task = vm.pendingTask;
  const candidates = pending.kind === "assign" ? task?.executor_candidates ?? []
    : pending.kind === "request_review" ? (task?.reviewer_candidates ?? []).filter((c) => c.eligible) : [];
  const item = pending.itemId ? vm.board?.planning?.pending_decisions.find((d) => d.item_id === pending.itemId) : undefined;
  const description = task ? t("actions.confirmTask", { number: task.number, title: task.title })
    : item ? item.text : t("actions.confirmMission", { name: vm.board?.mission.name ?? "" });
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
      onCancel={vm.cancelAction}
    >
      <div className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">{t("actions.guardNote")}</p>
        {vm.needsAgent && (
          <label htmlFor={agentId} className="block space-y-1">
            <span>{t("actions.agent")}</span>
            {candidates.length === 0 ? <p className="text-xs text-red-600">{t("actions.noCandidates")}</p> : (
              <Select id={agentId} value={vm.agentId} onChange={(e) => vm.setAgentId(e.target.value)} className="max-md:text-base">
                {candidates.map((c) => <option key={c.agent_id} value={c.agent_id}>{c.name}</option>)}
              </Select>
            )}
          </label>
        )}
        {pending.kind === "schedule" && (
          <label htmlFor={whenId} className="block space-y-1">
            <span>{t("actions.scheduledAt")}</span>
            <Input id={whenId} type="datetime-local" value={vm.scheduledAt} onChange={(e) => vm.setScheduledAt(e.target.value)} className="max-md:text-base" />
          </label>
        )}
        {pending.kind === "decide_item" && (
          <label htmlFor={decisionId} className="block space-y-1">
            <span>{t("actions.decision")}</span>
            <Select id={decisionId} value={vm.decision} onChange={(e) => vm.setDecision(e.target.value)} className="max-md:text-base">
              {["accept", "adjust", "reject"].map((d) => <option key={d} value={d}>{t(`actions.decisions.${d}`)}</option>)}
            </Select>
          </label>
        )}
        {vm.needsReason && (
          <label htmlFor={reasonId} className="block space-y-1">
            <span>{t("actions.reason")}</span>
            <Textarea id={reasonId} value={vm.reason} onChange={(e) => vm.setReason(e.target.value)} rows={3} className="max-md:text-base" />
          </label>
        )}
      </div>
    </ConfirmDialog>
  );
}
