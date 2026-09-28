import { ChevronDown, ChevronRight, HardDriveDownload, Loader2, Lock, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useBackupFilesViewModel } from "@/hooks/useBackupFilesViewModel";
import { cn } from "@/lib/utils";

/** Decimal units, like the Docker card and `du --si`. */
function formatSize(bytes: number): string {
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

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

/** Backup files on the host, grouped, with selection and "move to trash" (2026-09-28). */
export function BackupFilesCard() {
  const vm = useBackupFilesViewModel();
  const busy = vm.status === "submitting";

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <HardDriveDownload className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">Backups</h2>
            {vm.data && (
              <span className="text-xs text-muted-foreground">
                {vm.data.total_count} item(s), {formatSize(vm.data.total_size)} — {formatSize(vm.data.reclaimable_size)} removable
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button size="sm" variant="outline" className="gap-2" onClick={vm.refresh} disabled={vm.refreshing || busy}>
              <RefreshCw className={cn("h-4 w-4", vm.refreshing && "animate-spin")} />
              Rescan
            </Button>
            <Button
              size="sm"
              variant="destructive"
              className="gap-2"
              onClick={vm.requestDelete}
              disabled={vm.selected.size === 0 || busy}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Move {vm.selected.size > 0 ? `${vm.selected.size} (${formatSize(vm.selectedSize)})` : "selected"} to trash
            </Button>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">
          /root/backup, the weekly Hermes archive (newest archive protected), rollback snapshots and dumps left in /tmp.
          Items go to the trash — space is freed when you empty it. System (/var/backups) and project source files are
          never listed.
        </p>

        {vm.status === "loading" && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Scanning backups…
          </p>
        )}
        {vm.loadError && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">
            Failed to scan backups: {vm.loadError}
          </p>
        )}
        {vm.data && vm.groups.length === 0 && <p className="text-sm text-muted-foreground">No backup files found.</p>}

        <div className="space-y-2">
          {vm.groups.map((group) => {
            const open = vm.expanded.has(group.group);
            const removable = group.items.some((item) => !item.protected);
            return (
              <div key={group.group} className="rounded-md border border-border">
                <div className="flex flex-wrap items-center gap-2 p-2">
                  <input
                    type="checkbox"
                    aria-label={`Select all in ${group.label}`}
                    className="h-4 w-4"
                    checked={vm.isGroupSelected(group)}
                    disabled={!removable || busy}
                    onChange={() => vm.toggleGroup(group)}
                  />
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-1 text-left text-sm font-medium"
                    onClick={() => vm.toggleExpanded(group.group)}
                  >
                    {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                    <span className="truncate">{group.label}</span>
                  </button>
                  <span className="text-xs text-muted-foreground">
                    {group.count} · {formatSize(group.total_size)}
                  </span>
                </div>
                {open && (
                  <div className="max-h-72 space-y-1 overflow-auto border-t border-border bg-muted/30 p-2 font-mono text-xs">
                    {group.items.map((item) => (
                      <label key={item.path} className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 shrink-0"
                          checked={vm.selected.has(item.path)}
                          disabled={Boolean(item.protected) || busy}
                          onChange={() => vm.toggleItem(item.path)}
                        />
                        <span className="min-w-0 flex-1 truncate" title={item.protected ?? item.path}>
                          {item.protected && <Lock className="mr-1 inline h-3 w-3" />}
                          {item.path}
                          {item.is_dir ? "/" : ""}
                        </span>
                        <span className="shrink-0 text-muted-foreground">{formatDate(item.mtime)}</span>
                        <span className="w-16 shrink-0 text-right text-muted-foreground">{formatSize(item.size)}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {vm.status === "success" && vm.lastResult && (
          <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-sm">
            Moved {vm.lastResult.count} item(s), {formatSize(vm.lastResult.total_size)}, to {vm.lastResult.trash_path}. Empty
            the trash in the Cleanup card to free the space.
          </p>
        )}
        {vm.status === "error" && vm.errorMessage && (
          <p className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm text-destructive">
            {vm.errorMessage}
          </p>
        )}

        <ConfirmDialog
          open={vm.status === "confirming" || busy}
          title="Move backups to trash?"
          description={`${vm.selected.size} item(s), ${formatSize(vm.selectedSize)}, will be moved to the trash. They can be restored from there until the trash is emptied; after that they are gone for good.`}
          confirmLabel="Move to trash"
          loading={busy}
          dismissDisabled={busy}
          onConfirm={() => void vm.confirmDelete()}
          onCancel={vm.cancelDelete}
        />
      </CardContent>
    </Card>
  );
}
