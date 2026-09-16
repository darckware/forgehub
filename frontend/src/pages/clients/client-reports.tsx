import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Calendar,
  Download,
  FileText,
  History,
  Loader2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  type ClientReport,
  downloadReportFile,
  useClientReports,
  useGenerateClientReport,
  useGenerateMonthlyReport,
  useReviewClientReport,
} from "@/hooks/useClientReports";

interface ClientReportsPanelProps {
  clientId: string;
  defaultIrregularityId?: string | null;
}

export function ClientReportsPanel({ clientId, defaultIrregularityId }: ClientReportsPanelProps) {
  const { t } = useTranslation("clients");
  const reports = useClientReports(clientId);
  const generateOnDemand = useGenerateClientReport(clientId);
  const generateMonthly = useGenerateMonthlyReport(clientId);
  const reviewMutation = useReviewClientReport(clientId);

  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [month, setMonth] = useState("");
  const [unreviewTarget, setUnreviewTarget] = useState<ClientReport | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleGenerateOnDemand = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!periodStart || !periodEnd) return;
    setErrorMessage(null);
    try {
      await generateOnDemand.mutateAsync({
        period_start: periodStart,
        period_end: periodEnd,
        irregularity_id: defaultIrregularityId || undefined,
      });
      setPeriodStart("");
      setPeriodEnd("");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : t("reports.generateError"));
    }
  };

  const handleGenerateMonthly = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!month) return;
    setErrorMessage(null);
    try {
      await generateMonthly.mutateAsync({ month });
      setMonth("");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : t("reports.monthlyError"));
    }
  };

  const handleDownload = async (report: ClientReport) => {
    setDownloadingId(report.id);
    try {
      await downloadReportFile(report.id);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : t("reports.downloadError"));
    } finally {
      setDownloadingId(null);
    }
  };

  const handleReviewToggle = (report: ClientReport) => {
    if (report.reviewed_at) {
      setUnreviewTarget(report);
    } else {
      reviewMutation.mutate({ reportId: report.id, reviewed: true });
    }
  };

  const handleConfirmUnreview = () => {
    if (!unreviewTarget) return;
    reviewMutation.mutate({ reportId: unreviewTarget.id, reviewed: false });
    setUnreviewTarget(null);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            {t("reports.title")}
          </h2>
          <p className="text-xs text-muted-foreground">{t("reports.description")}</p>
        </div>
      </div>

      {errorMessage && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive" role="alert">
          {errorMessage}
        </div>
      )}

      {/* Formulários de Geração */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Sob Demanda */}
        <form
          onSubmit={handleGenerateOnDemand}
          className="rounded-xl border border-border bg-card/60 p-4 space-y-3"
        >
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
            {t("reports.onDemandTitle")}
          </span>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] text-muted-foreground block mb-1">
                {t("reports.periodStart")}
              </label>
              <input
                type="date"
                required
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label className="text-[11px] text-muted-foreground block mb-1">
                {t("reports.periodEnd")}
              </label>
              <input
                type="date"
                required
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
          <Button
            type="submit"
            size="sm"
            disabled={generateOnDemand.isPending || !periodStart || !periodEnd}
            className="w-full"
          >
            {generateOnDemand.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Calendar className="h-4 w-4 mr-2" />
            )}
            {t("reports.generateOnDemand")}
          </Button>
        </form>

        {/* Mensal */}
        <form
          onSubmit={handleGenerateMonthly}
          className="rounded-xl border border-border bg-card/60 p-4 space-y-3"
        >
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
            {t("reports.monthlyTitle")}
          </span>
          <div>
            <label className="text-[11px] text-muted-foreground block mb-1">
              {t("reports.monthLabel")}
            </label>
            <input
              type="month"
              required
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              placeholder="YYYY-MM"
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <Button
            type="submit"
            variant="outline"
            size="sm"
            disabled={generateMonthly.isPending || !month}
            className="w-full"
          >
            {generateMonthly.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <History className="h-4 w-4 mr-2" />
            )}
            {t("reports.generateMonthly")}
          </Button>
        </form>
      </div>

      {/* Lista de Relatórios */}
      <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
        {reports.isLoading ? (
          <div className="flex items-center justify-center p-8 text-xs text-muted-foreground gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{t("states.loading")}</span>
          </div>
        ) : reports.isError ? (
          <div className="p-4 text-xs text-destructive text-center">
            {t("reports.loadError")}
          </div>
        ) : !reports.data?.length ? (
          <div className="p-8 text-center text-xs text-muted-foreground">
            {t("reports.empty")}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {reports.data.map((report) => {
              const isReviewed = Boolean(report.reviewed_at);
              const isDownloading = downloadingId === report.id;
              return (
                <div
                  key={report.id}
                  className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between hover:bg-muted/20 transition-colors"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Badge variant={report.kind === "monthly" ? "secondary" : "outline"}>
                        {report.kind === "monthly" ? t("reports.kindMonthly") : t("reports.kindOnDemand")}
                      </Badge>
                      <span className="text-xs font-semibold text-foreground">
                        {report.period_start} → {report.period_end}
                      </span>
                      {isReviewed ? (
                        <Badge variant="success" className="inline-flex items-center gap-1 text-[10px]">
                          <ShieldCheck className="h-3 w-3" />
                          {t("reports.reviewed")}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                          <ShieldAlert className="h-3 w-3" />
                          {t("reports.draft")}
                        </Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {t("reports.generatedAt")}: {new Date(report.generated_at).toLocaleString()}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleDownload(report)}
                      disabled={isDownloading}
                      className="text-xs h-8"
                    >
                      {isDownloading ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                      ) : (
                        <Download className="h-3.5 w-3.5 mr-1" />
                      )}
                      {t("reports.download")}
                    </Button>

                    <Button
                      type="button"
                      variant={isReviewed ? "destructive" : "secondary"}
                      size="sm"
                      onClick={() => handleReviewToggle(report)}
                      disabled={reviewMutation.isPending}
                      className="text-xs h-8"
                    >
                      {isReviewed ? t("reports.unreview") : t("reports.markReviewed")}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(unreviewTarget)}
        onCancel={() => setUnreviewTarget(null)}
        title={t("reports.unreviewTitle")}
        description={t("reports.unreviewDescription")}
        confirmLabel={t("reports.unreviewConfirm")}
        onConfirm={handleConfirmUnreview}
        variant="destructive"
      />
    </div>
  );
}
