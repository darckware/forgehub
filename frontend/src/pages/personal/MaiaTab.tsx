import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Loader2, PauseCircle, Save, ScrollText, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMaiaSettingsViewModel } from "@/hooks/usePersonalContactsViewModel";

function when(iso: string | null | undefined, locale: string): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
}

/** The Maia's WhatsApp service: its settings (wait, capture) and what she is doing now. The rules text
 * she reads lives in the Regras de atendimento tab (`onOpenServiceRules` switches to it). */
export function MaiaTab({ onOpenServiceRules }: { onOpenServiceRules?: () => void } = {}) {
  const { t, i18n } = useTranslation("personal");
  const vm = useMaiaSettingsViewModel();
  const s = vm.state;

  return (
    <div className="grid grid-cols-1 gap-4 pt-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{t("maia.rules.settingsTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* The instructions text moved to the Regras de atendimento tab (2026-11-14), one document
              per agent + channel; this card keeps only the WhatsApp service's own settings. */}
          <div className="flex flex-col gap-2 rounded-md border bg-muted/40 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <span className="flex items-start gap-1.5">
              <ScrollText className="mt-0.5 h-4 w-4 shrink-0" />
              {t("maia.rules.movedNote")}
            </span>
            {onOpenServiceRules ? (
              <Button type="button" size="sm" variant="outline" className="max-md:h-auto max-md:whitespace-normal" onClick={onOpenServiceRules}>
                {t("maia.rules.openServiceRules")}
              </Button>
            ) : (
              <Link to="/personal?tab=service-rules" className="text-primary underline-offset-4 hover:underline">
                {t("maia.rules.openServiceRules")}
              </Link>
            )}
          </div>
          {vm.loading || !vm.form ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void vm.save(); }}>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="maia-wait">{t("maia.rules.wait")}</Label>
                  <Input id="maia-wait" type="number" min={0} max={240} className="w-32 max-md:text-base"
                    value={vm.form.wait_minutes} onChange={(e) => vm.change({ wait_minutes: e.target.value })} />
                  <p className="text-xs text-muted-foreground">{t("maia.rules.waitHelp")}</p>
                  {vm.minutesError && <p className="text-xs text-destructive">{t("maia.rules.waitInvalid")}</p>}
                </div>
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" className="mt-0.5 h-4 w-4" checked={vm.form.capture_enabled}
                    onChange={(e) => vm.change({ capture_enabled: e.target.checked })} />
                  <span>
                    {t("maia.rules.capture")}
                    <span className="block text-xs text-muted-foreground">{t("maia.rules.captureHelp")}</span>
                  </span>
                </label>
              </div>
              {vm.error && <p className="text-sm text-destructive">{vm.error}</p>}
              {vm.saved && <p className="text-sm text-emerald-600">{t("maia.rules.saved")}</p>}
              <div className="flex flex-wrap items-center gap-2">
                <Button type="submit" disabled={!vm.dirty || vm.submitting || Boolean(vm.minutesError)}>
                  {vm.submitting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                  {t("actions.save")}
                </Button>
                {vm.dirty && <Button type="button" variant="outline" onClick={vm.discard}>{t("actions.cancel")}</Button>}
                {vm.updatedAt && (
                  <span className="text-xs text-muted-foreground">{t("maia.rules.updatedAt", { when: when(vm.updatedAt, i18n.language) })}</span>
                )}
              </div>
            </form>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{t("maia.now.title")}</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 text-sm">
            <Stat label={t("maia.now.contacts")} value={s?.contacts} />
            <Stat label={t("maia.now.blocked")} value={s?.blocked} />
            <Stat label={t("maia.now.suggestions")} value={s?.suggestions_pending} highlight={Boolean(s?.suggestions_pending)} />
            <Stat label={t("maia.now.contextPending")} value={s?.context_pending} />
            {Boolean(s?.context_failed) && <Stat label={t("maia.now.contextFailed")} value={s?.context_failed} highlight />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5 text-lg"><PauseCircle className="h-4 w-4" />{t("maia.paused.title")}</CardTitle>
            <CardDescription>{t("maia.paused.description")}</CardDescription>
          </CardHeader>
          <CardContent>
            {!s?.paused.length ? <p className="text-sm text-muted-foreground">{t("maia.paused.empty")}</p> : (
              <ul className="divide-y text-sm">
                {s.paused.map((p) => (
                  <li key={p.phone} className="flex flex-wrap justify-between gap-2 py-2">
                    <span>{p.name || p.phone}</span>
                    <span className="text-muted-foreground">{t("maia.paused.until", { when: when(p.until, i18n.language) })}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5 text-lg"><Target className="h-4 w-4" />{t("maia.tasks.title")}</CardTitle>
            <CardDescription>{t("maia.tasks.description")}</CardDescription>
          </CardHeader>
          <CardContent>
            {!s?.open_tasks.length ? <p className="text-sm text-muted-foreground">{t("maia.tasks.empty")}</p> : (
              <ul className="divide-y text-sm">
                {s.open_tasks.map((task) => (
                  <li key={task.phone} className="space-y-0.5 py-2">
                    <p className="font-medium">{task.name || task.phone}</p>
                    <p className="break-words">{task.goal}</p>
                    {task.expires_at && (
                      <p className="text-xs text-muted-foreground">{t("maia.tasks.expires", { when: when(task.expires_at, i18n.language) })}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Stat({ label, value, highlight }: { label: string; value: number | undefined; highlight?: boolean }) {
  return (
    <div className="rounded-md border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={highlight ? "text-xl font-semibold text-amber-600" : "text-xl font-semibold"}>{value ?? "—"}</p>
    </div>
  );
}
