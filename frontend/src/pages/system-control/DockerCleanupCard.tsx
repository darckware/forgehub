import { ChevronDown, ChevronRight, Container, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useDockerCleanupViewModel, type DockerPruneAction } from "@/hooks/useDockerCleanupViewModel";
import { cn } from "@/lib/utils";

/** Decimal units, like Docker itself -- the page's formatBytes is binary
 * (1024), which would show `docker system df`'s "92.26GB" as "85.9 GB" and
 * make this card disagree with the CLI an operator cross-checks it against. */
function formatDockerSize(bytes: number | null | undefined, locale: string): string {
  if (bytes == null) return "—";
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

export function DockerCleanupCard() {
  const { t, i18n } = useTranslation("systemControl");
  const vm = useDockerCleanupViewModel();
  const confirm = vm.pendingAction;
  const busy = vm.status === "submitting";
  const disk = vm.usage?.disk;
  const size = (bytes: number | null | undefined) => formatDockerSize(bytes, i18n.language);
  const actionLabel = (action: DockerPruneAction) => t(`docker.actions.${action}.label`);

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Container className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">Docker</h2>
            {vm.usage && (
              <span className="text-xs text-muted-foreground">
                {t("docker.reclaimable", { size: size(vm.totalReclaimable) })}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button size="sm" variant="outline" className="gap-2" onClick={vm.refresh} disabled={vm.refreshing || busy}>
              <RefreshCw className={cn("h-4 w-4", vm.refreshing && "animate-spin")} />
              {t("docker.refresh")}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              className="gap-2"
              onClick={() => vm.requestPrune("all")}
              disabled={!vm.usage || vm.totalReclaimable === 0 || busy}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              {actionLabel("all")}
            </Button>
          </div>
        </div>

        {vm.status === "loading" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> {t("docker.reading")}
          </p>
        )}
        {vm.loadError && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">
            {t("docker.readFailed", { error: vm.loadError })}
          </p>
        )}

        {disk && vm.diskPercent !== null && (
          <div className="space-y-1">
            <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
              <span>
                {t("docker.disk", { used: size(disk.used), total: size(disk.total), percent: vm.diskPercent })}
              </span>
              <span>{t("docker.free", { size: size(disk.available) })}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  vm.diskPercent >= 90 ? "bg-destructive" : vm.diskPercent >= 75 ? "bg-amber-500" : "bg-emerald-500"
                )}
                style={{ width: `${vm.diskPercent}%` }}
              />
            </div>
          </div>
        )}

        {vm.usage && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {vm.usage.types.map((type) => {
              const action: DockerPruneAction | null =
                type.type === "Build Cache" ? "build_cache" : type.type === "Images" ? "unused_images" : null;
              const reclaimable = type.reclaimable;
              return (
                <div key={type.type} className="rounded-md border border-border p-3">
                  <span className="flex items-center justify-between gap-1">
                    <span className="text-xs font-medium uppercase text-muted-foreground">{t(`docker.types.${type.type}`, { defaultValue: type.type })}</span>
                    {action && (
                      <button
                        type="button"
                        className="rounded p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        aria-label={actionLabel(action)}
                        title={actionLabel(action)}
                        disabled={reclaimable === 0 || busy}
                        onClick={() => vm.requestPrune(action)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </span>
                  <span className="mt-1 block text-lg font-semibold">{size(type.size)}</span>
                  <span className="block text-xs text-muted-foreground">
                    {t("docker.inUse", { active: type.active, total: type.total_count, size: size(reclaimable) })}
                  </span>
                  {type.type === "Local Volumes" && (
                    <span className="block text-[11px] text-muted-foreground">{t("docker.volumesProtected")}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {vm.unusedImages.length > 0 && (
          <div>
            <button
              type="button"
              className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
              onClick={vm.toggleImages}
            >
              {vm.showImages ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              {t("docker.unusedImages", { count: vm.unusedImages.length })}
            </button>
            {vm.showImages && (
              <div className="mt-2 max-h-64 space-y-1 overflow-auto rounded-md bg-muted/40 p-3 font-mono text-xs">
                {vm.unusedImages.map((image) => (
                  <div key={image.id} className="flex items-center justify-between gap-3">
                    <span className="min-w-0 flex-1 truncate" title={`${image.name} ${image.id}`}>
                      {image.name === "<none>" ? `<none> ${image.id.replace("sha256:", "").slice(0, 12)}` : image.name}
                    </span>
                    <span className="shrink-0 text-muted-foreground">{image.created_since}</span>
                    <span className="shrink-0 text-muted-foreground">{size(image.size)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {vm.status === "success" && vm.lastResult && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 font-mono text-xs">
            {vm.lastResult.results.build_cache && <div>{t("docker.types.Build Cache")} — {vm.lastResult.results.build_cache}</div>}
            {vm.lastResult.results.unused_images && <div>{t("docker.types.Images")} — {vm.lastResult.results.unused_images}</div>}
          </div>
        )}
        {vm.status === "error" && vm.errorMessage && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">
            {t("docker.cleanupFailed", { error: vm.errorMessage })}
          </p>
        )}

        <ConfirmDialog
          open={confirm !== null}
          title={confirm ? t(`docker.actions.${confirm}.title`) : undefined}
          description={confirm ? t(`docker.actions.${confirm}.description`) : undefined}
          confirmLabel={confirm ? actionLabel(confirm) : undefined}
          loading={busy}
          dismissDisabled={busy}
          onConfirm={() => void vm.confirmPrune()}
          onCancel={vm.cancelPrune}
        />
      </CardContent>
    </Card>
  );
}
