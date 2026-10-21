import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CloudUpload,
  History,
  Loader2,
  Pencil,
  Play,
  Plus,
  Power,
  PowerOff,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  offsiteTargetFormDefaults,
  offsiteTargetFormSchema,
  slugifyTargetName,
  useOffsiteBackupRuns,
  usePostgresContainers,
  type OffsiteBackupRun,
  type OffsiteBackupTarget,
  type OffsiteTargetFormInput,
} from "@/hooks/useOffsiteBackup";
import { useOffsiteBackupViewModel, type OffsiteBackupViewModel, type OffsiteError } from "@/hooks/useOffsiteBackupViewModel";
import { cn } from "@/lib/utils";

/** Decimal units, like the other System Control cards. */
function formatSize(bytes: number, locale: string): string {
  if (bytes < 1000) return `${new Intl.NumberFormat(locale).format(bytes)} B`;
  const units = ["kB", "MB", "GB", "TB"];
  let value = bytes / 1000;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: value >= 100 ? 0 : 1 }).format(value)} ${units[unit]}`;
}

function formatDateTime(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(locale, { dateStyle: "short", timeStyle: "short" });
}

const STATUS_VARIANT: Record<OffsiteBackupRun["status"], "success" | "destructive" | "warning" | "secondary"> = {
  ok: "success",
  failed: "destructive",
  interrupted: "warning",
  running: "secondary",
};

function RunBadge({ run }: { run: OffsiteBackupRun }) {
  const { t } = useTranslation("systemControl");
  return (
    <Badge variant={STATUS_VARIANT[run.status]} className="gap-1 whitespace-nowrap">
      {run.status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
      {t(`offsiteBackup.status.${run.status}`)}
    </Badge>
  );
}

function errorText(t: (key: string, options?: Record<string, unknown>) => string, error: OffsiteError): string {
  return t(`offsiteBackup.errors.${error.code}`, { detail: error.detail });
}

/** System Control -> "Backup externo" (2026-10-20): what goes to the encrypted
 * Google Drive repository, one target per project, and how each last run went. */
export function OffsiteBackupCard() {
  const { t, i18n } = useTranslation("systemControl");
  const vm = useOffsiteBackupViewModel();
  const data = vm.data;
  const busy = vm.status === "submitting";
  const maintenance = data?.repository_maintenance;

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <CloudUpload className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">{t("offsiteBackup.title")}</h2>
            {data && (
              <span className="text-xs text-muted-foreground">
                {t("offsiteBackup.summary", { count: vm.enabledCount, total: data.targets.length })}
              </span>
            )}
            {data?.running && (
              <Badge variant="secondary" className="gap-1">
                <Loader2 className="h-3 w-3 animate-spin" /> {t("offsiteBackup.runningNow")}
              </Badge>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button size="sm" variant="outline" className="gap-2" onClick={vm.refresh} disabled={vm.refreshing}>
              <RefreshCw className={cn("h-4 w-4", vm.refreshing && "animate-spin")} />
              {t("offsiteBackup.refresh")}
            </Button>
            <Button size="sm" variant="outline" className="gap-2" onClick={vm.openCreate} disabled={!data}>
              <Plus className="h-4 w-4" />
              {t("offsiteBackup.add")}
            </Button>
            <Button
              size="sm"
              className="gap-2"
              onClick={() => void vm.runAll()}
              disabled={!data || busy || data.running || vm.enabledCount === 0}
            >
              {vm.startingTarget === "all" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {t("offsiteBackup.runAll")}
            </Button>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">{t("offsiteBackup.description")}</p>

        {data && (
          <div className="grid grid-cols-1 gap-1 rounded-md border border-border bg-muted/30 p-2 text-xs sm:grid-cols-2">
            <div className="min-w-0 break-all">
              <span className="text-muted-foreground">{t("offsiteBackup.repository")}: </span>
              <span className="font-mono">{data.repository}</span>
            </div>
            <div className="min-w-0">
              <span className="text-muted-foreground">{t("offsiteBackup.schedule")}: </span>
              {data.schedule ? (
                <span>
                  <span className="font-mono">{data.schedule.expression}</span>
                  {!data.schedule.enabled && <span className="text-amber-600"> · {t("offsiteBackup.schedulePaused")}</span>}
                  {data.schedule.enabled && data.schedule.next_run_at && (
                    <span> · {t("offsiteBackup.nextRun", { when: formatDateTime(data.schedule.next_run_at, i18n.language) })}</span>
                  )}
                </span>
              ) : (
                <span className="text-amber-600">
                  {data.schedule_error === "not_scheduled"
                    ? t("offsiteBackup.notScheduled")
                    : t("offsiteBackup.scheduleUnknown", { detail: data.schedule_error ?? "" })}
                </span>
              )}
            </div>
            <div className="min-w-0 sm:col-span-2">
              <span className="text-muted-foreground">{t("offsiteBackup.maintenance")}: </span>
              {maintenance ? (
                <span className="inline-flex flex-wrap items-center gap-1">
                  <RunBadge run={maintenance} /> {formatDateTime(maintenance.finished_at ?? maintenance.started_at, i18n.language)}
                  {maintenance.error && <span className="break-all text-destructive">{maintenance.error}</span>}
                </span>
              ) : (
                <span>{t("offsiteBackup.maintenanceNever")}</span>
              )}
            </div>
          </div>
        )}

        {vm.status === "loading" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> {t("offsiteBackup.loading")}
          </p>
        )}
        {vm.loadError && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">
            {errorText(t, vm.loadError)}
          </p>
        )}
        {vm.actionError && (
          <p className="break-words rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">
            {errorText(t, vm.actionError)}
          </p>
        )}
        {vm.startedTargets && (
          <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-sm">
            {t("offsiteBackup.started", { count: vm.startedTargets.length })}
          </p>
        )}

        {data && data.targets.length === 0 && <p className="text-sm text-muted-foreground">{t("offsiteBackup.empty")}</p>}

        {data && data.targets.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("offsiteBackup.columns.target")}</TableHead>
                <TableHead>{t("offsiteBackup.columns.paths")}</TableHead>
                <TableHead>{t("offsiteBackup.columns.database")}</TableHead>
                <TableHead>{t("offsiteBackup.columns.lastRun")}</TableHead>
                <TableHead className="text-right">{t("offsiteBackup.columns.actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.targets.map((target) => (
                <TargetRows key={target.id} target={target} vm={vm} locale={i18n.language} running={data.running} />
              ))}
            </TableBody>
          </Table>
        )}

        {vm.dialog && <TargetDialog vm={vm} />}

        <ConfirmDialog
          open={vm.deleting !== null}
          title={t("offsiteBackup.deleteTitle")}
          description={t("offsiteBackup.deleteDescription", { name: vm.deleting?.label ?? "" })}
          confirmLabel={t("offsiteBackup.deleteConfirm")}
          loading={busy}
          dismissDisabled={busy}
          onConfirm={() => void vm.confirmDelete()}
          onCancel={vm.cancelDelete}
        />
      </CardContent>
    </Card>
  );
}

function TargetRows({
  target,
  vm,
  locale,
  running,
}: {
  target: OffsiteBackupTarget;
  vm: OffsiteBackupViewModel;
  locale: string;
  running: boolean;
}) {
  const { t } = useTranslation("systemControl");
  const last = target.last_run;
  const success = target.last_success;
  const stale = vm.isStale(target);
  const busy = vm.status === "submitting";
  const historyOpen = vm.historyFor === target.name;

  return (
    <>
      <TableRow className={cn(!target.enabled && "opacity-60")}>
        <TableCell className="min-w-[9rem] align-top">
          <div className="font-medium">{target.label}</div>
          <div className="font-mono text-xs text-muted-foreground">{target.name}</div>
          {!target.enabled && <Badge variant="outline" className="mt-1">{t("offsiteBackup.disabled")}</Badge>}
          {target.include_system_state && (
            <Badge variant="outline" className="mt-1">{t("offsiteBackup.systemState")}</Badge>
          )}
        </TableCell>
        <TableCell className="min-w-[16rem] max-w-[22rem] align-top">
          <ul className="space-y-0.5 font-mono text-xs">
            {target.paths.map((path) => (
              <li key={path} className="break-all">{path}</li>
            ))}
          </ul>
          {target.excludes.length > 0 && (
            <div className="mt-1 text-xs text-muted-foreground" title={target.excludes.join("\n")}>
              {t("offsiteBackup.excludesCount", { count: target.excludes.length })}
            </div>
          )}
        </TableCell>
        <TableCell className="align-top font-mono text-xs">{target.postgres_container ?? "—"}</TableCell>
        <TableCell className="min-w-[13rem] align-top text-xs">
          {last ? (
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-1">
                <RunBadge run={last} />
                <span className="text-muted-foreground">{formatDateTime(last.finished_at ?? last.started_at, locale)}</span>
              </div>
              {last.status === "ok" && last.data_added !== null && (
                <div className="text-muted-foreground">
                  {t("offsiteBackup.added", { size: formatSize(last.data_added, locale) })}
                  {last.snapshot_id && <span className="font-mono"> · {last.snapshot_id}</span>}
                </div>
              )}
              {last.error && (
                <div className="line-clamp-3 break-all text-destructive" title={last.error}>
                  {last.error}
                </div>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground">{t("offsiteBackup.never")}</span>
          )}
          {stale && (
            <div className="mt-1 flex items-center gap-1 text-amber-600">
              <AlertTriangle className="h-3 w-3 shrink-0" />
              {success
                ? t("offsiteBackup.staleSince", { when: formatDateTime(success.finished_at, locale) })
                : t("offsiteBackup.noSuccess")}
            </div>
          )}
        </TableCell>
        <TableCell className="align-top">
          <div className="flex justify-end gap-0.5">
            <Button
              size="icon"
              variant="ghost"
              title={t("offsiteBackup.runOne")}
              aria-label={t("offsiteBackup.runOne")}
              onClick={() => void vm.runTarget(target)}
              disabled={!target.enabled || busy || running}
            >
              {vm.startingTarget === target.name ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            </Button>
            <Button
              size="icon"
              variant={historyOpen ? "secondary" : "ghost"}
              title={t("offsiteBackup.history")}
              aria-label={t("offsiteBackup.history")}
              onClick={() => vm.toggleHistory(target)}
            >
              <History className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title={t("offsiteBackup.edit")}
              aria-label={t("offsiteBackup.edit")}
              onClick={() => vm.openEdit(target)}
              disabled={busy}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title={target.enabled ? t("offsiteBackup.disable") : t("offsiteBackup.enable")}
              aria-label={target.enabled ? t("offsiteBackup.disable") : t("offsiteBackup.enable")}
              onClick={() => void vm.toggleEnabled(target)}
              disabled={busy}
            >
              {target.enabled ? <PowerOff className="h-4 w-4" /> : <Power className="h-4 w-4" />}
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="text-destructive"
              title={t("offsiteBackup.delete")}
              aria-label={t("offsiteBackup.delete")}
              onClick={() => vm.requestDelete(target)}
              disabled={busy}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </TableCell>
      </TableRow>
      {historyOpen && (
        <TableRow>
          <TableCell colSpan={5} className="bg-muted/30">
            <RunHistory target={target.name} locale={locale} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function RunHistory({ target, locale }: { target: string; locale: string }) {
  const { t } = useTranslation("systemControl");
  const runs = useOffsiteBackupRuns(target);
  if (runs.isLoading) {
    return (
      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> {t("offsiteBackup.loading")}
      </p>
    );
  }
  if (!runs.data?.length) return <p className="text-xs text-muted-foreground">{t("offsiteBackup.never")}</p>;
  return (
    <ul className="space-y-1 text-xs">
      {runs.data.map((run) => (
        <li key={run.id} className="flex flex-wrap items-center gap-2">
          <RunBadge run={run} />
          <span>{formatDateTime(run.started_at, locale)}</span>
          <span className="text-muted-foreground">{t(`offsiteBackup.trigger.${run.trigger}`)}</span>
          {run.status === "ok" && run.data_added !== null && (
            <span className="text-muted-foreground">
              {t("offsiteBackup.added", { size: formatSize(run.data_added, locale) })}
              {run.snapshot_id && <span className="font-mono"> · {run.snapshot_id}</span>}
            </span>
          )}
          {run.error && <span className="min-w-0 basis-full break-all text-destructive">{run.error}</span>}
        </li>
      ))}
    </ul>
  );
}

function TargetDialog({ vm }: { vm: OffsiteBackupViewModel }) {
  const { t } = useTranslation("systemControl");
  const dialog = vm.dialog!;
  const editing = dialog.mode === "edit";
  const containers = usePostgresContainers(true);
  const { register, handleSubmit, formState, watch, setValue, getFieldState } = useForm<OffsiteTargetFormInput>({
    resolver: zodResolver(offsiteTargetFormSchema),
    defaultValues: offsiteTargetFormDefaults(editing ? dialog.target : undefined),
  });
  const label = watch("label");
  const currentContainer = watch("postgres_container");

  // Suggest the identifier from the name until the operator types one.
  useEffect(() => {
    if (!editing && !getFieldState("name").isDirty) setValue("name", slugifyTargetName(label));
  }, [editing, label, getFieldState, setValue]);

  const fieldError = (name: keyof OffsiteTargetFormInput) => {
    const message = formState.errors[name]?.message;
    return message ? <span className="text-xs text-destructive">{t(`offsiteBackup.form.errors.${String(message)}`)}</span> : null;
  };
  const containerOptions = Array.from(
    new Set([...(containers.data?.containers ?? []), ...(currentContainer ? [currentContainer] : [])]),
  ).sort();

  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4">
      <div className="fixed inset-0 bg-black/60" onClick={vm.closeDialog} aria-hidden />
      <div role="dialog" aria-modal="true" className="relative my-auto w-full max-w-2xl space-y-4 rounded-lg border bg-background p-5 shadow-xl">
        <h2 className="text-lg font-semibold">{t(editing ? "offsiteBackup.form.editTitle" : "offsiteBackup.form.createTitle")}</h2>
        <form onSubmit={handleSubmit((input) => vm.submit(input))} className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="ob-label">{t("offsiteBackup.form.label")}</Label>
              <Input id="ob-label" className="max-md:text-base" {...register("label")} />
              {fieldError("label")}
            </div>
            <div className="space-y-1">
              <Label htmlFor="ob-name">{t("offsiteBackup.form.name")}</Label>
              <Input id="ob-name" className="font-mono max-md:text-base" disabled={editing} {...register("name")} />
              <span className="text-xs text-muted-foreground">{t("offsiteBackup.form.nameHint")}</span>
              {fieldError("name")}
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ob-paths">{t("offsiteBackup.form.paths")}</Label>
            <Textarea
              id="ob-paths"
              rows={4}
              className="font-mono text-xs max-md:text-base"
              placeholder="/root/project/meu-projeto"
              {...register("paths")}
            />
            <span className="text-xs text-muted-foreground">{t("offsiteBackup.form.pathsHint")}</span>
            {fieldError("paths")}
          </div>
          <div className="space-y-1">
            <Label htmlFor="ob-excludes">{t("offsiteBackup.form.excludes")}</Label>
            <Textarea
              id="ob-excludes"
              rows={3}
              className="font-mono text-xs max-md:text-base"
              placeholder="*.log"
              {...register("excludes")}
            />
            <span className="text-xs text-muted-foreground">{t("offsiteBackup.form.excludesHint")}</span>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ob-container">{t("offsiteBackup.form.container")}</Label>
            <Select id="ob-container" {...register("postgres_container")}>
              <option value="">{t("offsiteBackup.form.noContainer")}</option>
              {containerOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
            <span className="text-xs text-muted-foreground">
              {containers.isError ? t("offsiteBackup.form.containersFailed") : t("offsiteBackup.form.containerHint")}
            </span>
          </div>
          <div className="space-y-2">
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4" {...register("include_system_state")} />
              <span>
                {t("offsiteBackup.form.systemState")}
                <span className="block text-xs text-muted-foreground">{t("offsiteBackup.form.systemStateHint")}</span>
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4" {...register("enabled")} />
              {t("offsiteBackup.form.enabled")}
            </label>
          </div>
          {vm.formError && <p className="break-words text-sm text-destructive">{errorText(t, vm.formError)}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={vm.closeDialog} disabled={vm.saving}>
              {t("offsiteBackup.form.cancel")}
            </Button>
            <Button type="submit" disabled={vm.saving}>
              {vm.saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t(editing ? "offsiteBackup.form.save" : "offsiteBackup.form.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
