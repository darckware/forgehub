import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, ChevronDown, ChevronRight, FileText, History, Loader2, RefreshCw, Save } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePhoneListDetail } from "@/hooks/useIsPhone";
import { serviceRuleKey, type ServiceRule, type ServiceRuleFileState } from "@/hooks/useServiceRules";
import { useServiceRulesViewModel } from "@/hooks/useServiceRulesViewModel";
import { cn } from "@/lib/utils";

function when(iso: string | null | undefined, locale: string): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
}

const BADGE_VARIANT: Record<ServiceRuleFileState, "success" | "warning" | "outline"> = {
  in_sync: "success",
  differs: "warning",
  missing: "warning",
  unknown: "outline",
};

function FileStateBadge({ state }: { state: ServiceRuleFileState }) {
  const { t } = useTranslation("personal");
  return <Badge variant={BADGE_VARIANT[state]}>{t(`serviceRules.fileState.${state}`)}</Badge>;
}

/**
 * Pessoal -> "Regras de atendimento" (2026-11-14, Marcelo): the customer-service rules of the
 * agents that talk to people outside the ecosystem, one document per agent + channel. ForgeHub
 * stores them and mirrors each into the agent's `ATENDIMENTO_<CANAL>.md`; the badge says whether
 * that file still matches.
 */
