/** "Pedir ao agente" (Remote Access): a maintenance task for one or more
 * authorized agents on the chosen machines -- free text, optionally the
 * library scripts to use, and the client's ticket/demand. An agent qualifies
 * with library scripts or with free commands covering every machine; chosen
 * scripts need a script permission covering their risk (2026-11-11). One Messages task
 * per agent; what each runs lands in the machine's history. Right-hand panel
 * (2026-11-11). State:
 * useAgentRequestViewModel. */
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Bot, Check, Loader2, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { SidePanel } from "@/components/ui/side-panel";
import { Textarea } from "@/components/ui/textarea";
import { useAgentRequestViewModel } from "@/hooks/useAgentRequestViewModel";
import type { Server } from "@/hooks/useServers";

export function AgentRequestDialog({ machines, onClose }: { machines: Server[]; onClose: () => void }) {
  const { t } = useTranslation("remoteAccess");
  const vm = useAgentRequestViewModel(machines);
  const busy = vm.status === "submitting";

  return (
    <SidePanel
      onClose={onClose}
      busy={busy}
      size="2xl"
      titleId="ask-agent-title"
      icon={<Bot className="h-4 w-4" aria-hidden="true" />}
      title={t("askAgent.title")}
      closeLabel={t("cancel")}
      footer={
        <>
          <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={busy} className="cursor-pointer">{t(vm.result ? "prepare.close" : "cancel")}</Button>
          {!vm.result && (
            <Button type="button" size="sm" onClick={vm.submit} disabled={!vm.canSubmit} className="cursor-pointer gap-1.5">
              {busy ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              {t("askAgent.send", { count: vm.chosenAgents.size || 1 })}
            </Button>
          )}
        </>
      }
    >
      {vm.result ? (
        <div className="space-y-3 text-sm">
          <p className="flex items-center gap-2 font-medium"><Check className="h-4 w-4 text-emerald-600" aria-hidden="true" /> {t("askAgent.sent", { count: vm.result.length })}</p>
          <ul className="space-y-1">
            {vm.result.map((r) => (
              <li key={r.demand_id}>{r.agent_name}: <Link to="/demands" className="underline">{t("askAgent.message", { number: r.demand_number ?? "" })}</Link></li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">{t("askAgent.sentHelp")}</p>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm">
            <span className="text-muted-foreground">{t("askAgent.machines")}: </span>
            <span className="font-medium">{vm.machines.map((m) => m.name).join(", ")}</span>
          </p>

          <div className="space-y-1">
            <Label htmlFor="ask-instruction">{t("askAgent.instruction")}</Label>
            <Textarea id="ask-instruction" value={vm.instruction} onChange={(e) => vm.setInstruction(e.target.value)}
              placeholder={t("askAgent.instructionPlaceholder")} className="min-h-[100px] max-md:text-base" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ask-add-script">{t("askAgent.scripts")}</Label>
            <p className="text-xs text-muted-foreground">{t("askAgent.scriptsHelp")}</p>
            <Select id="ask-add-script" value="" onChange={(e) => vm.addScript(e.target.value)} className="max-md:text-base">
              <option value="">{t("askAgent.addScript")}</option>
              {vm.scriptGroups.map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.scripts.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </optgroup>
              ))}
            </Select>
            {vm.scripts.map(({ script, values }) => (
              <div key={script.id} className="space-y-2 rounded-md border border-border p-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{script.name}</span>
                  <Badge variant={script.risk === "destructive" ? "destructive" : script.risk === "change" ? "warning" : "secondary"}>{t(`library.risks.${script.risk}`)}</Badge>
                  <Button type="button" size="icon" variant="ghost" onClick={() => vm.removeScript(script.id)} aria-label={t("askAgent.removeScript", { name: script.name })} className="ml-auto h-7 w-7 cursor-pointer">
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  </Button>
                </div>
                {script.parameters.filter((p) => !p.vault_secret).map((p) => (
                  <div key={p.name} className="space-y-1">
                    <Label htmlFor={`ask-${script.id}-${p.name}`} className="text-xs">{p.label || p.name}{p.required && !p.default && !p.secret && " *"}</Label>
                    {p.secret ? (
                      <p className="text-xs text-muted-foreground">{t("askAgent.secretParam")}</p>
                    ) : p.options?.length ? (
                      <Select id={`ask-${script.id}-${p.name}`} value={values[p.name] ?? p.default ?? ""} onChange={(e) => vm.setScriptValue(script.id, p.name, e.target.value)} className="max-md:text-base">
                        {!p.default && <option value="">{t("composer.optionNone")}</option>}
                        {p.options.map((o) => <option key={o} value={o}>{t(`composer.options.${o}`, { defaultValue: o })}</option>)}
                      </Select>
                    ) : (
                      <Input id={`ask-${script.id}-${p.name}`} value={values[p.name] ?? ""} onChange={(e) => vm.setScriptValue(script.id, p.name, e.target.value)} className="max-md:text-base" />
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>

          {vm.clientItems.length > 0 && (
            <div className="space-y-1">
              <Label htmlFor="ask-item">{t("composer.record.item")}</Label>
              <Select id="ask-item" value={vm.itemKey} onChange={(e) => vm.setItemKey(e.target.value)} className="max-md:text-base">
                <option value="">{t("composer.record.itemNone")}</option>
                {vm.clientItems.map((i) => (
                  <option key={`${i.kind}:${i.id}`} value={`${i.kind}:${i.id}`}>{t(`maintenance.item.${i.kind}`, { id: i.id })} · {i.title}</option>
                ))}
              </Select>
            </div>
          )}

          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">{t("askAgent.agents")}</legend>
            {vm.candidates.length === 0 && <p className="text-xs text-amber-600">{t("askAgent.noAgents")}</p>}
            {vm.candidates.map((c) => {
              const ok = c.block === null;
              const can = [
                c.scriptsCeiling ? t("askAgent.canScripts", { level: t(`authz.risk.${c.scriptsCeiling}`, { defaultValue: c.scriptsCeiling }) }) : null,
                c.commands ? t("askAgent.canCommands") : null,
              ].filter(Boolean).join(" · ");
              const reasonId = `ask-agent-block-${c.id}`;
              return (
                <div key={c.id} className={ok ? undefined : "opacity-60"}>
                  <label className={`flex flex-wrap items-center gap-x-2 text-sm ${ok ? "cursor-pointer" : "cursor-not-allowed"}`}>
                    <input type="checkbox" disabled={!ok} checked={ok && vm.chosenAgents.has(c.id)} onChange={() => vm.toggleAgent(c.id)}
                      aria-describedby={ok ? undefined : reasonId} />
                    {c.name}
                    {can && <span className="text-xs text-muted-foreground">({can})</span>}
                  </label>
                  {!ok && <p id={reasonId} className="pl-6 text-xs text-muted-foreground">{t(`askAgent.block.${c.block}`)}</p>}
                </div>
              );
            })}
            <p className="text-xs text-muted-foreground">{t("askAgent.agentsHelp")}</p>
          </fieldset>
          {vm.error && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
        </div>
      )}
    </SidePanel>
  );
}
