import { useState } from "react";
import { errorMessage } from "@/hooks/useMissionExecutionsViewModel";
import { useTranslation } from "react-i18next";
import { useDecideGovernedApproval, useGovernedApprovalRequests } from "@/hooks/useGovernance";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

/** The server remains authoritative for evidence, separation of duties and replay. */
export function MissionAcceptance({ projectId, canAct }: { projectId: string; canAct: boolean }) {
  const { t } = useTranslation("missions");
  const requests = useGovernedApprovalRequests("pending");
  const decide = useDecideGovernedApproval();
  const [reason, setReason] = useState("");
  const [decision, setDecision] = useState<"approved" | "changes_requested" | null>(null);
  const [done, setDone] = useState(false);
  const request = requests.data?.find(row => row.target_type === "mission_dossier" && row.target_id === projectId);
  return <section className="space-y-3 rounded-lg border p-4" aria-label={t("acceptance.title")}>
    <h2 className="font-semibold">{t("acceptance.title")}</h2>
    {requests.isLoading ? <p role="status">{t("acceptance.loading")}</p>
      : requests.isError ? <div role="alert"><p>{t("acceptance.error")}</p><Button variant="outline" onClick={() => requests.refetch()}>{t("board.retry")}</Button></div>
      : done ? <p role="status">{t("acceptance.recorded")}</p>
      : !request ? <p>{t("acceptance.missing")}</p> : <>
        <p className="text-sm text-muted-foreground">{t("acceptance.submitted", { name: request.requested_by_name })}</p>
        <p className="text-sm">{t("acceptance.hash")} <code className="break-all">{request.target_hash}</code></p>
        {canAct && <>
          <label className="block text-sm" htmlFor="mission-acceptance-reason">{t("acceptance.reason")}</label>
          <Textarea id="mission-acceptance-reason" value={reason} onChange={event => setReason(event.target.value)} disabled={decide.isPending} />
          <div className="flex flex-wrap gap-2"><Button disabled={!reason.trim() || decide.isPending} onClick={() => { decide.reset(); setDecision("approved"); }}>{t("acceptance.approve")}</Button>
            <Button variant="outline" disabled={!reason.trim() || decide.isPending} onClick={() => { decide.reset(); setDecision("changes_requested"); }}>{t("acceptance.return")}</Button></div>
          <ConfirmDialog open={decision !== null} variant="default" title={t("acceptance.title")}
            confirmLabel={t(decision === "approved" ? "acceptance.approve" : "acceptance.return")}
            loading={decide.isPending} error={decide.error ? errorMessage(decide.error) : undefined}
            onCancel={() => { if (!decide.isPending) setDecision(null); }}
            onConfirm={() => { if (decision) decide.mutate({ requestId: request.id, decision, comments: reason.trim() },
              { onSuccess: () => { setDecision(null); setDone(true); } }); }}>
            <p>{reason}</p><code className="break-all">{request.target_hash}</code>
          </ConfirmDialog>
        </>}
      </>}
  </section>;
}
