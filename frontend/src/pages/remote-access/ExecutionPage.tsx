/**
 * Execution screen (Remote Access phase 4, Marcelo 2026-10-15): per machine,
 * what came back -- stdout/stderr, exit code, duration -- and a clear verdict.
 * From a failed run, a fix can be run on the failed machines only; it is
 * linked to this one, so the history reads failure -> fix -> result.
 */
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronRight, CornerDownRight, Lightbulb, Loader2, Play, Square, TerminalSquare, Wrench } from "lucide-react";

import { CopyButton } from "@/components/CopyButton";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useExecutionViewModel } from "@/hooks/useExecutionViewModel";
import { detectKnownFailure, formatDuration, type HostExecutionResult, type KnownFailure } from "@/hooks/useHostExecutions";
import { VerdictBadge } from "./VerdictBadge";

/** What to do about a failure ForgeHub recognizes (detectKnownFailure),
 * shown on the machine's row without having to open the raw output. */
function KnownFailureHint({ failure }: { failure: KnownFailure }) {
  const { t } = useTranslation("remoteAccess");
  const k = `knownFailure.${failure.kind}`;
  const owner = failure.owner ?? t(`${k}.someone`);
  const steps = t(`${k}.steps`, { returnObjects: true, owner }) as unknown as string[];
  return (
    <div role="note" className="mt-3 ml-7 space-y-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
      <p className="flex items-start gap-2 font-medium">
        <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
        {t(`${k}.title`)}
      </p>
      <p className="text-muted-foreground">{t(`${k}.why`, { owner })}</p>
      <ol className="list-decimal space-y-1 pl-5">
        {steps.map((step, i) => <li key={i}>{step}</li>)}
      </ol>
    </div>
  );
}

function OutputBlock({ label, text, tone }: { label: string; text: string | null; tone?: "error" }) {
  if (!text) return null;
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <pre className={`max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-md border p-3 font-mono text-xs ${tone === "error" ? "border-destructive/30 bg-destructive/5" : "border-border bg-muted/40"}`}>
        {text}
      </pre>
    </div>
  );
}

