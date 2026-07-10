import { useState } from "react";
import {
  AlertCircle,
  Bot,
  Check,
  Clock,
  Copy,
  Eye,
  Loader2,
  Pencil,
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
  useUpdateCronJob,
  type CronJob,
} from "@/hooks/useFoundationCrons";
import {
  fetchScriptContentWithFallback,
  scriptKeys,
  useFoundationScripts,
  useScriptFileContent,
  useSyncScripts,
  type ScriptLocationRef,
} from "@/hooks/useFoundationScripts";
import { useAssistantStore } from "@/store/assistantStore";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { useQueryClient } from "@tanstack/react-query";

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

const CRON_HEALTH_LABEL: Record<CronJob["health"], string> = {
  ok: "Working",
  error: "Error",
  overdue: "Not running",
  never_ran: "Never ran",
  off: "Off",
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
  candidates,
  onClose,
}: {
  title: string;
  subtitle?: string;
  candidates: ScriptLocationRef[];
  onClose: () => void;
}) {
  const { data, isLoading, isError, error } = useScriptFileContent(candidates, true);
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
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="overflow-auto p-4">
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading file…
            </div>
          )}
          {isError && (
            <p className="text-sm text-destructive">{(error as Error)?.message ?? "Failed to load file."}</p>
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
          <h3 className="text-sm font-semibold">Edit task: {job.name}</h3>
          <Button variant="ghost" size="icon" aria-label="Cancel" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {updateJob.isError && (
          <p className="text-sm text-destructive">{(updateJob.error as Error)?.message}</p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Name</label>
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              Interval (cron expression)
            </label>
            <Input
              value={form.schedule_display}
              onChange={(e) => setForm((f) => ({ ...f, schedule_display: e.target.value }))}
              placeholder="*/5 * * * *"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Delivery (deliver)</label>
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
              Enabled
            </label>
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Description / prompt</label>
          <Textarea
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            rows={4}
          />
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={updateJob.isPending}>
            {updateJob.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CronsTab() {
  const { data, isLoading, isError, error } = useFoundationCrons();
  const jobs = data?.jobs;
  const storeErrors = data?.store_errors ?? [];
  // Script registry (cron-referenced only) joined by filename, to show each
  // job's script inline -- there is no separate Scripts tab anymore; the
  // full per-profile catalog lives in Agent Tools.
  const { data: scripts } = useFoundationScripts();
  const scriptsByName = new Map((scripts ?? []).map((s) => [s.name, s]));
  const deleteJob = useDeleteCronJob();
  const updateJob = useUpdateCronJob();
  const resetJob = useResetCronJob();
  const [editingJob, setEditingJob] = useState<CronJob | null>(null);
  const [viewingJob, setViewingJob] = useState<CronJob | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const setPendingSeed = useAssistantStore((s) => s.setPendingSeed);

  function handleDelete(job: CronJob) {
    if (!window.confirm(`Delete the cron "${job.name}" (profile ${job.profile})? This action cannot be undone.`))
      return;
    deleteJob.mutate(job.id);
  }

  async function handleSendToAssistant(job: CronJob) {
    setSendingId(job.id);
    try {
      const candidates: ScriptLocationRef[] = job.script
        ? [
            { location: job.profile, name: job.script },
            { location: "central", name: job.script },
          ]
        : [];
      const fileResult = candidates.length > 0 ? await fetchScriptContentWithFallback(candidates) : null;
      setPendingSeed(buildCronChatMessage(job, fileResult?.content ?? null, fileResult?.path ?? null));
      setAssistantOpen(true);
    } finally {
      setSendingId(null);
    }
  }

  return (
    <div className="space-y-4">
      {editingJob && <CronEditPanel job={editingJob} onClose={() => setEditingJob(null)} />}
      {viewingJob && (
        <FileViewerOverlay
          title={`${viewingJob.name} — ${viewingJob.script ?? "no script"}`}
          candidates={
            viewingJob.script
              ? [
                  { location: viewingJob.profile, name: viewingJob.script },
                  { location: "central", name: viewingJob.script },
                ]
              : []
          }
          onClose={() => setViewingJob(null)}
        />
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading crons…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load crons: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isError && storeErrors.length > 0 && (
        <Card className="border-destructive/50">
          <CardContent className="space-y-2 py-4">
            <div className="flex items-center gap-2 font-medium text-destructive">
              <AlertCircle className="h-5 w-5" />
              Corrupted cron store{storeErrors.length > 1 ? "s" : ""}
            </div>
            <p className="text-sm text-muted-foreground">
              These profiles&apos; jobs are missing from the list below, and their scheduler has
              stopped running them entirely — the gateway refuses to tick on a corrupted store.
              Fix the file, then restart that profile&apos;s gateway.
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
              <p className="font-medium">No crons found</p>
              <p className="text-sm text-muted-foreground">
                {storeErrors.length > 0
                  ? "Every parsable per-profile `hermes cron` store is empty — see the corrupted stores above."
                  : "No jobs registered in any per-profile `hermes cron` store."}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && jobs && jobs.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Task</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Interval</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Next run</TableHead>
                  <TableHead>Last run</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell>
                      <span className="font-medium">{job.name}</span>
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
                          title={scriptsByName.get(job.script)?.path ?? `View ${job.script}`}
                          className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                        >
                          <ScrollText className="h-3 w-3 shrink-0" />
                          <code>{job.script}</code>
                          {scriptsByName.get(job.script)?.status === "broken" && (
                            <span className="text-destructive">
                              {scriptsByName.get(job.script)?.escapes_scripts_dir
                                ? "— symlink escapes the scripts dir"
                                : "— file not found"}
                            </span>
                          )}
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
                            ? `Last execution log: ${formatTimestamp(job.last_log_at)}`
                            : "No execution log yet (crons/logs/)"
                        }
                      >
                        {CRON_HEALTH_LABEL[job.health]}
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
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`${job.enabled ? "Turn off" : "Turn on"} ${job.name}`}
                        title={job.enabled ? "Turn off" : "Turn on"}
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
                        aria-label={`Reset ${job.name}`}
                        title="Reset (clear errors and re-arm the schedule)"
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
                        aria-label={`View file for ${job.name}`}
                        disabled={!job.script}
                        title={job.script ? `View ${job.script}` : "No script attached"}
                        onClick={() => setViewingJob(job)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Send ${job.name} to the assistant`}
                        disabled={sendingId === job.id}
                        title="Open the assistant with this job's data and script as context"
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
                        aria-label={`Edit ${job.name}`}
                        onClick={() => setEditingJob(job)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${job.name}`}
                        disabled={deleteJob.isPending}
                        onClick={() => handleDelete(job)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Crons</h1>
          <p className="text-muted-foreground">
            Scheduled tasks and scripts (`hermes cron`) across every Hermes profile, with
            description, interval, executing agent, and run status.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={handleSync} disabled={isSyncing}>
            {isSyncing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Sync
          </Button>
          <AssistantToggleButton />
        </div>
      </div>

      <CronsTab />
    </div>
  );
}
