import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Bot,
  Check,
  Clock,
  Copy,
  Eye,
  Loader2,
  Pencil,
  Play,
  Power,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Trash2,
  X,
} from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import {
  cronJobKeys,
  useDeleteCronJob,
  useFoundationCrons,
  useResetCronJob,
  useRunCronJob,
  useUpdateCronJob,
  type CronJob,
} from "@/hooks/useFoundationCrons";
import {
  fetchScriptContent,
  scriptKeys,
  useScriptFileContent,
  useSyncScripts,
  type ScriptLocationRef,
} from "@/hooks/useFoundationScripts";
import { useAssistantStore } from "@/store/assistantStore";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

// Keyed by `health` (real execution evidence), not `status` (which only
// mirrors the enabled flag and used to show every job as "Active" while the
// scheduler had silently stopped running them).
const CRON_HEALTH_VARIANT: Record<CronJob["health"], "success" | "warning" | "destructive" | "outline"> = {
  ok: "success",
  error: "destructive",
  overdue: "warning",
  never_ran: "outline",
  off: "outline",
};

const CRON_HEALTH_KEY: Record<CronJob["health"], string> = {
  ok: "working", error: "error", overdue: "notRunning", never_ran: "neverRun", off: "off",
};

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function buildCronChatMessage(job: CronJob, fileContent: string | null, filePath: string | null): string {
  const lines: string[] = [
    "I need help adjusting this Hermes cron job. Please review it and suggest fixes.",
    "",
    `Task: ${job.name}`,
    `Profile: ${job.profile}`,
    `Schedule: ${job.schedule_display ?? "—"}`,
    `Status: ${job.status} (health: ${job.health})`,
  ];
  if (job.deliver) lines.push(`Deliver: ${job.deliver}`);
  if (job.description) lines.push(`Description: ${job.description}`);

  if (job.script) {
    lines.push("", `Script: ${job.script}`);
    if (fileContent != null) {
      if (filePath) lines.push(`Path: ${filePath}`);
      lines.push("", "```", fileContent, "```");
    } else {
      lines.push("(Could not read the script file content -- it may be missing or broken.)");
    }
  }
  return lines.join("\n");
}

