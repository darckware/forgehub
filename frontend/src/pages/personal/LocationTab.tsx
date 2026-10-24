import { useTranslation } from "react-i18next";
import { Loader2, MapPin, Pencil, Plus, Save } from "lucide-react";
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

const fieldClass = "max-md:text-base";

/** Where Marcelo was each day -- sent by the Maia or set here -- which the summary's weather uses. */
export function LocationTab() {
  const { t, i18n } = useTranslation("personal");
  const vm = usePersonalLocationViewModel();
  const draft = vm.editing;

  return (
    <div className="flex flex-col gap-4 pt-4">
      <Card>
        <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-lg">{t("location.title")}</CardTitle>
            <CardDescription>{t("location.description")}</CardDescription>
          </div>
          {!draft && (
            <Button size="sm" onClick={() => vm.open()}>
              <Plus className="mr-1 h-4 w-4" />{t("location.add")}
            </Button>
          )}
        </CardHeader>
        {draft && (
          <CardContent>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void vm.save(); }}>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="space-y-1">
                  <Label htmlFor="location-day">{t("fields.date")}</Label>
                  <Input id="location-day" type="date" className={fieldClass} value={draft.day}
                    onChange={(e) => vm.change({ day: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="location-city">{t("location.city")}</Label>
                  <Input id="location-city" maxLength={120} className={fieldClass} value={draft.city}
                    onChange={(e) => vm.change({ city: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="location-state">{t("location.state")}</Label>
                  <Input id="location-state" maxLength={80} className={fieldClass} value={draft.state}
                    onChange={(e) => vm.change({ state: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="location-lat">{t("location.latitude")}</Label>
                  <Input id="location-lat" inputMode="decimal" className={fieldClass} value={draft.latitude}
                    onChange={(e) => vm.change({ latitude: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="location-lon">{t("location.longitude")}</Label>
                  <Input id="location-lon" inputMode="decimal" className={fieldClass} value={draft.longitude}
                    onChange={(e) => vm.change({ longitude: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="location-notes">{t("location.notes")}</Label>
                  <Input id="location-notes" className={fieldClass} value={draft.notes}
                    onChange={(e) => vm.change({ notes: e.target.value })} />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">{t("location.replaceHint")}</p>
              {vm.error && <p className="text-sm text-destructive">{vm.error}</p>}
              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={!vm.valid || vm.status === "submitting"}>
                  {vm.status === "submitting" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                  {t("actions.save")}
                </Button>
                <Button type="button" variant="outline" onClick={vm.cancel}>{t("actions.cancel")}</Button>
              </div>
            </form>
          </CardContent>
        )}
      </Card>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="location-from">{t("location.from")}</Label>
          <Input id="location-from" type="date" className={`w-44 ${fieldClass}`} value={vm.start}
            onChange={(e) => vm.setStart(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="location-to">{t("location.to")}</Label>
          <Input id="location-to" type="date" className={`w-44 ${fieldClass}`} value={vm.end}
            onChange={(e) => vm.setEnd(e.target.value)} />
        </div>
      </div>

      {vm.query.isLoading && <Loader2 className="h-5 w-5 animate-spin" />}
      {vm.query.isError && <p className="text-sm text-destructive">{String(vm.query.error)}</p>}
      {!vm.query.isLoading && !vm.query.isError && vm.locations.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("location.empty")}</p>
      )}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {vm.locations.map((loc) => (
          <Card key={loc.id}>
            <CardContent className="flex items-start gap-3 p-4">
              <MapPin className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{loc.state ? `${loc.city} (${loc.state})` : loc.city}</p>
                <p className="text-sm text-muted-foreground">{formatDay(loc.day, i18n.language)}</p>
                <p className="text-xs text-muted-foreground">{loc.latitude.toFixed(4)}, {loc.longitude.toFixed(4)}</p>
                {loc.notes && <p className="mt-1 break-words text-xs">{loc.notes}</p>}
                <Badge variant="outline" className="mt-2 text-xs">{t(`location.source.${loc.source}`)}</Badge>
              </div>
              <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t("location.edit")} onClick={() => vm.open(loc)}>
                <Pencil className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
