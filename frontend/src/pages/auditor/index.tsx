import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Bot,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Loader2,
  Pencil,
  Play,
  PlayCircle,
  Plus,
  Power,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/PageHeader";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useAuditChecks,
  useAuditRuns,
  useAuditStatus,
  useCreateAuditCheck,
  useDeleteAuditCheck,
  useRunAllAuditChecks,
  useRunAuditCheck,
  useRemediateAuditCheck,
  useUpdateAuditCheck,
  type AuditCheck,
  type AuditCheckInput,
} from "@/hooks/useAudit";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { useAssistantStore } from "@/store/assistantStore";

const RUN_STATUS_BADGE: Record<string, { variant: "success" | "destructive" | "warning" | "outline" }> = {
  ok: { variant: "success" },
  fail: { variant: "destructive" },
  error: { variant: "destructive" },
  timeout: { variant: "warning" },
};

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function remediationError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    const body = error.body as { detail?: { problems?: string[] } } | undefined;
    if (body?.detail?.problems?.length) return body.detail.problems.join("; ");
  }
  const message = error instanceof Error ? error.message : String(error ?? "");
  const match = message.match(/"problems"\s*:\s*(\[[^\]]+\])/);
  if (match) {
    try { return (JSON.parse(match[1]) as string[]).join("; "); } catch { /* keep original */ }
  }
  return message;
}

/** Context attached invisibly to the assistant chat (assistantStore's
 * pendingHiddenContext), mirroring Crons'/Agent Tools' maintenance
 * message: check metadata first, then the command and last result. */
function buildAuditCheckChatMessage(check: AuditCheck): string {
  const lines: string[] = [
    "I need help with this Auditor checkpoint. Please review it and suggest fixes.",
    "",
    `Check: ${check.name}`,
    `Category: ${check.category ?? "—"}`,
    `Responsible agent: ${check.agent_profile}`,
    `Enabled: ${check.enabled ? "yes" : "no"}`,
    `Timeout: ${check.timeout_seconds}s`,
  ];
  if (check.workdir) lines.push(`Directory: ${check.workdir}`);
  if (check.description) lines.push(`Description: ${check.description}`);
  lines.push("", "Command:", "```", check.command, "```");
  if (check.remediation_description) lines.push("", `Correction: ${check.remediation_description}`);
  if (check.remediation_command) {
    lines.push("Correction command (requires administrator confirmation):", "```", check.remediation_command, "```");
  }
  if (check.last_run) {
    lines.push(
      "",
      `Last run: ${check.last_run.status} at ${formatTimestamp(check.last_run.created_at)}`,
    );
    if (check.last_run.output) lines.push("```", check.last_run.output, "```");
  }
  return lines.join("\n");
}

/** Inline create/edit form. Editing is rendered immediately below its check
 * row, keeping the operator in the list and allowing normal page scrolling. */