export default function ExecutionPage() {
  const { id } = useParams<{ id: string }>();
  const { t, i18n } = useTranslation("remoteAccess");
  const navigate = useNavigate();
  const vm = useExecutionViewModel(id, (next) => navigate(`/remote-access/executions/${next.id}`));
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "medium" });

  useEffect(() => {
    document.title = `${t("execution.title")} · ForgeHub`;
  }, [t]);

  const back = (
    <Link to="/remote-access" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" /> {t("title")}
    </Link>
  );

  if (vm.status === "loading") {
    return <div className="flex min-h-64 items-center justify-center" role="status"><Loader2 className="h-5 w-5 motion-safe:animate-spin" aria-label={t("loading")} /></div>;
  }
  if (vm.status !== "ready" || !vm.execution) {
    return (
      <div className="space-y-4">
        {back}
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          {t(vm.status === "not_found" ? "execution.notFound" : "execution.loadFailed")}
        </p>
      </div>
    );
  }

  const e = vm.execution;
  const knownFailureOf = (r: HostExecutionResult) =>
    r.status === "failed" ? detectKnownFailure([r.stderr, r.stdout].filter(Boolean).join("\n")) : null;
  const resultDetail = (r: HostExecutionResult, known: KnownFailure | null) => {
    if (r.status === "skipped") return r.skip_reason;
    if (known) return t(`knownFailure.${known.kind}.short`);
    if (r.status === "failed" && r.failure) return t(`failure.${r.failure}`);
    return null;
  };

  return (
    <div className="space-y-6 max-md:break-words">
      {back}
      <PageHeader
        icon={<TerminalSquare className="h-7 w-7 text-primary" aria-hidden="true" />}
        title={t("execution.title")}
        description={t("execution.subtitle", { who: e.requested_by, when: fmt.format(new Date(e.started_at)), targets: e.target_summary ?? "—" })}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <VerdictBadge verdict={e.verdict} />
            {e.status === "cancelled" && <Badge variant="outline">{t("execution.cancelled")}</Badge>}
            {vm.canCancel && (
              <Button type="button" variant="outline" size="sm" onClick={vm.askCancel} className="cursor-pointer gap-1.5">
                <Square className="h-3.5 w-3.5" aria-hidden="true" /> {t("execution.cancel")}
              </Button>
            )}
            {vm.failedResults.length > 0 && e.verdict !== "running" && (
              <Button type="button" size="sm" onClick={vm.followUp.start} className="cursor-pointer gap-1.5 max-md:h-auto max-md:whitespace-normal">
                <Wrench className="h-3.5 w-3.5" aria-hidden="true" /> {t("execution.fixFailed", { count: vm.failedResults.length })}
              </Button>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(["succeeded", "failed", "skipped", "running"] as const).map((k) => (
          <div key={k} className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">{t(`verdict.${k}`)}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {k === "running" ? e.counts.running + e.counts.pending : e.counts[k]}
            </p>
          </div>
        ))}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center gap-2 space-y-0 pb-3">
          <CardTitle className="text-base">{t("execution.command", { shell: t(`run.shells.${e.shell}`) })}</CardTitle>
          {/* Copies the command as stored: secrets stay masked (********). */}
          <CopyButton getText={() => e.command} title={t("execution.copyCommand")} />
        </CardHeader>
        <CardContent className="space-y-3">
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">{e.command}</pre>
          {e.parent_execution_id && (
            <Link to={`/remote-access/executions/${e.parent_execution_id}`} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
              <CornerDownRight className="h-3 w-3" aria-hidden="true" /> {t("execution.parent")}
            </Link>
          )}
          {e.follow_up_ids.length > 0 && (
            <ul className="space-y-1">
              {e.follow_up_ids.map((fid, i) => (
                <li key={fid}>
                  <Link to={`/remote-access/executions/${fid}`} className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
                    <Wrench className="h-3 w-3" aria-hidden="true" /> {t("execution.followUpLink", { n: i + 1 })}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {vm.followUp.open && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t("execution.fixTitle", { count: vm.failedResults.length })}</CardTitle>
            <p className="text-xs text-muted-foreground">{vm.failedResults.map((r) => r.server_name).join(", ")}</p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="fix-shell">{t("run.shell")}</Label>
                <Select id="fix-shell" value={vm.followUp.shell} onChange={(ev) => vm.followUp.setShell(ev.target.value as "sh" | "powershell")} className="max-md:text-base">
                  <option value="sh">{t("run.shells.sh")}</option>
                  <option value="powershell">{t("run.shells.powershell")}</option>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="fix-timeout">{t("run.timeout")}</Label>
                <Input id="fix-timeout" type="number" min={5} max={1800} value={vm.followUp.timeoutSeconds}
                  onChange={(ev) => vm.followUp.setTimeoutSeconds(Number(ev.target.value) || 300)} className="max-md:text-base" />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="fix-command">{t("run.command")}</Label>
              <Textarea id="fix-command" value={vm.followUp.command} onChange={(ev) => vm.followUp.setCommand(ev.target.value)}
                className="min-h-[120px] font-mono text-xs max-md:text-base" spellCheck={false} />
            </div>
            {vm.followUp.error && <p role="alert" className="text-xs text-destructive">{vm.followUp.error}</p>}
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={vm.followUp.close} disabled={vm.followUp.submitting} className="cursor-pointer">{t("cancel")}</Button>
              <Button type="button" size="sm" onClick={vm.followUp.submit} disabled={vm.followUp.submitting || !vm.followUp.command.trim()} className="cursor-pointer gap-1.5">
                {vm.followUp.submitting ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Play className="h-3.5 w-3.5" aria-hidden="true" />}
                {t("execution.runFix", { count: vm.failedResults.length })}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t("execution.perMachine")}</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border p-0">
          {e.results.map((r) => {
            const open = vm.expanded.has(r.id);
            const hasOutput = Boolean(r.stdout || r.stderr);
            const known = knownFailureOf(r);
            const detail = resultDetail(r, known);
            return (
              <section key={r.id} className="px-6 py-3">
                <button
                  type="button"
                  onClick={() => vm.toggleExpanded(r.id)}
                  disabled={!hasOutput}
                  aria-expanded={open}
                  className="flex w-full cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 text-left disabled:cursor-default"
                >
                  {hasOutput ? (open ? <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" /> : <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />) : <span className="w-4" />}
                  <span className="font-medium">{r.server_name}</span>
                  <VerdictBadge verdict={r.status} />
                  {r.exit_code !== null && <span className="font-mono text-xs text-muted-foreground">{t("execution.exitCode", { code: r.exit_code })}</span>}
                  <span className="text-xs text-muted-foreground">{formatDuration(r.duration_ms)}</span>
                  {detail && <span className="text-xs text-muted-foreground">· {detail}</span>}
                </button>
                {known && <KnownFailureHint failure={known} />}
                {open && (
                  <div className="mt-3 space-y-3 pl-7">
                    <OutputBlock label={t("execution.stdout")} text={r.stdout} />
                    <OutputBlock label={t("execution.stderr")} text={r.stderr} tone="error" />
                    {r.truncated && <p className="text-xs text-muted-foreground">{t("execution.truncated")}</p>}
                  </div>
                )}
              </section>
            );
          })}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={vm.confirmingCancel}
        title={t("execution.cancelTitle")}
        description={t("execution.cancelDescription", { count: e.counts.pending })}
        confirmLabel={t("execution.cancel")}
        cancelLabel={t("cancel")}
        loading={vm.cancelling}
        dismissDisabled={vm.cancelling}
        error={vm.cancelError}
        onConfirm={vm.confirmCancel}
        onCancel={vm.dismissCancel}
      />
    </div>
  );
}
