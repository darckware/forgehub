import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useRequestAthosMonitoring, type ActivityIncident } from "@/hooks/useAgentActivity";

interface RequestAthosDialogProps {
  incident: ActivityIncident | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RequestAthosDialog({ incident, open, onOpenChange }: RequestAthosDialogProps) {
  const { t } = useTranslation("agentActivity");
  const requestMonitoring = useRequestAthosMonitoring();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !incident) return;
    setError(null);
    setNotice(null);
  }, [incident, open]);

  const close = () => {
    if (!requestMonitoring.isPending) onOpenChange(false);
  };

  const submit = async () => {
    if (!incident?.execution_id || requestMonitoring.isPending) return;
    setError(null);
    try {
      await requestMonitoring.mutateAsync({ incidentKey: incident.key, executionId: incident.execution_id });
      setNotice(t("monitoring.success"));
      onOpenChange(false);
    } catch {
      setError(t("monitoring.failure"));
    }
  };

  return (
    <>
      {notice && (
        <p role="status" className="fixed bottom-4 right-4 z-50 max-w-sm rounded-md border border-emerald-500/40 bg-card px-4 py-3 text-sm text-emerald-700 shadow-lg dark:text-emerald-400">
          {notice}
        </p>
      )}

      <ConfirmDialog
        open={open && incident !== null}
        title={t("monitoring.title")}
        description={t("monitoring.description")}
        confirmLabel={t("monitoring.confirm")}
        cancelLabel={t("monitoring.cancel")}
        closeLabel={t("monitoring.close")}
        variant="default"
        icon="warning"
        loading={requestMonitoring.isPending}
        confirmDisabled={!incident?.execution_id}
        dismissDisabled={requestMonitoring.isPending}
        error={error}
        onConfirm={() => void submit()}
        onCancel={close}
      >
        {incident && (
          <>
            <div className="rounded-md border border-border bg-background p-3">
              <p className="text-sm font-medium">{incident.title}</p>
              {incident.summary && <p className="mt-1 text-xs text-muted-foreground">{incident.summary}</p>}
              <dl className="mt-3 grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
                <dt className="text-muted-foreground">{t("monitoring.errorCode")}</dt>
                <dd className="break-all font-mono">{incident.error_code ?? t("monitoring.notRecorded")}</dd>
                <dt className="text-muted-foreground">{t("monitoring.execution")}</dt>
                <dd className="break-all font-mono">{incident.execution_id ?? t("monitoring.notRecorded")}</dd>
                <dt className="text-muted-foreground">{t("monitoring.checkpoint")}</dt>
                <dd className="break-all font-mono">{incident.checkpoint_id ?? t("monitoring.notRecorded")}</dd>
                <dt className="text-muted-foreground">{t("monitoring.blocker")}</dt>
                <dd className="break-all font-mono">{incident.blocker_code ?? t("monitoring.notRecorded")}</dd>
              </dl>
            </div>

            {!incident.execution_id && (
              <p role="alert" className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
                {t("monitoring.missingExecution")}
              </p>
            )}
          </>
        )}
      </ConfirmDialog>
    </>
  );
}
