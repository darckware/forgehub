import { useMemo, useState } from "react";
import { Eye, Loader2, Newspaper, RefreshCw, Search, Trash2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Markdown } from "@/components/Markdown";
import { useTranslation } from "react-i18next";
import {
  newsKeys,
  useDeleteAllNewsReports,
  useDeleteNewsReport,
  useNewsReportContent,
  useNewsReports,
  type NewsReport,
} from "@/hooks/useNews";

const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;
// ForgeHub is a single-region (Brazil) product -- pin display to
// America/Sao_Paulo instead of trusting whatever timezone the browser/OS
// happens to be set to (a UTC-configured machine would otherwise show
// timestamps hours off from what the report's own "Publicado: ... UTC"
// lines mean locally).
const DISPLAY_TIMEZONE = "America/Sao_Paulo";

function formatDate(value: string | null): string {
  if (!value) return "—";
  // report.date is a bare "YYYY-MM-DD" (no time/offset -- parsed from the
  // filename): a calendar date, not an instant, so it must NOT go through
  // any timezone conversion at all -- construct it from local components
  // and format with no explicit timeZone so the same Y-M-D round-trips
  // regardless of DISPLAY_TIMEZONE or the runtime's own timezone.
  if (DATE_ONLY_RE.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString();
  }
  // Full ISO timestamp (modified_at, used as the fallback): a real instant,
  // so pin it to DISPLAY_TIMEZONE for formatting.
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { timeZone: DISPLAY_TIMEZONE });
}

function ReportViewerOverlay({
  report,
  onClose,
}: {
  report: NewsReport;
  onClose: () => void;
}) {
  const { data, isLoading, isError } = useNewsReportContent(report);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h3 className="truncate font-semibold">{report.title}</h3>
            <p className="truncate text-xs text-muted-foreground">
              {report.profile} · {report.filename}
            </p>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="overflow-auto p-4">
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading report…
            </div>
          )}
          {isError && <p className="text-sm text-destructive">Failed to load report.</p>}
          {data?.content != null && <Markdown content={data.content} />}
        </div>
      </div>
    </div>
  );
}

export default function NewsPage() {
  const { t } = useTranslation("news");
  const { data: reports, isLoading, isError, error } = useNewsReports();
  const deleteReport = useDeleteNewsReport();
  const deleteAll = useDeleteAllNewsReports();
  const queryClient = useQueryClient();
  const [isSyncing, setIsSyncing] = useState(false);
  const [search, setSearch] = useState("");
  const [viewingReport, setViewingReport] = useState<NewsReport | null>(null);
  const [pendingDelete, setPendingDelete] = useState<NewsReport | null>(null);
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);

  const filtered = useMemo(() => {
    const list = reports ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        r.profile.toLowerCase().includes(q) ||
        r.preview.toLowerCase().includes(q)
    );
  }, [reports, search]);

  async function confirmDelete() {
    if (!pendingDelete) return;
    await deleteReport.mutateAsync(pendingDelete);
    setPendingDelete(null);
  }

  async function confirmDeleteAllReports() {
    await deleteAll.mutateAsync();
    setConfirmDeleteAll(false);
  }

  async function handleSync() {
    setIsSyncing(true);
    try {
      // No DB table backs News (see news.py) -- "sync" here just forces a
      // fresh read of every profile's reports/ dir instead of trusting
      // whatever TanStack Query already has cached.
      await queryClient.invalidateQueries({ queryKey: newsKeys.list });
    } finally {
      setIsSyncing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <Newspaper className="h-7 w-7" />
            {t("title")}
          </h1>
          <p className="text-muted-foreground">
            {t("description")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={handleSync} disabled={isSyncing}>
            {isSyncing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {t("syncButton")}
          </Button>
          <Button
            variant="destructive"
            onClick={() => setConfirmDeleteAll(true)}
            disabled={!reports || reports.length === 0}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            {t("deleteAllButton")}
          </Button>
        </div>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("searchPlaceholder")}
          className="pl-8"
        />
      </div>

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("loadingNews")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <span>{t("loadError")}: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Newspaper className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">{t("noNewsFound")}</p>
              <p className="text-sm text-muted-foreground">
                {reports && reports.length > 0
                  ? t("noReportsMatchSearch")
                  : t("noReportRuns")}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && filtered.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("tableHeaders.report")}</TableHead>
                  <TableHead className="whitespace-nowrap">{t("tableHeaders.profile")}</TableHead>
                  <TableHead className="whitespace-nowrap">{t("tableHeaders.date")}</TableHead>
                  <TableHead className="whitespace-nowrap">{t("tableHeaders.articles")}</TableHead>
                  <TableHead className="whitespace-nowrap text-right">{t("tableHeaders.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((report) => (
                  <TableRow key={`${report.profile}/${report.filename}`}>
                    <TableCell>
                      <span className="font-medium">{report.title}</span>
                      <p className="mt-1 line-clamp-2 max-w-xl text-xs text-muted-foreground">
                        {report.preview}
                      </p>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{report.profile}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(report.date ?? report.modified_at)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{report.article_count}</Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-0.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`View ${report.title}`}
                          title="View report"
                          onClick={() => setViewingReport(report)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Delete ${report.title}`}
                          title="Delete report"
                          onClick={() => setPendingDelete(report)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {viewingReport && (
        <ReportViewerOverlay report={viewingReport} onClose={() => setViewingReport(null)} />
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title={t("deleteReportTitle")}
        description={pendingDelete ? t("deleteReportDescription", { title: pendingDelete.title }) : undefined}
        confirmLabel={t("deleteConfirmLabel")}
        loading={deleteReport.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />

      <ConfirmDialog
        open={confirmDeleteAll}
        title={t("deleteAllTitle")}
        description={t("deleteAllDescription")}
        confirmLabel={t("deleteAllConfirmLabel")}
        loading={deleteAll.isPending}
        onConfirm={confirmDeleteAllReports}
        onCancel={() => setConfirmDeleteAll(false)}
      />
    </div>
  );
}
