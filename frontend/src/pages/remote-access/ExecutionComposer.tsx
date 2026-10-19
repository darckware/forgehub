/** Single execution screen: machines on the left, script + parameters + when
 * on the right, a review step before anything runs or is scheduled. State:
 * useExecutionComposerViewModel. */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarClock, Check, ClipboardCopy, Copy, KeyRound, Loader2, Play, Search, TriangleAlert, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useExecutionComposerViewModel, type WhenMode } from "@/hooks/useExecutionComposerViewModel";
import type { HostExecutionDetail } from "@/hooks/useHostExecutions";
import type { HostSchedule } from "@/hooks/useHostScripts";
import { scriptFits } from "@/hooks/useHostScripts";
import { cn } from "@/lib/utils";
import { STATUS_DOT, statusKey } from "./machineStatus";

const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7];

export function ExecutionComposer({
  onRan,
  onScheduled,
  initialSystem,
}: {
  onRan: (execution: HostExecutionDetail) => void;
  onScheduled: (schedule: HostSchedule) => void;
  initialSystem?: string | null;
}) {
  const { t } = useTranslation("remoteAccess");
  const vm = useExecutionComposerViewModel({ onRan, onScheduled, initialSystem });
  const [copied, setCopied] = useState(false);
  const busy = vm.status === "submitting";

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <Card>
        <CardHeader className="space-y-3 pb-3">
          <CardTitle className="text-base">{t("composer.machines", { count: vm.selected.size })}</CardTitle>
          <label className="relative block">
            <span className="sr-only">{t("composer.search")}</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input value={vm.filters.query} onChange={(e) => vm.setFilters({ query: e.target.value })} placeholder={t("composer.search")} className="pl-8 max-md:text-base" />
          </label>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <Select aria-label={t("composer.client")} value={vm.filters.clientId} onChange={(e) => vm.setFilters({ clientId: e.target.value })} className="max-md:text-base">
              <option value="">{t("composer.allClients")}</option>
              {vm.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              <option value="none">{t("workstations.noClient")}</option>
            </Select>
            <Select aria-label={t("composer.group")} value={vm.filters.groupId} onChange={(e) => vm.setFilters({ groupId: e.target.value })} className="max-md:text-base">
              <option value="">{t("composer.allGroups")}</option>
              {vm.groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </Select>
            <Select aria-label={t("composer.os")} value={vm.filters.os} onChange={(e) => vm.setFilters({ os: e.target.value })} className="max-md:text-base">
              <option value="">{t("composer.allOs")}</option>
              <option value="windows">Windows</option>
              <option value="linux">Linux</option>
              <option value="macos">macOS</option>
            </Select>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={vm.filters.onlyReady} onChange={(e) => vm.setFilters({ onlyReady: e.target.checked })} />
              {t("composer.onlyReady")}
            </label>
            <button type="button" onClick={vm.selectAllVisible} className="cursor-pointer text-primary hover:underline">{t("composer.selectVisible")}</button>
            <button type="button" onClick={vm.clearSelection} className="cursor-pointer text-muted-foreground hover:underline">{t("composer.clear")}</button>
          </div>
        </CardHeader>
        <CardContent>
          <ul className="max-h-[50vh] divide-y divide-border overflow-y-auto rounded-md border border-border">
            {vm.visibleMachines.length === 0 && <li className="p-3 text-sm text-muted-foreground">{t("composer.noMachines")}</li>}
            {vm.visibleMachines.map((m) => {
              const entry = vm.entryOf(m.id);
              const label = entry ? t(`status.${statusKey(entry)}`) : undefined;
              const fits = !vm.script || scriptFits(vm.script.platform, m.os_family);
              return (
                <li key={m.id}>
                  <label className={cn("flex cursor-pointer items-center gap-2 px-3 py-2 text-sm", !fits && "opacity-50")}>
                    <input type="checkbox" checked={vm.selected.has(m.id)} onChange={() => vm.toggleMachine(m.id)} />
                    <span className={cn("h-2 w-2 shrink-0 rounded-full", entry?.readiness === "busy" ? "bg-sky-500" : STATUS_DOT[entry?.status ?? "unknown"])} title={label} aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{m.name}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {[m.os_family ? t(`os.${m.os_family}`) : null, m.darckware_client_name, m.kind === "server" ? t("composer.server") : null].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    {entry && entry.status !== "complete" && <span className="text-[10px] text-muted-foreground">{entry.readiness === "busy" ? t("readiness.busy") : label}</span>}
                  </label>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t(vm.status === "confirming" || busy || vm.status === "error" ? "composer.review" : "composer.what")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {vm.status === "idle" ? (
            <>
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t("composer.source")}>
                {(["library", "adhoc"] as const).map((mode) => (
                  <Button key={mode} type="button" size="sm" variant={vm.source === mode ? "default" : "outline"} onClick={() => vm.setSource(mode)} className="cursor-pointer" role="radio" aria-checked={vm.source === mode}>
                    {t(`composer.sources.${mode}`)}
                  </Button>
                ))}
              </div>

              {vm.source === "library" ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-[180px_minmax(0,1fr)]">
                    <Select aria-label={t("library.category")} value={vm.categoryFilter} onChange={(e) => vm.setCategoryFilter(e.target.value)} className="max-md:text-base">
                      <option value="">{t("library.allCategories")}</option>
                      {vm.categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                    </Select>
                    <Select aria-label={t("composer.script")} value={vm.script?.id ?? ""} onChange={(e) => vm.selectScript(e.target.value)} className="max-md:text-base">
                      <option value="">{t("composer.pickScript")}</option>
                      {vm.scripts.map((s) => <option key={s.id} value={s.id}>{s.name} · {t(`os.${s.platform}`)}</option>)}
                    </Select>
                  </div>
                  {vm.script && (
                    <div className="space-y-3 rounded-md border border-border p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline">{t(`os.${vm.script.platform}`)}</Badge>
                        <Badge variant={vm.script.risk === "destructive" ? "destructive" : vm.script.risk === "change" ? "warning" : "secondary"}>{t(`library.risks.${vm.script.risk}`)}</Badge>
                        <span className="text-xs text-muted-foreground">v{vm.script.current_version}</span>
                      </div>
                      {vm.script.description && <p className="text-sm text-muted-foreground">{vm.script.description}</p>}
                      {vm.selected.size > 0 && (
                        <p className={cn("text-xs", vm.fitCount < vm.selected.size ? "text-amber-600" : "text-muted-foreground")}>
                          {t("composer.fits", { fit: vm.fitCount, total: vm.selected.size })}
                        </p>
                      )}
                      {/* Fixed infrastructure (e.g. the RustDesk server) is read from
                          ForgeVault when the script runs: never typed, never shown. */}
                      {Object.entries(
                        vm.script.parameters.reduce<Record<string, string[]>>((acc, p) => {
                          if (p.vault_secret) (acc[p.vault_secret] ??= []).push(p.label || p.name);
                          return acc;
                        }, {}),
                      ).map(([secret, labels]) => (
                        <p key={secret} className="flex items-start gap-2 rounded-md border bg-muted/40 p-2 text-xs text-muted-foreground">
                          <KeyRound className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                          <span>{t("composer.fromVault", { fields: labels.join(", "), secret })}</span>
                        </p>
                      ))}
                      {vm.script.parameters.filter((p) => !p.vault_secret).map((p) => (
                        <div key={p.name} className="space-y-1">
                          <Label htmlFor={`param-${p.name}`}>{p.label || p.name}{p.required && " *"}</Label>
                          {p.options?.length ? (
                            <Select
                              id={`param-${p.name}`}
                              value={vm.paramValues[p.name] ?? p.default ?? ""}
                              onChange={(e) => vm.setParam(p.name, e.target.value)}
                              className="max-md:text-base"
                            >
                              {!p.default && <option value="">{t("composer.optionNone")}</option>}
                              {p.options.map((o) => (
                                <option key={o} value={o}>{t(`composer.options.${o}`, { defaultValue: o })}</option>
                              ))}
                            </Select>
                          ) : (
                            <>
                              <Input
                                id={`param-${p.name}`}
                                type={p.secret ? "password" : "text"}
                                autoComplete="off"
                                value={vm.paramValues[p.name] ?? ""}
                                onChange={(e) => vm.setParam(p.name, e.target.value)}
                                className="max-md:text-base"
                              />
                              {/* The default isn't echoed as a placeholder: it showed
                                  infrastructure values (servers, keys) on screen.
                                  It still applies when the field is left blank. */}
                              {p.default && <p className="text-xs text-muted-foreground">{t("composer.usesDefault")}</p>}
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <Select aria-label={t("run.shell")} value={vm.shell} onChange={(e) => vm.setShell(e.target.value as "sh" | "powershell")} className="max-md:text-base">
                    <option value="powershell">{t("run.shells.powershell")}</option>
                    <option value="sh">{t("run.shells.sh")}</option>
                  </Select>
                  <Textarea aria-label={t("run.command")} value={vm.command} onChange={(e) => vm.setCommand(e.target.value)} className="min-h-[140px] font-mono text-xs max-md:text-base" spellCheck={false} />
                </div>
              )}

              <fieldset className="space-y-3">
                <legend className="text-sm font-medium">{t("composer.when")}</legend>
                <div className="flex flex-wrap gap-2">
                  {(["now", "once", "weekly"] as WhenMode[]).map((mode) => (
                    <Button key={mode} type="button" size="sm" variant={vm.when === mode ? "default" : "outline"} onClick={() => vm.setWhen(mode)} className="cursor-pointer" aria-pressed={vm.when === mode}>
                      {t(`composer.whenModes.${mode}`)}
                    </Button>
                  ))}
                </div>
                {vm.when !== "now" && (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="space-y-1 sm:col-span-2">
                      <Label htmlFor="sched-name">{t("composer.scheduleName")}</Label>
                      <Input id="sched-name" value={vm.scheduleName} onChange={(e) => vm.setScheduleName(e.target.value)} className="max-md:text-base" />
                    </div>
                    {vm.when === "once" ? (
                      <div className="space-y-1">
                        <Label htmlFor="sched-at">{t("composer.runAt")}</Label>
                        <Input id="sched-at" type="datetime-local" value={vm.runAt} onChange={(e) => vm.setRunAt(e.target.value)} className="max-md:text-base" />
                      </div>
                    ) : (
                      <>
                        <div className="space-y-1 sm:col-span-2">
                          <span className="text-sm font-medium">{t("composer.weekdays")}</span>
                          <div className="flex flex-wrap gap-1.5">
                            {WEEKDAYS.map((d) => (
                              <button key={d} type="button" onClick={() => vm.toggleWeekday(d)} aria-pressed={vm.weekdays.has(d)}
                                className={cn("cursor-pointer rounded-md border px-2.5 py-1 text-xs", vm.weekdays.has(d) ? "border-primary bg-primary text-primary-foreground" : "border-border")}>
                                {t(`composer.days.${d}`)}
                              </button>
                            ))}
                          </div>
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="sched-time">{t("composer.time")}</Label>
                          <Input id="sched-time" type="time" value={vm.timeOfDay} onChange={(e) => vm.setTimeOfDay(e.target.value)} className="max-md:text-base" />
                        </div>
                      </>
                    )}
                    <div className="space-y-1">
                      <Label htmlFor="sched-window">{t("composer.window")}</Label>
                      <Input id="sched-window" type="number" min={5} max={1440} value={vm.windowMinutes} onChange={(e) => vm.setWindowMinutes(Number(e.target.value) || 120)} className="max-md:text-base" />
                    </div>
                    <p className="text-xs text-muted-foreground sm:col-span-2">{t("composer.windowHelp")}</p>
                  </div>
                )}
              </fieldset>

              {vm.noAccessMachines.length > 0 && vm.when === "now" && (
                <fieldset className="space-y-2 rounded-md border border-orange-500/40 bg-orange-500/5 p-3">
                  <legend className="px-1 text-sm font-medium">{t("composer.login.title")}</legend>
                  <p className="text-xs text-muted-foreground">
                    {t("composer.login.help", { count: vm.noAccessMachines.length, names: vm.noAccessMachines.map((m) => m.name).join(", ") })}
                  </p>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <Label htmlFor="run-login">{t("composer.login.user")}</Label>
                      <Input id="run-login" autoComplete="off" value={vm.loginUser} onChange={(e) => vm.setLoginUser(e.target.value)} className="max-md:text-base" />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="run-password">{t("composer.login.password")}</Label>
                      <Input id="run-password" type="password" autoComplete="off" value={vm.loginPassword} onChange={(e) => vm.setLoginPassword(e.target.value)} className="max-md:text-base" />
                    </div>
                  </div>
                </fieldset>
              )}
              {vm.problems.length > 0 && (vm.selected.size > 0 || vm.script || vm.command) && (
                <ul className="space-y-1 text-xs text-amber-600">
                  {[...new Set(vm.problems)].map((p) => (
                    <li key={p} className="flex items-center gap-1.5"><TriangleAlert className="h-3 w-3" aria-hidden="true" /> {t(`composer.problems.${p}`)}</li>
                  ))}
                </ul>
              )}
              {vm.rendered && (
                <div className="space-y-2 rounded-md border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">{t("composer.copyTitle")}</p>
                    <div className="flex gap-1">
                      <Button type="button" size="sm" variant="outline" className="cursor-pointer gap-1.5" onClick={() => {
                        void navigator.clipboard.writeText(vm.rendered!.script);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 1500);
                      }}>
                        {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
                        {t(copied ? "prepare.copied" : "prepare.copy")}
                      </Button>
                      <Button type="button" size="icon" variant="ghost" onClick={vm.closeRendered} aria-label={t("prepare.close")} className="cursor-pointer">
                        <X className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">{t(vm.rendered.shell === "powershell" ? "prepare.step2Windows" : "enroll.step2Linux")}</p>
                  <pre className="max-h-64 overflow-auto whitespace-pre rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">{vm.rendered.script}</pre>
                </div>
              )}
              {vm.renderError && <p role="alert" className="text-xs text-destructive">{vm.renderError}</p>}
              <div className="flex flex-wrap justify-end gap-2">
                {vm.source === "library" && vm.script && (
                  <Button type="button" variant="outline" onClick={vm.renderForCopy} disabled={vm.rendering} className="cursor-pointer gap-1.5" title={t("composer.copyHelp")}>
                    {vm.rendering ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : <ClipboardCopy className="h-4 w-4" aria-hidden="true" />}
                    {t("composer.copyScript")}
                  </Button>
                )}
                <Button type="button" onClick={vm.review} disabled={vm.problems.length > 0} className="cursor-pointer">{t("run.review")}</Button>
              </div>
            </>
          ) : (
            <div className="space-y-3">
              <p className="text-sm">
                {vm.when === "now"
                  ? t("composer.confirmNow", { count: vm.source === "library" ? vm.fitCount : vm.selected.size })
                  : vm.when === "once"
                    ? t("composer.confirmOnce", { at: vm.runAt.replace("T", " ") })
                    : t("composer.confirmWeekly", { days: [...vm.weekdays].sort().map((d) => t(`composer.days.${d}`)).join(", "), time: vm.timeOfDay })}
              </p>
              <p className="text-sm font-medium">{vm.source === "library" ? `${vm.script?.name} (v${vm.script?.current_version})` : t("composer.sources.adhoc")}</p>
              <p className="text-xs text-muted-foreground">{vm.selectedMachines.map((m) => m.name).join(", ")}</p>
              {vm.source === "adhoc" && <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">{vm.command}</pre>}
              {vm.script?.risk === "destructive" && (
                <p className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs">
                  <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" /> {t("composer.destructive")}
                </p>
              )}
              {vm.error && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" variant="outline" onClick={vm.back} disabled={busy} className="cursor-pointer">{t("run.back")}</Button>
                <Button type="button" onClick={vm.submit} disabled={busy} className="cursor-pointer gap-1.5">
                  {busy ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : vm.when === "now" ? <Play className="h-4 w-4" aria-hidden="true" /> : <CalendarClock className="h-4 w-4" aria-hidden="true" />}
                  {t(vm.when === "now" ? "composer.runNow" : "composer.schedule")}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