export function ServiceRulesTab() {
  const { t, i18n } = useTranslation("personal");
  const vm = useServiceRulesViewModel();
  const phone = usePhoneListDetail(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const rule = vm.selected;

  const pairLabel = (r: Pick<ServiceRule, "agent" | "channel">) =>
    `${t(`serviceRules.agents.${r.agent}`)} · ${t(`serviceRules.channels.${r.channel}`)}`;

  function pick(key: string) {
    const asksFirst = key !== vm.selectedKey && vm.dirty; // the dialog's confirm opens the detail
    vm.select(key);
    if (!asksFirst) phone.openDetail();
  }

  if (vm.status === "loading") {
    return <div className="pt-4"><Loader2 className="mx-auto h-5 w-5 animate-spin" /></div>;
  }
  if (vm.loadError) {
    return <p className="pt-4 text-sm text-destructive">{t("serviceRules.loadError")} {vm.loadError}</p>;
  }
  if (vm.rules.length === 0) {
    return <p className="pt-4 text-sm text-muted-foreground">{t("serviceRules.empty")}</p>;
  }

  return (
    <div className="flex flex-col gap-4 pt-4">
      <p className="text-sm text-muted-foreground">{t("serviceRules.description")}</p>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[18rem_minmax(0,1fr)]">
        {phone.showList && (
          <Card className="h-fit">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{t("serviceRules.pairs")}</CardTitle>
            </CardHeader>
            <CardContent className="p-2 pt-0">
              <ul className="flex flex-col gap-1" aria-label={t("serviceRules.pairs")}>
                {vm.rules.map((r) => {
                  const key = serviceRuleKey(r);
                  const active = key === vm.selectedKey;
                  return (
                    <li key={key}>
                      <button
                        type="button"
                        aria-current={active ? "true" : undefined}
                        onClick={() => pick(key)}
                        className={cn(
                          "flex w-full flex-col gap-1 rounded-md border px-3 py-2 text-left text-sm transition-colors hover:bg-muted",
                          active ? "border-primary bg-muted" : "border-transparent",
                        )}
                      >
                        <span className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium">{pairLabel(r)}</span>
                          <FileStateBadge state={r.file_state} />
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {r.updated_at
                            ? r.updated_by
                              ? t("serviceRules.updatedBy", { when: when(r.updated_at, i18n.language), who: r.updated_by })
                              : t("serviceRules.updated", { when: when(r.updated_at, i18n.language) })
                            : t("serviceRules.neverUpdated")}
                        </span>
                        {active && vm.dirty && (
                          <span className="text-xs text-amber-600">{t("serviceRules.unsaved")}</span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>
        )}

        {phone.showDetail && rule && (
          <Card className="min-w-0">
            {phone.isPhone && (
              <div className="border-b p-2 md:hidden">
                <Button size="sm" variant="ghost" onClick={phone.backToList}>
                  <ArrowLeft className="mr-1 h-4 w-4" />{t("serviceRules.back")}
                </Button>
              </div>
            )}
            <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 space-y-1">
                <CardTitle className="text-lg">
                  {t("serviceRules.editor", {
                    agent: t(`serviceRules.agents.${rule.agent}`),
                    channel: t(`serviceRules.channels.${rule.channel}`),
                  })}
                </CardTitle>
                <CardDescription className="flex items-start gap-1 break-all">
                  <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <span>
                    {t("serviceRules.filePath")}: <code className="text-xs" data-testid="service-rule-file-path">{rule.file_path}</code>
                  </span>
                </CardDescription>
              </div>
              <FileStateBadge state={rule.file_state} />
            </CardHeader>
            <CardContent className="space-y-3">
              {rule.file_state !== "in_sync" && (
                <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                  {t(`serviceRules.fileStateHelp.${rule.file_state}`)}
                </p>
              )}
              <form
                className="space-y-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void vm.save();
                }}
              >
                <Label htmlFor="service-rule-text" className="sr-only">
                  {pairLabel(rule)}
                </Label>
                <Textarea
                  id="service-rule-text"
                  rows={20}
                  spellCheck={false}
                  className="font-mono text-xs max-md:text-base"
                  value={vm.text}
                  onChange={(e) => vm.change(e.target.value)}
                  aria-invalid={vm.overLimit || undefined}
                />
                <p className={cn("text-xs", vm.overLimit ? "font-medium text-destructive" : "text-muted-foreground")}>
                  {t("serviceRules.chars", { count: vm.chars, max: vm.maxChars })}
                  {vm.overLimit && <> — {t("serviceRules.overLimit", { max: vm.maxChars })}</>}
                </p>
                {vm.dirty && vm.empty && <p className="text-xs text-destructive">{t("serviceRules.emptyText")}</p>}
                {vm.status === "error" && vm.error && <p className="text-sm text-destructive">{vm.error}</p>}
                {vm.status === "conflict" && (
                  <div className="flex flex-col gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-100 sm:flex-row sm:items-center sm:justify-between">
                    <span>{t("serviceRules.conflict")}</span>
                    <Button type="button" size="sm" variant="outline" onClick={() => void vm.reload()}>
                      <RefreshCw className="mr-1 h-4 w-4" />{t("serviceRules.reload")}
                    </Button>
                  </div>
                )}
                {vm.saved && <p className="text-sm text-emerald-600">{t("serviceRules.saved")}</p>}
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="submit" disabled={!vm.canSave}>
                    {vm.status === "saving" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                    {t("actions.save")}
                  </Button>
                  {vm.dirty && (
                    <Button type="button" variant="outline" onClick={vm.discard} disabled={vm.status === "saving"}>
                      {t("actions.cancel")}
                    </Button>
                  )}
                  {rule.updated_at && (
                    <span className="text-xs text-muted-foreground">
                      {rule.updated_by
                        ? t("serviceRules.updatedBy", { when: when(rule.updated_at, i18n.language), who: rule.updated_by })
                        : t("serviceRules.updated", { when: when(rule.updated_at, i18n.language) })}
                    </span>
                  )}
                </div>
              </form>

              <div className="border-t pt-3">
                <button
                  type="button"
                  className="flex items-center gap-1 text-sm font-medium"
                  aria-expanded={historyOpen}
                  onClick={() => setHistoryOpen((o) => !o)}
                >
                  {historyOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  <History className="h-4 w-4" />
                  {t("serviceRules.history")}
                </button>
                {historyOpen && (
                  <div className="mt-2">
                    {vm.historyLoading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : vm.historyError ? (
                      <p className="text-sm text-destructive">{t("serviceRules.historyError")}</p>
                    ) : vm.history.length === 0 ? (
                      <p className="text-sm text-muted-foreground">{t("serviceRules.historyEmpty")}</p>
                    ) : (
                      <ul className="divide-y text-sm">
                        {vm.history.map((h) => (
                          <li key={`${h.at}-${h.content_hash}`} className="flex flex-wrap justify-between gap-2 py-1.5">
                            <span>{when(h.at, i18n.language)} · {h.actor}</span>
                            <span className="text-muted-foreground">{t("serviceRules.historyEntry", { chars: h.chars })}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(vm.pendingKey)}
        variant="default"
        icon="warning"
        title={t("serviceRules.switch.title")}
        description={t("serviceRules.switch.description", { pair: rule ? pairLabel(rule) : "" })}
        confirmLabel={t("serviceRules.switch.confirm")}
        onConfirm={() => {
          vm.confirmSwitch();
          phone.openDetail();
        }}
        onCancel={vm.cancelSwitch}
      />
    </div>
  );
}
