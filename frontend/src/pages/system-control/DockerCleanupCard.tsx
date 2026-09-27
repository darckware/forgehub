import { ChevronDown, ChevronRight, Container, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useDockerCleanupViewModel, type DockerPruneAction } from "@/hooks/useDockerCleanupViewModel";
import { cn } from "@/lib/utils";

/** Decimal units, like Docker itself -- the page's formatBytes is binary
 * (1024), which would show `docker system df`'s "92.26GB" as "85.9 GB" and
 * make this card disagree with the CLI an operator cross-checks it against. */
function formatDockerSize(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1000) return `${bytes} B`;
  const units = ["kB", "MB", "GB", "TB"];
  let value = bytes / 1000;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unit]}`;
}

const CONFIRM_COPY: Record<DockerPruneAction, { title: string; description: string; label: string }> = {
  build_cache: {
    title: "Clear Docker build cache?",
    description:
      "Deletes the whole BuildKit cache (docker builder prune --all). Nothing running is affected; the next build of each project is slower while its layers are rebuilt.",
    label: "Clear build cache",
  },
  unused_images: {
    title: "Remove unused Docker images?",
    description:
      "Deletes every image no container uses (docker image prune --all), including rollback tags such as forgehub-frontend:rollback-*. Images of running or stopped containers are kept. Volumes are never touched.",
    label: "Remove images",
  },
  all: {
    title: "Clean Docker build cache and unused images?",
    description:
      "Deletes the whole BuildKit cache and every image no container uses, including rollback tags. Running services are not affected and volumes are never touched.",
    label: "Clean all",
  },
};

export function DockerCleanupCard() {
  const vm = useDockerCleanupViewModel();
  const confirm = vm.pendingAction ? CONFIRM_COPY[vm.pendingAction] : null;
  const busy = vm.status === "submitting";
  const disk = vm.usage?.disk;

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Container className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">Docker</h2>
            {vm.usage && (
              <span className="text-xs text-muted-foreground">
                up to {formatDockerSize(vm.totalReclaimable)} reclaimable
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button size="sm" variant="outline" className="gap-2" onClick={vm.refresh} disabled={vm.refreshing || busy}>
              <RefreshCw className={cn("h-4 w-4", vm.refreshing && "animate-spin")} />
              Refresh
            </Button>
            <Button
              size="sm"
              variant="destructive"
              className="gap-2"
              onClick={() => vm.requestPrune("all")}
              disabled={!vm.usage || vm.totalReclaimable === 0 || busy}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Clean all
            </Button>
          </div>
        </div>

        {vm.status === "loading" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Reading Docker disk usage…
          </p>
        )}
        {vm.loadError && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">
            Failed to read Docker usage: {vm.loadError}
          </p>
        )}

        {disk && vm.diskPercent !== null && (
          <div className="space-y-1">
            <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
              <span>
                Disk / — {formatDockerSize(disk.used)} of {formatDockerSize(disk.total)} used ({vm.diskPercent}%)
              </span>
              <span>{formatDockerSize(disk.available)} free</span>
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
                    <span className="text-xs font-medium uppercase text-muted-foreground">{type.type}</span>
                    {action && (
                      <button
                        type="button"
                        className="rounded p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        aria-label={CONFIRM_COPY[action].label}
                        title={CONFIRM_COPY[action].label}
                        disabled={reclaimable === 0 || busy}
                        onClick={() => vm.requestPrune(action)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </span>
                  <span className="mt-1 block text-lg font-semibold">{formatDockerSize(type.size)}</span>
                  <span className="block text-xs text-muted-foreground">
                    {type.active}/{type.total_count} in use · {formatDockerSize(reclaimable)} reclaimable
                  </span>
                  {type.type === "Local Volumes" && (
                    <span className="block text-[11px] text-muted-foreground">Never pruned (database data)</span>
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
              {vm.unusedImages.length} unused image(s)
            </button>
            {vm.showImages && (
              <div className="mt-2 max-h-64 space-y-1 overflow-auto rounded-md bg-muted/40 p-3 font-mono text-xs">
                {vm.unusedImages.map((image) => (
                  <div key={image.id} className="flex items-center justify-between gap-3">
                    <span className="min-w-0 flex-1 truncate" title={`${image.name} ${image.id}`}>
                      {image.name === "<none>" ? `<none> ${image.id.replace("sha256:", "").slice(0, 12)}` : image.name}
                    </span>
                    <span className="shrink-0 text-muted-foreground">{image.created_since}</span>
                    <span className="shrink-0 text-muted-foreground">{formatDockerSize(image.size)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {vm.status === "success" && vm.lastResult && (
          <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 font-mono text-xs">
            {vm.lastResult.results.build_cache && <div>Build cache — {vm.lastResult.results.build_cache}</div>}
            {vm.lastResult.results.unused_images && <div>Images — {vm.lastResult.results.unused_images}</div>}
          </div>
        )}
        {vm.status === "error" && vm.errorMessage && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">
            Docker cleanup failed: {vm.errorMessage}
          </p>
        )}

        <ConfirmDialog
          open={confirm !== null}
          title={confirm?.title}
          description={confirm?.description}
          confirmLabel={confirm?.label}
          loading={busy}
          dismissDisabled={busy}
          onConfirm={() => void vm.confirmPrune()}
          onCancel={vm.cancelPrune}
        />
      </CardContent>
    </Card>
  );
}
