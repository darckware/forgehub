import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, Loader2, LocateFixed, MapPin, Sunrise } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePersonalLocationViewModel } from "@/hooks/usePersonalViewModel";

function formatDay(day: string, locale: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" })
    .format(new Date(Date.UTC(y, m - 1, d)));
}

function formatMoment(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" })
    .format(new Date(iso));
}

function placeName(city: string | null, state: string | null): string | null {
  if (city && state) return `${city} (${state})`;
  return city || state;
}

const fieldClass = "max-md:text-base";

/** Marcelo's current GPS location (the summary's weather uses it) and the Maia's daily summaries. */
export function LocationTab() {
  const { t, i18n } = useTranslation("personal");
  const vm = usePersonalLocationViewModel();
  const current = vm.current;
  const busy = vm.status === "locating" || vm.status === "submitting";

  return (
    <div className="flex flex-col gap-4 pt-4">
      <Card>
        <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-lg">{t("location.title")}</CardTitle>
            <CardDescription>{t("location.description")}</CardDescription>
          </div>
          <Button size="sm" onClick={() => void vm.shareMyLocation()} disabled={busy}
            className="max-md:h-auto max-md:whitespace-normal max-md:py-2">
            {busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <LocateFixed className="mr-1 h-4 w-4" />}
            {vm.status === "locating" ? t("location.locating") : t("location.useMine")}
          </Button>
        </CardHeader>
        <CardContent className="space-y-2">
          {vm.location.isLoading && <Loader2 className="h-5 w-5 animate-spin" />}
          {vm.location.isError && <p className="text-sm text-destructive">{String(vm.location.error)}</p>}
          {!vm.location.isLoading && !vm.location.isError && !current && (
            <p className="text-sm text-muted-foreground">{t("location.none")}</p>
          )}
          {current && (
            <div className="flex items-start gap-3">
              <MapPin className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 space-y-0.5">
                <p className="font-medium">{placeName(current.city, current.state) ?? t("location.unnamed")}</p>
                <p className="text-xs text-muted-foreground">
                  {current.latitude.toFixed(5)}, {current.longitude.toFixed(5)}
                  {current.accuracy_m !== null && ` · ${t("location.accuracy", { meters: Math.round(current.accuracy_m) })}`}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t("location.sharedAt", { when: formatMoment(current.shared_at, i18n.language) })}
                </p>
                <Badge variant="outline" className="text-xs">{t(`location.source.${current.source}`)}</Badge>
              </div>
            </div>
          )}
          {vm.error && (
            <p className="text-sm text-destructive">
              {"gps" in vm.error ? t(`location.gpsError.${vm.error.gps}`) : vm.error.message}
            </p>
          )}
          <p className="text-xs text-muted-foreground">{t("location.pinHint")}</p>
        </CardContent>
      </Card>

      <div className="space-y-1">
        <h2 className="text-lg font-semibold">{t("dailySummary.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("dailySummary.description")}</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="summary-from">{t("dailySummary.from")}</Label>
          <Input id="summary-from" type="date" className={`w-44 ${fieldClass}`} value={vm.start}
            onChange={(e) => vm.setStart(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="summary-to">{t("dailySummary.to")}</Label>
          <Input id="summary-to" type="date" className={`w-44 ${fieldClass}`} value={vm.end}
            onChange={(e) => vm.setEnd(e.target.value)} />
        </div>
      </div>

      {vm.summaries.isLoading && <Loader2 className="h-5 w-5 animate-spin" />}
      {vm.summaries.isError && <p className="text-sm text-destructive">{String(vm.summaries.error)}</p>}
      {!vm.summaries.isLoading && !vm.summaries.isError && vm.summaryList.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("dailySummary.empty")}</p>
      )}
      <div className="flex flex-col gap-2">
        {vm.summaryList.map((summary) => {
          const open = vm.expanded === summary.id;
          const place = placeName(summary.location_city, summary.location_state);
          return (
            <Card key={summary.id}>
              <CardContent className="space-y-2 p-4">
                <button type="button" className="flex w-full items-start gap-3 text-left" aria-expanded={open}
                  onClick={() => vm.toggle(summary.id)}>
                  <Sunrise className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium capitalize">{formatDay(summary.day, i18n.language)}</p>
                    <p className="text-xs text-muted-foreground">
                      {place
                        ? t("dailySummary.locationUsed", { place })
                        : summary.latitude !== null && summary.longitude !== null
                          ? t("dailySummary.locationUsed", { place: `${summary.latitude.toFixed(4)}, ${summary.longitude.toFixed(4)}` })
                          : t("dailySummary.noLocation")}
                    </p>
                    {!open && <p className="mt-1 line-clamp-2 break-words text-sm text-muted-foreground">{summary.content}</p>}
                  </div>
                  {open ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
                </button>
                {open && <p className="whitespace-pre-wrap break-words text-sm">{summary.content}</p>}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