function FileViewerOverlay({
  title,
  subtitle,
  scriptRef,
  onClose,
}: {
  title: string;
  subtitle?: string;
  scriptRef: ScriptLocationRef;
  onClose: () => void;
}) {
  const { t } = useTranslation("crons");
  const { data, isLoading, isError, error } = useScriptFileContent(scriptRef, true);
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (!data?.content) return;
    await navigator.clipboard.writeText(data.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h3 className="truncate font-semibold">{title}</h3>
            <p className="truncate text-xs text-muted-foreground">{data?.path ?? subtitle ?? ""}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleCopy} disabled={!data?.content}>
              {copied ? (
                <Check className="mr-2 h-3.5 w-3.5" />
              ) : (
                <Copy className="mr-2 h-3.5 w-3.5" />
              )}
              {copied ? t("crons.copied") : t("crons.copy")}
            </Button>
            <Button variant="ghost" size="icon" aria-label={t("crons.close")} onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="overflow-auto p-4">
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              {t("crons.loadingFile")}
            </div>
          )}
          {isError && (
            <p className="text-sm text-destructive">{t("crons.loadFileError", { error: (error as Error)?.message ?? "" })}</p>
          )}
          {data?.content != null && (
            <pre className="whitespace-pre-wrap break-all text-xs">
              <code>{data.content}</code>
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

interface EditForm {
  name: string;
  description: string;
  schedule_display: string;
  deliver: string;
  enabled: boolean;
}

function CronEditPanel({
  job,
  onClose,
}: {
  job: CronJob;
  onClose: () => void;
}) {
  const { t } = useTranslation("crons");
  const updateJob = useUpdateCronJob();
  const [form, setForm] = useState<EditForm>({
    name: job.name,
    description: job.description ?? "",
    schedule_display: job.schedule_display ?? "",
    deliver: job.deliver ?? "",
    enabled: job.status !== "disabled",
  });

  function handleSave() {
    updateJob.mutate(
      {
        jobId: job.id,
        updates: {
          name: form.name,
          description: form.description,
          schedule_display: form.schedule_display,
          deliver: form.deliver,
          enabled: form.enabled,
        },
      },
      { onSuccess: onClose }
    );
  }

  return (
    <Card className="border-primary/40">
      <CardContent className="space-y-4 py-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">{t("crons.editTask", { name: job.name })}</h3>
          <Button variant="ghost" size="icon" aria-label={t("crons.cancel")} onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {updateJob.isError && (
          <p className="text-sm text-destructive">{(updateJob.error as Error)?.message}</p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">{t("crons.name")}</label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              {t("crons.cronExpression")}
            </label>
            <Input
              value={form.schedule_display}
              onChange={(e) => setForm((f) => ({ ...f, schedule_display: e.target.value }))}
              placeholder="*/5 * * * *"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">{t("crons.delivery")}</label>
            <Input
              value={form.deliver}
              onChange={(e) => setForm((f) => ({ ...f, deliver: e.target.value }))}
              placeholder="local, telegram, telegram:chat_id…"
            />
          </div>
          <div className="flex items-center gap-2 pt-5">
            <input
              id={`enabled-${job.id}`}
              type="checkbox"
              className="h-4 w-4"
              checked={form.enabled}
              onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
            />
            <label htmlFor={`enabled-${job.id}`} className="text-sm">
              {t("crons.enabled")}
            </label>
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">{t("crons.prompt")}</label>
          <Textarea className="resize-none"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            rows={4}
          />
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("crons.cancel")}
          </Button>
          <Button onClick={handleSave} disabled={updateJob.isPending}>
            {updateJob.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {t("crons.save")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CronsTab() {
  const { t } = useTranslation("crons");
  const { data, isLoading, isError, error } = useFoundationCrons();
  const jobs = data?.jobs;
  const storeErrors = data?.store_errors ?? [];
  const deleteJob = useDeleteCronJob();
  const updateJob = useUpdateCronJob();
  const resetJob = useResetCronJob();
  const runJob = useRunCronJob();
  const [editingJob, setEditingJob] = useState<CronJob | null>(null);
  const [viewingJob, setViewingJob] = useState<CronJob | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [deletingJob, setDeletingJob] = useState<CronJob | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const setPendingHiddenContext = useAssistantStore((s) => s.setPendingHiddenContext);

  function handleRun(job: CronJob) {
    setRunError(null);
    runJob.mutate(job.id, {
      onError: (err) => {
        setRunError(t("crons.runError", { name: job.name, error: (err as Error)?.message ?? t("crons.unknownError") }));
      },
    });
  }

  async function handleSendToAssistant(job: CronJob) {
    setSendingId(job.id);
    try {
      const fileResult = job.script
        ? await fetchScriptContent({ location: job.profile, name: job.script }).catch(() => null)
        : null;
      setPendingHiddenContext(buildCronChatMessage(job, fileResult?.content ?? null, fileResult?.path ?? null));
      setAssistantOpen(true);
    } finally {
      setSendingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <ConfirmDialog
        open={deletingJob !== null}
        title={t("crons.deleteTitle")}
        description={t("crons.deleteDescription", { name: deletingJob?.name, profile: deletingJob?.profile })}
        confirmLabel={t("crons.delete")}
        loading={deleteJob.isPending}
        error={deleteJob.isError ? (deleteJob.error as Error)?.message : null}
        onCancel={() => setDeletingJob(null)}
        onConfirm={() => deletingJob && deleteJob.mutate(deletingJob.id, { onSuccess: () => setDeletingJob(null) })}
      />
      {editingJob && <CronEditPanel job={editingJob} onClose={() => setEditingJob(null)} />}
      {viewingJob && (
        <FileViewerOverlay
          title={`${viewingJob.name} — ${viewingJob.script ?? t("crons.noScript")}`}
          scriptRef={{ location: viewingJob.profile, name: viewingJob.script ?? "" }}
          onClose={() => setViewingJob(null)}
        />
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("crons.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("crons.loadError", { error: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {runError && <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{runError}</p>}

      {!isLoading && !isError && jobs && jobs.length > 0 && (
        <section aria-label={t("crons.healthSummary")} className="grid grid-cols-2 gap-2 md:grid-cols-5">
          {(["ok", "error", "overdue", "never_ran", "off"] as const).map((health) => (
            <div key={health} className="rounded-md border border-border bg-card px-3 py-2">
              <span className="block text-xs text-muted-foreground">{t(`crons.${CRON_HEALTH_KEY[health]}`)}</span>
              <strong className="text-xl tabular-nums">{jobs.filter((job) => job.health === health).length}</strong>
            </div>
          ))}
        </section>
      )}

      {!isError && storeErrors.length > 0 && (
        <Card className="border-destructive/50">
          <CardContent className="space-y-2 py-4">
            <div className="flex items-center gap-2 font-medium text-destructive">
              <AlertCircle className="h-5 w-5" />
              {t("crons.corruptedStores", { count: storeErrors.length })}
            </div>
            <p className="text-sm text-muted-foreground">
              {t("crons.corruptedDescription")}
            </p>
            <ul className="space-y-1 text-sm">
              {storeErrors.map((se) => (
                <li key={se.store}>
                  <span className="font-medium">{se.profile}</span>{" "}
                  <code className="text-xs text-muted-foreground">{se.store}</code>
                  <span className="text-destructive"> — {se.error}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && jobs && jobs.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Clock className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">{t("crons.noCrons")}</p>
              <p className="text-sm text-muted-foreground">
                {storeErrors.length > 0
                  ? t("crons.noCronsDescription")
                  : t("crons.noJobsRegistered")}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && jobs && jobs.length > 0 && (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("crons.task")}</TableHead>
                  <TableHead className="whitespace-nowrap">{t("crons.agent")}</TableHead>
                  <TableHead className="whitespace-nowrap">{t("crons.interval")}</TableHead>
                  <TableHead className="whitespace-nowrap">{t("crons.status")}</TableHead>
                  <TableHead className="whitespace-nowrap">{t("crons.nextRun")}</TableHead>
                  <TableHead className="whitespace-nowrap">{t("crons.lastRun")}</TableHead>
                  <TableHead className="whitespace-nowrap text-right">{t("crons.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell>
                      <span className="font-medium">{job.name}</span>
                      {job.is_audit_job && <Badge variant="outline" className="ml-2">{t("crons.auditJob")}</Badge>}
                      {job.description && (
                        <p
                          className="max-w-md truncate text-xs text-muted-foreground"
                          title={job.description}
                        >
                          {job.description}
                        </p>
                      )}
                      {job.script && (
                        <button
                          type="button"
                          onClick={() => setViewingJob(job)}
                          title={t("crons.viewScript", { name: job.script })}
                          className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                        >
                          <ScrollText className="h-3 w-3 shrink-0" />
                          <code>{job.script}</code>
                          {job.script_state === "missing" && <span className="text-destructive">{t("crons.missingScript")}</span>}
                          {job.script_state === "broken" && <span className="text-destructive">{t("crons.brokenScript")}</span>}
                        </button>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{job.profile}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      <code className="text-xs">{job.schedule_display ?? "—"}</code>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={CRON_HEALTH_VARIANT[job.health]}
                        title={
                          job.last_log_at
                            ? t("crons.lastLog", { date: formatTimestamp(job.last_log_at) })
                            : t("crons.noLog")
                        }
                      >
                        {t(`crons.${CRON_HEALTH_KEY[job.health]}`)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatTimestamp(job.next_run_at)}
                    </TableCell>
                    <TableCell className="text-sm">
                      <span
                        className={
                          job.last_status === "error" ? "text-destructive" : "text-muted-foreground"
                        }
                      >
                        {formatTimestamp(job.last_run_at)}
                        {job.last_status ? ` (${job.last_status})` : ""}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-0.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("crons.runNowLabel", { name: job.name })}
                          title={t("crons.runNowTitle")}
                          disabled={runJob.isPending && runJob.variables === job.id}
                          onClick={() => handleRun(job)}
                        >
                          {runJob.isPending && runJob.variables === job.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Play className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t(job.enabled ? "crons.turnOffLabel" : "crons.turnOnLabel", { name: job.name })}
                          title={t(job.enabled ? "crons.turnOff" : "crons.turnOn")}
                          disabled={!job.id || (updateJob.isPending && updateJob.variables?.jobId === job.id)}
                          onClick={() => updateJob.mutate({ jobId: job.id, updates: { enabled: !job.enabled } })}
                        >
                          {updateJob.isPending && updateJob.variables?.jobId === job.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Power className={job.enabled ? "h-4 w-4 text-emerald-600" : "h-4 w-4 text-muted-foreground"} />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("crons.resetLabel", { name: job.name })}
                          title={t("crons.resetTitle")}
                          disabled={!job.id || (resetJob.isPending && resetJob.variables === job.id)}
                          onClick={() => resetJob.mutate(job.id)}
                        >
                          {resetJob.isPending && resetJob.variables === job.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <RotateCcw className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("crons.viewFileLabel", { name: job.name })}
                          disabled={!job.script}
                          title={job.script ? t("crons.viewScript", { name: job.script }) : t("crons.noScript")}
                          onClick={() => setViewingJob(job)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("crons.sendLabel", { name: job.name })}
                          disabled={sendingId === job.id}
                          title={t("crons.sendTitle")}
                          onClick={() => handleSendToAssistant(job)}
                        >
                          {sendingId === job.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Bot className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("crons.editLabel", { name: job.name })}
                          onClick={() => setEditingJob(job)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("crons.deleteLabel", { name: job.name })}
                          disabled={deleteJob.isPending}
                          onClick={() => setDeletingJob(job)}
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
    </div>
  );
}

export default function CronsPage() {
  const { t } = useTranslation("crons");
  const queryClient = useQueryClient();
  const [isSyncing, setIsSyncing] = useState(false);
  const { sync: syncScripts } = useSyncScripts();

  async function handleSync() {
    setIsSyncing(true);
    try {
      await syncScripts();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: cronJobKeys.list }),
        queryClient.invalidateQueries({ queryKey: scriptKeys.list }),
      ]);
    } finally {
      setIsSyncing(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("crons.title")}</h1>
          <p className="text-muted-foreground">
            {t("crons.description")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={handleSync} disabled={isSyncing}>
            {isSyncing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {t("crons.sync")}
          </Button>
          <AssistantToggleButton />
        </div>
      </div>

      <CronsTab />
    </div>
  );
}
