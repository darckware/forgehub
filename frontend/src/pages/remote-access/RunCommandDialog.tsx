/** "Run a command" on machines/groups (Remote Access phase 4). Two steps:
 * compose, then review what will run where before it is sent. State lives in
 * useRunCommandViewModel. */
import { useTranslation } from "react-i18next";
import { Loader2, Play, TerminalSquare, TriangleAlert, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { HostExecutionDetail } from "@/hooks/useHostExecutions";
import { useRunCommandViewModel } from "@/hooks/useRunCommandViewModel";

export function RunCommandDialog({
  onClose,
  onStarted,
  initialServerIds,
}: {
  onClose: () => void;
  onStarted: (execution: HostExecutionDetail) => void;
  initialServerIds?: string[];
}) {
  const { t } = useTranslation("remoteAccess");
  const vm = useRunCommandViewModel(onStarted, initialServerIds);
  const busy = vm.status === "submitting";

  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true" aria-labelledby="run-command-title">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <div className="relative z-10 my-auto flex w-full max-w-2xl flex-col rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id="run-command-title" className="flex items-center gap-2 text-base font-semibold">
            <TerminalSquare className="h-4 w-4" aria-hidden="true" /> {t("run.title")}
          </h2>
          <button type="button" onClick={onClose} disabled={busy} aria-label={t("cancel")} className="cursor-pointer text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {vm.status === "idle" ? (
          <div className="space-y-4 px-6 py-4">
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">{t("run.targets")}</legend>
              {vm.groups.length > 0 && (
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {vm.groups.map((g) => (
                    <label key={g.id} className="flex items-center gap-1.5 text-sm">
                      <input type="checkbox" checked={vm.groupIds.has(g.id)} onChange={() => vm.toggleGroup(g.id)} />
                      {t("run.groupLabel", { name: g.name, size: g.size })}
                      {g.clientName && <span className="text-xs text-muted-foreground">· {g.clientName}</span>}
                    </label>
                  ))}
                </div>
              )}
              <div className="max-h-40 overflow-y-auto rounded-md border border-border p-2">
                {vm.machines.map((m) => (
                  <label key={m.id} className="flex items-center gap-1.5 py-0.5 text-sm">
                    <input type="checkbox" checked={vm.serverIds.has(m.id)} onChange={() => vm.toggleServer(m.id)} />
                    <span className="font-medium">{m.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {[m.os_family ? t(`os.${m.os_family}`) : null, m.darckware_client_name].filter(Boolean).join(" · ")}
                    </span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{t("run.targetCount", { count: vm.targetCount })}</p>
            </fieldset>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="run-shell">{t("run.shell")}</Label>
                <Select id="run-shell" value={vm.shell} onChange={(e) => vm.setShell(e.target.value as "sh" | "powershell")} className="max-md:text-base">
                  <option value="sh">{t("run.shells.sh")}</option>
                  <option value="powershell">{t("run.shells.powershell")}</option>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="run-timeout">{t("run.timeout")}</Label>
                <Input
                  id="run-timeout"
                  type="number"
                  min={5}
                  max={1800}
                  value={vm.timeoutSeconds}
                  onChange={(e) => vm.setTimeoutSeconds(Number(e.target.value) || 300)}
                  className="max-md:text-base"
                />
              </div>
            </div>
            {vm.mixedOs && (
              <p className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
                <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden="true" />
                {t("run.mixedOs")}
              </p>
            )}

            <div className="space-y-1">
              <Label htmlFor="run-command">{t("run.command")}</Label>
              <Textarea
                id="run-command"
                value={vm.command}
                onChange={(e) => vm.setCommand(e.target.value)}
                placeholder={vm.shell === "powershell" ? "Get-ComputerInfo | Select-Object OsName, OsVersion" : "uname -a && df -h"}
                className="min-h-[140px] font-mono text-xs max-md:text-base"
                spellCheck={false}
              />
              <p className="text-[11px] text-muted-foreground">{t("run.maskingNote")}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3 px-6 py-4">
            <p className="text-sm">{t("run.reviewSummary", { count: vm.targetCount, shell: t(`run.shells.${vm.shell}`), timeout: vm.timeoutSeconds })}</p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">{vm.command}</pre>
            <p className="text-xs text-muted-foreground">{t("run.reviewNote")}</p>
            {vm.error && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-6 py-4">
          {vm.status === "idle" ? (
            <>
              <Button type="button" variant="outline" size="sm" onClick={onClose} className="cursor-pointer">{t("cancel")}</Button>
              <Button type="button" size="sm" onClick={vm.review} disabled={!vm.canReview} className="cursor-pointer">{t("run.review")}</Button>
            </>
          ) : (
            <>
              <Button type="button" variant="outline" size="sm" onClick={vm.back} disabled={busy} className="cursor-pointer">{t("run.back")}</Button>
              <Button type="button" size="sm" onClick={vm.submit} disabled={busy} className="cursor-pointer gap-1.5">
                {busy ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Play className="h-3.5 w-3.5" aria-hidden="true" />}
                {t("run.confirm", { count: vm.targetCount })}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