function CheckFormPanel({ initial, onClose }: { initial: AuditCheck | null; onClose: () => void }) {
  const { t } = useTranslation("auditor");
  const createCheck = useCreateAuditCheck();
  const updateCheck = useUpdateAuditCheck();
  const pending = createCheck.isPending || updateCheck.isPending;
  const error = (createCheck.error ?? updateCheck.error) as Error | null;
  const [form, setForm] = useState<AuditCheckInput>({
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    category: initial?.category ?? "",
    command: initial?.command ?? "",
    remediation_description: initial?.remediation_description ?? "",
    remediation_command: initial?.remediation_command ?? "",
    workdir: initial?.workdir ?? "",
    agent_profile: initial?.agent_profile ?? "athos",
    enabled: initial?.enabled ?? true,
    timeout_seconds: initial?.timeout_seconds ?? 55,
  });
  const enabledId = `check-enabled-${initial?.id ?? "new"}`;

  function handleSave() {
    const payload: AuditCheckInput = {
      ...form,
      description: form.description || null,
      remediation_description: form.remediation_description || null,
      remediation_command: form.remediation_command || null,
      category: form.category || null,
      workdir: form.workdir || null,
    };
    if (initial) {
      updateCheck.mutate({ checkId: initial.id, updates: payload }, { onSuccess: onClose });
    } else {
      createCheck.mutate(payload, { onSuccess: onClose });
    }
  }

  return (
    <div className="rounded-lg border border-primary/30 bg-card shadow-sm">
      <div className="flex items-center justify-between border-b border-border bg-muted/30 px-4 py-3">
        <div>
          <h3 className="font-semibold">{initial ? `${t("auditor.edit")}: ${initial.name}` : t("auditor.newCheck")}</h3>
          <p className="text-xs text-muted-foreground">
            {initial ? t("auditor.editDescription") : t("auditor.createDescription")}
          </p>
        </div>
        <Button variant="ghost" size="icon" aria-label={t("auditor.closeEditor")} title={t("auditor.closeEditor")} onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="space-y-4 p-4">
          {error && <p className="text-sm text-destructive">{error.message}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">{t("auditor.name")}</label>
              <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">{t("auditor.category")}</label>
              <Input
                value={form.category ?? ""}
                placeholder="infra, cron, backup…"
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">{t("auditor.agent")}</label>
              <Input
                value={form.agent_profile}
                onChange={(e) => setForm((f) => ({ ...f, agent_profile: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">{t("auditor.timeoutLabel")}</label>
              <Input
                type="number"
                min={1}
                max={600}
                value={form.timeout_seconds}
                onChange={(e) => setForm((f) => ({ ...f, timeout_seconds: Number(e.target.value) || 55 }))}
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              {t("auditor.commandLabel")}
            </label>
            <Textarea
              value={form.command}
              rows={3}
              className="resize-none font-mono text-xs"
              onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
            />
          </div>
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
              {t("auditor.correctionTitle")}
            </p>
            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">{t("auditor.correctionContext")}</label>
                <Textarea className="resize-none"
                  value={form.remediation_description ?? ""}
                  rows={2}
                  placeholder={t("auditor.correctionContextHint")}
                  onChange={(e) => setForm((f) => ({ ...f, remediation_description: e.target.value }))}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">{t("auditor.correctionCommand")}</label>
                <Textarea
                  value={form.remediation_command ?? ""}
                  rows={3}
                  className="resize-none font-mono text-xs"
                  placeholder={t("auditor.correctionCommandHint")}
                  onChange={(e) => setForm((f) => ({ ...f, remediation_command: e.target.value }))}
                />
              </div>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">{t("auditor.directory")}</label>
              <Input
                value={form.workdir ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, workdir: e.target.value }))}
              />
            </div>
            <div className="flex items-center gap-2 pt-5">
              <input
                id={enabledId}
                type="checkbox"
                className="h-4 w-4"
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
              <label htmlFor={enabledId} className="text-sm">
                {t("auditor.enabled")}
              </label>
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">{t("auditor.description")}</label>
            <Textarea className="resize-none"
              value={form.description ?? ""}
              rows={2}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              {t("auditor.cancel")}
            </Button>
            <Button onClick={handleSave} disabled={pending || !form.name || !form.command}>
              {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("auditor.save")}
            </Button>
          </div>
      </div>
    </div>
  );
}

/** Expanded row: latest output + recent history for one check. */
function CheckHistory({ check }: { check: AuditCheck }) {
  const { t } = useTranslation("auditor");
  const { data: runs, isLoading } = useAuditRuns(check.id);
  return (
    <div className="space-y-2 border-t border-border/60 bg-muted/20 px-4 py-3">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-md border border-border/60 bg-background/60 p-3">
          <p className="mb-1 text-[10px] uppercase text-muted-foreground">{t("auditor.auditContext")}</p>
          <p className="text-xs">{check.description || t("auditor.noContext")}</p>
        </div>
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
          <p className="mb-1 text-[10px] uppercase text-amber-700 dark:text-amber-400">{t("auditor.correction")}</p>
          <p className="text-xs">
            {check.remediation_description || t("auditor.manualCorrection")}
          </p>
        </div>
      </div>
      {check.last_run?.output && (
        <div>
          <p className="mb-1 text-[10px] uppercase text-muted-foreground">{t("auditor.latestOutput")}</p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted/50 p-2 text-xs">
            {check.last_run.output}
          </pre>
        </div>
      )}
      <p className="text-[10px] uppercase text-muted-foreground">{t("auditor.recentHistory")}</p>
      {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      {runs && runs.length === 0 && <p className="text-xs text-muted-foreground">{t("auditor.neverRun")}</p>}
      {runs?.map((run) => (
        <p key={run.id} className="flex items-center gap-2 text-xs text-muted-foreground">
          <Badge variant={RUN_STATUS_BADGE[run.status]?.variant ?? "outline"} className="text-[10px]">
            {t(`auditor.state.${run.status}`)}
          </Badge>
          {formatTimestamp(run.created_at)}
          {run.duration_ms != null && <span>· {(run.duration_ms / 1000).toFixed(1)}s</span>}
          <span>
            · {run.requested_by === "cron"
              ? t("auditor.source.cron")
              : run.requested_by === "athos-remediation"
                ? t("auditor.source.athosRemediation")
                : run.requested_by === "remediation-verification"
                  ? t("auditor.source.verification")
                  : t("auditor.source.manual")}
          </span>
        </p>
      ))}
    </div>
  );
}

export default function AuditorPage() {
  const { t } = useTranslation("auditor");
  const { data: checks, isLoading, isError, error } = useAuditChecks();
  const { data: status, isError: statusError, error: statusFailure } = useAuditStatus();
  const runAll = useRunAllAuditChecks();
  const runOne = useRunAuditCheck();
  const remediate = useRemediateAuditCheck();
  const updateCheck = useUpdateAuditCheck();
  const deleteCheck = useDeleteAuditCheck();
  const [formCheck, setFormCheck] = useState<AuditCheck | "new" | null>(null);
  const [deleting, setDeleting] = useState<AuditCheck | null>(null);
  const [remediating, setRemediating] = useState<AuditCheck | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [profileFilter, setProfileFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [stateFilter, setStateFilter] = useState("all");
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const setPendingHiddenContext = useAssistantStore((s) => s.setPendingHiddenContext);
  const profiles = useMemo(
    () => Array.from(new Set((checks ?? []).map((check) => check.agent_profile))).sort(),
    [checks],
  );
  const categories = useMemo(() => Array.from(new Set((checks ?? []).map((check) => check.category).filter((item): item is string => Boolean(item)))).sort(), [checks]);
  const visibleChecks = useMemo(() => (checks ?? []).filter((check) => {
    const state = !check.enabled ? "disabled" : check.last_run?.status ?? "never";
    return (profileFilter === "all" || check.agent_profile === profileFilter)
      && (categoryFilter === "all" || check.category === categoryFilter)
      && (stateFilter === "all" || state === stateFilter);
  }), [checks, profileFilter, categoryFilter, stateFilter]);

  function handleSendToAssistant(check: AuditCheck) {
    setPendingHiddenContext(buildAuditCheckChatMessage(check));
    setAssistantOpen(true);
  }

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col gap-4 p-6">
      <ConfirmDialog
        open={deleting !== null}
        title={t("auditor.deleteTitle", { name: deleting?.name ?? "" })}
        description={t("auditor.deleteDescription")}
        loading={deleteCheck.isPending}
        onConfirm={() => {
          if (deleting) deleteCheck.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
        onCancel={() => setDeleting(null)}
      />
      <ConfirmDialog
        open={remediating !== null}
        title={t("auditor.remediateTitle", { name: remediating?.name ?? "" })}
        description={`${remediating?.remediation_description ?? t("auditor.remediateDescription")} ${t("auditor.remediateVerification")}`}
        confirmLabel={t("auditor.sendToAthos")}
        variant="default"
        icon="wrench"
        loading={remediate.isPending}
        onConfirm={() => {
          if (remediating) remediate.mutate(remediating.id, { onSuccess: () => setRemediating(null) });
        }}
        onCancel={() => setRemediating(null)}
      />

      <PageHeader title={t("auditor.title")} icon={<ClipboardCheck className="h-5 w-5" />}
        actions={<>
          <Button size="sm" className="gap-1.5" disabled={runAll.isPending} onClick={() => runAll.mutate()}>
            {runAll.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
            {t("auditor.runChecklist")}
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setFormCheck("new")}>
            <Plus className="h-4 w-4" /> {t("auditor.newCheck")}
          </Button>
          <AssistantToggleButton size="sm" />
        </>} />

      <section aria-label={t("auditor.summary")} className="grid grid-cols-2 gap-2 rounded-md border bg-card p-3 text-sm md:grid-cols-5">
        {[["enabled", status?.enabled], ["working", status?.ok], ["failed", status?.fail],
          ["neverRun", status?.never_ran], ["disabled", status ? status.total - status.enabled : undefined]].map(([label, value]) => (
          <div key={label as string} className="border-l-2 border-border pl-3 first:border-l-0">
            <p className="text-xs text-muted-foreground">{t(`auditor.${label}`)}</p>
            <p className="font-mono text-lg font-semibold tabular-nums">{value ?? "—"}</p>
          </div>
        ))}
      </section>

      <section aria-label={t("auditor.athosMonitor")} className="rounded-md border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("auditor.athosMonitor")}</p>
            <h2 className="mt-1 font-mono text-sm">{status?.athos_monitor?.job_name ?? "ecosystem-weekly-audit"}</h2>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant={status?.athos_monitor?.state === "healthy" ? "success" : status?.athos_monitor?.state === "failed" ? "destructive" : "warning"}>
              {status?.athos_monitor ? t(`auditor.monitor.${status.athos_monitor.state}`) : t("auditor.monitor.unavailable")}
            </Badge>
            <Link className="text-sm text-primary underline-offset-2 hover:underline" to="/crons">{t("auditor.openCrons")}</Link>
          </div>
        </div>
        {status?.athos_monitor ? <>
          <div className="mt-3 grid grid-cols-1 gap-2 border-t pt-3 text-xs text-muted-foreground sm:grid-cols-3">
            <p>{t("auditor.schedule")}: <code>{status.athos_monitor.schedule ?? "—"}</code></p>
            <p>{t("auditor.lastRun")}: {formatTimestamp(status.athos_monitor.last_run_at)}</p>
            <p>{t("auditor.nextRun")}: {formatTimestamp(status.athos_monitor.next_run_at)}</p>
          </div>
          {status.athos_monitor.issues.length > 0 && <ul className="mt-2 list-inside list-disc text-xs text-destructive">{status.athos_monitor.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>}
        </> : <p className="mt-2 text-sm text-muted-foreground">{t("auditor.monitorUnavailable", { reason: statusError ? (statusFailure as Error)?.message : "" })}</p>}
      </section>

      {runAll.isError && (
        <p className="text-sm text-destructive">{t("auditor.runFailed")}: {(runAll.error as Error)?.message}</p>
      )}
      {remediate.isError && (
        <p role="alert" className="text-sm text-destructive">{t("auditor.remediationFailed")}: {remediationError(remediate.error)}</p>
      )}
      {remediate.isSuccess && (
        <p
          className={
            remediate.data.escalated_to_inbox
              ? "rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300"
              : "rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300"
          }
        >
          {remediate.data.escalated_to_inbox
            ? t("auditor.remediateEscalated", { id: remediate.data.inbox_demand_id })
            : t("auditor.remediateSuccess")}
        </p>
      )}

      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("auditor.loadFailed")}: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && (checks ?? []).length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
            {t("auditor.noChecksAction")}
          </CardContent>
        </Card>
      )}

      {(checks ?? []).length > 0 && (
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2" aria-label={t("auditor.filters")}>
            <label className="text-xs">{t("auditor.category")} <select className="ml-1 rounded border bg-background p-1" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="all">{t("auditor.all")}</option>{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
            <label className="text-xs">{t("auditor.status")} <select className="ml-1 rounded border bg-background p-1" value={stateFilter} onChange={(event) => setStateFilter(event.target.value)}><option value="all">{t("auditor.all")}</option>{["ok", "fail", "error", "timeout", "never", "disabled"].map((state) => <option key={state} value={state}>{t(`auditor.state.${state}`)}</option>)}</select></label>
            <span className="mr-1 text-xs font-medium text-muted-foreground">{t("auditor.profiles")}:</span>
            {["all", ...profiles].map((profile) => (
              <Button
                key={profile}
                size="sm"
                variant={profileFilter === profile ? "default" : "outline"}
                className="h-7 capitalize"
                onClick={() => setProfileFilter(profile)}
              >
                {profile === "all" ? `${t("auditor.all")} (${(checks ?? []).length})` : `${profile} (${(checks ?? []).filter((check) => check.agent_profile === profile).length})`}
              </Button>
            ))}
          </div>
          <Card className="min-h-0 flex-1 overflow-hidden">
          <CardContent className="h-full overflow-auto p-0">
            {formCheck === "new" && (
              <div className="border-b border-border p-4">
                <CheckFormPanel key="new" initial={null} onClose={() => setFormCheck(null)} />
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("auditor.check")}</TableHead>
                  <TableHead>{t("auditor.category")}</TableHead>
                  <TableHead>{t("auditor.agent")}</TableHead>
                  <TableHead>{t("auditor.status")}</TableHead>
                  <TableHead>{t("auditor.lastRun")}</TableHead>
                  <TableHead className="text-right">{t("auditor.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleChecks.map((check) => {
                  const isOpen = expanded.has(check.id);
                  const badge = check.last_run ? RUN_STATUS_BADGE[check.last_run.status] : null;
                  return (
                    <Fragment key={check.id}>
                      <TableRow key={check.id} className={!check.enabled ? "opacity-60" : undefined}>
                        <TableCell>
                          <button
                            type="button"
                            className="flex items-start gap-1.5 text-left"
                            onClick={() => toggleExpand(check.id)}
                          >
                            {isOpen ? (
                              <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                            )}
                            <span>
                              <span className="font-medium">{check.name}</span>
                              {check.description && (
                                <p className="max-w-md truncate text-xs text-muted-foreground" title={check.description}>
                                  {check.description}
                                </p>
                              )}
                              <code className="block max-w-md truncate text-[11px] text-muted-foreground" title={check.command}>
                                {check.command}
                              </code>
                            </span>
                          </button>
                        </TableCell>
                        <TableCell>
                          {check.category ? <Badge variant="outline">{check.category}</Badge> : "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">{check.agent_profile}</TableCell>
                        <TableCell>
                          {!check.enabled ? (
                            <Badge variant="outline">{t("auditor.disabled")}</Badge>
                          ) : badge ? (
                            <Badge variant={badge.variant}>{t(`auditor.state.${check.last_run?.status}`)}</Badge>
                          ) : (
                            <Badge variant="outline">{t("auditor.neverRun")}</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatTimestamp(check.last_run?.created_at)}
                          {check.last_run?.duration_ms != null && (
                            <span className="block text-xs">{(check.last_run.duration_ms / 1000).toFixed(1)}s</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-0.5">
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`${t("auditor.run")} ${check.name}`}
                              title={t("auditor.run")}
                              disabled={runOne.isPending && runOne.variables === check.id}
                              onClick={() => runOne.mutate(check.id)}
                            >
                              {runOne.isPending && runOne.variables === check.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Play className="h-4 w-4" />
                              )}
                            </Button>
                            {check.remediation_command && check.last_run && check.last_run.status !== "ok" && (
                              <Button
                                variant="ghost"
                                size="icon"
                                aria-label={`${t("auditor.remediate")} ${check.name}`}
                                title={t("auditor.remediateHint")}
                                className="text-amber-600"
                                disabled={remediate.isPending}
                                onClick={() => setRemediating(check)}
                              >
                                <Wrench className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`${t("auditor.sendToAssistant")} ${check.name}`}
                              title={t("auditor.sendToAssistant")}
                              onClick={() => handleSendToAssistant(check)}
                            >
                              <Bot className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`${check.enabled ? t("auditor.disable") : t("auditor.enable")} ${check.name}`}
                              title={check.enabled ? t("auditor.disable") : t("auditor.enable")}
                              onClick={() =>
                                updateCheck.mutate({ checkId: check.id, updates: { enabled: !check.enabled } })
                              }
                            >
                              <Power className={check.enabled ? "h-4 w-4 text-emerald-600" : "h-4 w-4 text-muted-foreground"} />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`${t("auditor.edit")} ${check.name}`}
                              title={formCheck !== "new" && formCheck?.id === check.id ? t("auditor.closeEditor") : t("auditor.edit")}
                              className={formCheck !== "new" && formCheck?.id === check.id ? "bg-accent text-accent-foreground" : undefined}
                              onClick={() =>
                                setFormCheck((current) =>
                                  current !== "new" && current?.id === check.id ? null : check,
                                )
                              }
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`${t("auditor.delete")} ${check.name}`}
                              title={t("auditor.delete")}
                              className="text-destructive"
                              onClick={() => setDeleting(check)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                      {formCheck !== "new" && formCheck?.id === check.id && (
                        <TableRow key={`${check.id}-editor`} className="hover:bg-transparent">
                          <TableCell colSpan={6} className="bg-muted/10 p-3">
                            <CheckFormPanel key={check.id} initial={check} onClose={() => setFormCheck(null)} />
                          </TableCell>
                        </TableRow>
                      )}
                      {isOpen && (
                        <TableRow key={`${check.id}-history`}>
                          <TableCell colSpan={6} className="p-0">
                            <CheckHistory check={check} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
            {visibleChecks.length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">{t("auditor.noResults")}</p>}
          </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
