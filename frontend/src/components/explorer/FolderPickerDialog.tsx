import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUp, Check, ChevronRight, Copy, Folder, FolderInput, FolderPlus, HardDrive, Home, Loader2, Star, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  isValidName,
  joinPath,
  parentPath,
  pathSegments,
  useExplorerListing,
  useExplorerMutations,
  type ExplorerEntry,
} from "@/hooks/useFileExplorer";
import { errorMessage, type FileExplorerViewModel } from "@/hooks/useFileExplorerViewModel";
import type { QuickAccessItem } from "./ExplorerTree";

/** "Move to…" / "Copy to…" -- Windows' folder picker: browse to a folder
 * (click selects it, double-click opens it), optionally create one, then
 * confirm. The actual transfer is vm.transferTo, the same code path as
 * paste and drag-and-drop. */
export function FolderPickerDialog({
  vm,
  entries,
  mode,
  quickAccess,
}: {
  vm: FileExplorerViewModel;
  entries: ExplorerEntry[];
  mode: "copy" | "move";
  quickAccess: QuickAccessItem[];
}) {
  const { t } = useTranslation("explorer");
  const [browsePath, setBrowsePath] = useState(vm.path);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [address, setAddress] = useState<string | null>(null);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const listing = useExplorerListing(browsePath);
  // Long paths: keep the END (the folder you're in) visible, not the root.
  const crumbsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = crumbsRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [browsePath, address]);
  const { createFolder } = useExplorerMutations();
  const destination = selectedPath ?? browsePath;
  const working = vm.operation.status === "working";
  const error = localError ?? (vm.operation.status === "error" ? vm.operation.message ?? null : null);

  // A folder being moved can't receive itself (or be entered as a target).
  const movingDirs = entries.filter((e) => e.type === "dir").map((e) => e.path);
  const isBlocked = (path: string) => movingDirs.some((dir) => path === dir || path.startsWith(`${dir}/`));
  const folders = (listing.data?.path === browsePath ? listing.data.entries : [])
    .filter((e) => e.type === "dir" && (vm.showHidden || !e.name.startsWith(".")))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
  // Moving into the folder the items already sit in is a no-op.
  const sameFolder = mode === "move" && entries.every((e) => parentPath(e.path) === destination);
  const canConfirm = !working && !isBlocked(destination) && !sameFolder;

  function browse(path: string) {
    setBrowsePath(path);
    setSelectedPath(null);
    setLocalError(null);
  }

  async function submitNewFolder() {
    const name = (newFolder ?? "").trim();
    if (!isValidName(name)) {
      setLocalError(t("dialogs.nameInvalid"));
      return;
    }
    try {
      const created = await createFolder.mutateAsync(joinPath(browsePath, name));
      setNewFolder(null);
      setLocalError(null);
      setSelectedPath(created.path);
    } catch (err) {
      setLocalError(errorMessage(err));
    }
  }

  const close = () => {
    vm.dismissError();
    vm.closeDialog();
  };
  const title =
    entries.length === 1
      ? t(mode === "move" ? "moveTo.titleOne" : "copyTo.titleOne", { name: entries[0].name })
      : t(mode === "move" ? "moveTo.titleMany" : "copyTo.titleMany", { count: entries.length });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" aria-hidden="true" onMouseDown={close} />
      <div
        className="relative z-10 flex h-[70vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
        onKeyDown={(e) => e.key === "Escape" && close()}
      >
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          {mode === "move" ? <FolderInput className="h-5 w-5 text-primary" /> : <Copy className="h-5 w-5 text-primary" />}
          <h2 className="flex-1 truncate text-base font-semibold">{title}</h2>
          <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t("actions.close")} onClick={close}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex min-h-0 flex-1">
          <div className="hidden w-48 shrink-0 overflow-auto border-r border-border py-2 sm:block">
            {quickAccess.map((item) => (
              <button
                key={item.path}
                type="button"
                title={item.path}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-1 text-left text-sm hover:bg-accent/60",
                  browsePath === item.path && "bg-accent"
                )}
                onClick={() => browse(item.path)}
              >
                {item.icon === "home" ? (
                  <Home className="h-4 w-4 shrink-0 text-sky-500" />
                ) : item.icon === "drive" ? (
                  <HardDrive className="h-4 w-4 shrink-0 text-muted-foreground" />
                ) : item.icon === "star" ? (
                  <Star className="h-4 w-4 shrink-0 text-amber-500" />
                ) : (
                  <Folder className="h-4 w-4 shrink-0 text-amber-400" />
                )}
                <span className="truncate">{item.label}</span>
              </button>
            ))}
          </div>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                disabled={!parentPath(browsePath)}
                title={t("nav.up")}
                aria-label={t("nav.up")}
                onClick={() => browse(parentPath(browsePath) ?? "/")}
              >
                <ArrowUp className="h-4 w-4" />
              </Button>
              {address !== null ? (
                <form
                  className="min-w-0 flex-1"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (address.trim().startsWith("/")) browse(address.trim().replace(/\/+$/, "") || "/");
                    setAddress(null);
                  }}
                >
                  <input
                    autoFocus
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    onBlur={() => setAddress(null)}
                    aria-label={t("nav.address")}
                    spellCheck={false}
                    className="h-8 w-full rounded-md border border-input bg-background px-2 font-mono text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                </form>
              ) : (
                <div
                  ref={crumbsRef}
                  className="flex h-8 min-w-0 flex-1 cursor-text items-center overflow-x-auto rounded-md border border-input bg-background px-1"
                  title={t("nav.editAddress")}
                  onClick={() => setAddress(browsePath)}
                >
                  {pathSegments(browsePath).map((segment, index) => (
                    <span key={segment.path} className="flex shrink-0 items-center">
                      {index > 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
                      <button
                        type="button"
                        className="rounded px-1.5 py-0.5 text-xs hover:bg-accent"
                        onClick={(e) => {
                          e.stopPropagation();
                          browse(segment.path);
                        }}
                      >
                        {segment.name}
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="min-h-0 flex-1 overflow-auto p-1" role="listbox" aria-label={t("moveTo.foldersLabel")}>
              {listing.isLoading ? (
                <div className="flex h-full items-center justify-center">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : listing.isError ? (
                <p className="p-4 text-center text-sm text-destructive">{errorMessage(listing.error)}</p>
              ) : folders.length === 0 && newFolder === null ? (
                <p className="p-4 text-center text-sm text-muted-foreground">{t("moveTo.noSubfolders")}</p>
              ) : (
                folders.map((folder) => {
                  const blocked = isBlocked(folder.path);
                  const selected = selectedPath === folder.path;
                  return (
                    <button
                      key={folder.path}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      disabled={blocked}
                      title={blocked ? t("moveTo.cannotIntoItself") : folder.path}
                      className={cn(
                        "flex w-full select-none items-center gap-2 rounded-sm px-2 py-1 text-left text-sm",
                        selected ? "bg-primary/15 ring-1 ring-primary/40" : "hover:bg-accent/60",
                        blocked && "cursor-not-allowed opacity-40"
                      )}
                      onClick={() => setSelectedPath(selected ? null : folder.path)}
                      onDoubleClick={() => !blocked && browse(folder.path)}
                    >
                      <Folder className="h-4 w-4 shrink-0 fill-amber-400/30 text-amber-400" />
                      <span className="truncate">{folder.name}</span>
                    </button>
                  );
                })
              )}
              {newFolder !== null && (
                <form
                  className="flex items-center gap-2 px-2 py-1"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void submitNewFolder();
                  }}
                >
                  <FolderPlus className="h-4 w-4 shrink-0 text-amber-400" />
                  <input
                    autoFocus
                    value={newFolder}
                    onChange={(e) => setNewFolder(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") {
                        e.stopPropagation();
                        setNewFolder(null);
                      }
                    }}
                    aria-label={t("dialogs.nameLabel")}
                    spellCheck={false}
                    className="h-7 min-w-0 flex-1 rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  />
                  <Button type="submit" size="icon" className="h-7 w-7" disabled={createFolder.isPending} aria-label={t("actions.create")}>
                    {createFolder.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                  </Button>
                </form>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-2 border-t border-border px-4 py-3">
          <div className="flex min-w-0 items-center gap-2 text-xs">
            <span className="shrink-0 text-muted-foreground">{t("moveTo.destination")}</span>
            {/* rtl + ellipsis cuts the START of a long path, so the destination
                folder's own name stays readable; the bdi keeps the path LTR. */}
            <span className="truncate text-left font-mono [direction:rtl]" title={destination}>
              <bdi>{destination}</bdi>
            </span>
          </div>
          {sameFolder && <p className="text-xs text-muted-foreground">{t("moveTo.alreadyThere")}</p>}
          {error && (
            <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </p>
          )}
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={newFolder !== null}
              onClick={() => {
                setNewFolder(t("dialogs.defaultFolderName"));
                setLocalError(null);
              }}
            >
              <FolderPlus className="mr-1.5 h-4 w-4" />
              {t("actions.newFolder")}
            </Button>
            <div className="flex-1" />
            <Button variant="outline" size="sm" onClick={close}>
              {t("moveTo.cancel")}
            </Button>
            <Button size="sm" disabled={!canConfirm} onClick={() => void vm.transferTo(entries, destination, mode)}>
              {working ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : mode === "move" ? (
                <FolderInput className="mr-1.5 h-4 w-4" />
              ) : (
                <Copy className="mr-1.5 h-4 w-4" />
              )}
              {t(mode === "move" ? "moveTo.confirm" : "copyTo.confirm")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
