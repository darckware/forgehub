import { useEffect, useState, type DragEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, Folder, FolderOpen, HardDrive, Home, Loader2, Pin, PinOff, RotateCcw, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { baseName, useExplorerListing, type QuickAccessEntry } from "@/hooks/useFileExplorer";

/** A built-in Quick access entry, before the user's pins/unpins are merged in. */
export type QuickAccessItem = Omit<QuickAccessEntry, "pinned">;

export interface TreeDropHandlers {
  onDragOver: (event: DragEvent, path: string) => void;
  onDrop: (event: DragEvent, path: string) => void;
  dropTarget: string | null;
}

/** Explorer's left navigation pane: Quick access links plus a lazily
 * expanded folder tree rooted at "/", auto-opened along the current path. */
export function ExplorerTree({
  currentPath,
  quickAccess,
  hiddenCount,
  showHidden,
  onNavigate,
  onUnpin,
  onRestoreDefaults,
  pinDrop,
  drop,
}: {
  currentPath: string;
  quickAccess: QuickAccessEntry[];
  hiddenCount: number;
  showHidden: boolean;
  onNavigate: (path: string) => void;
  onUnpin: (entry: QuickAccessEntry) => void;
  onRestoreDefaults: () => void;
  /** Dropping folders on the "Quick access" heading pins them, like Explorer. */
  pinDrop: {
    onDragOver: (event: DragEvent) => void;
    onDragLeave: () => void;
    onDrop: (event: DragEvent) => void;
    active: boolean;
  };
  drop: TreeDropHandlers;
}) {
  const { t } = useTranslation("explorer");
  return (
    <nav aria-label={t("tree.label")} className="flex min-h-0 flex-col overflow-auto py-2 text-sm">
      <div
        className={cn(
          "mx-1 flex items-center gap-1 rounded-sm px-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground",
          pinDrop.active && "bg-primary/10 ring-1 ring-primary"
        )}
        title={t("tree.quickAccessHelp")}
        onDragOver={pinDrop.onDragOver}
        onDragLeave={pinDrop.onDragLeave}
        onDrop={pinDrop.onDrop}
      >
        <span className="flex-1">{t("tree.quickAccess")}</span>
        {hiddenCount > 0 && (
          <button
            type="button"
            className="flex items-center gap-0.5 rounded px-1 normal-case tracking-normal hover:bg-accent hover:text-foreground"
            title={t("tree.restoreDefaultsHelp", { count: hiddenCount })}
            onClick={onRestoreDefaults}
          >
            <RotateCcw className="h-3 w-3" />
            {t("tree.restoreDefaults")}
          </button>
        )}
      </div>
      <div role="group" aria-label={t("tree.quickAccess")}>
      {quickAccess.map((item) => (
        <TreeRow
          key={`qa-${item.path}`}
          depth={0}
          label={item.label}
          title={item.path}
          icon={quickIcon(item.icon)}
          active={currentPath === item.path}
          isDropTarget={drop.dropTarget === item.path}
          onClick={() => onNavigate(item.path)}
          onDragOver={(e) => drop.onDragOver(e, item.path)}
          onDrop={(e) => drop.onDrop(e, item.path)}
          action={{ label: t("actions.unpin"), icon: <PinOff className="h-3.5 w-3.5" />, onClick: () => onUnpin(item) }}
        />
      ))}
      </div>
      <div className="mt-3 px-3 pb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t("tree.thisComputer")}
      </div>
      <TreeNode path="/" depth={0} currentPath={currentPath} showHidden={showHidden} onNavigate={onNavigate} drop={drop} />
    </nav>
  );
}

function quickIcon(icon: QuickAccessItem["icon"]) {
  const cls = "h-4 w-4 shrink-0";
  if (icon === "home") return <Home className={cn(cls, "text-sky-500")} />;
  if (icon === "drive") return <HardDrive className={cn(cls, "text-muted-foreground")} />;
  if (icon === "star") return <Star className={cn(cls, "text-amber-500")} />;
  if (icon === "pin") return <Pin className={cn(cls, "text-primary")} />;
  return <Folder className={cn(cls, "text-amber-400")} />;
}

function isAncestor(ancestor: string, path: string) {
  return ancestor === "/" ? path !== "/" : path.startsWith(`${ancestor}/`);
}

function TreeNode({
  path,
  depth,
  currentPath,
  showHidden,
  onNavigate,
  drop,
}: {
  path: string;
  depth: number;
  currentPath: string;
  showHidden: boolean;
  onNavigate: (path: string) => void;
  drop: TreeDropHandlers;
}) {
  const [expanded, setExpanded] = useState(() => path === "/" || isAncestor(path, currentPath));
  useEffect(() => {
    if (isAncestor(path, currentPath)) setExpanded(true);
  }, [path, currentPath]);
  const listing = useExplorerListing(path, expanded);
  const children = (listing.data?.path === path ? listing.data.entries : [])
    .filter((e) => e.type === "dir" && (showHidden || !e.name.startsWith(".")))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
  const active = currentPath === path;

  return (
    <>
      <TreeRow
        depth={depth}
        label={path === "/" ? "/" : baseName(path)}
        title={path}
        icon={
          path === "/" ? (
            <HardDrive className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : expanded ? (
            <FolderOpen className="h-4 w-4 shrink-0 text-amber-400" />
          ) : (
            <Folder className="h-4 w-4 shrink-0 text-amber-400" />
          )
        }
        chevron={
          listing.isFetching && expanded && !listing.data ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : expanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )
        }
        onToggle={() => setExpanded((v) => !v)}
        active={active}
        isDropTarget={drop.dropTarget === path}
        onClick={() => onNavigate(path)}
        onDragOver={(e) => drop.onDragOver(e, path)}
        onDrop={(e) => drop.onDrop(e, path)}
      />
      {expanded &&
        children.map((child) => (
          <TreeNode
            key={child.path}
            path={child.path}
            depth={depth + 1}
            currentPath={currentPath}
            showHidden={showHidden}
            onNavigate={onNavigate}
            drop={drop}
          />
        ))}
    </>
  );
}

function TreeRow({
  depth,
  label,
  title,
  icon,
  chevron,
  onToggle,
  active,
  isDropTarget,
  onClick,
  onDragOver,
  onDrop,
  action,
}: {
  depth: number;
  label: string;
  title: string;
  icon: ReactNode;
  chevron?: ReactNode;
  onToggle?: () => void;
  active: boolean;
  isDropTarget: boolean;
  onClick: () => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: (event: DragEvent) => void;
  /** Hover-revealed row action (Quick access rows: unpin). */
  action?: { label: string; icon: ReactNode; onClick: () => void };
}) {
  return (
    <div
      className={cn(
        "group flex items-center gap-1 rounded-sm py-0.5 pr-2",
        active ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
        isDropTarget && "ring-1 ring-primary"
      )}
      style={{ paddingLeft: 4 + depth * 12 }}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {onToggle ? (
        <button
          type="button"
          tabIndex={-1}
          className="flex h-4 w-4 shrink-0 items-center justify-center rounded text-muted-foreground hover:text-foreground"
          onClick={onToggle}
          aria-label={title}
        >
          {chevron}
        </button>
      ) : (
        <span className="w-4 shrink-0" />
      )}
      <button type="button" className="flex min-w-0 flex-1 items-center gap-1.5 text-left" title={title} onClick={onClick}>
        {icon}
        <span className="truncate">{label}</span>
      </button>
      {action && (
        <button
          type="button"
          className="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 hover:bg-accent hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
          title={action.label}
          aria-label={`${action.label}: ${label}`}
          onClick={action.onClick}
        >
          {action.icon}
        </button>
      )}
    </div>
  );
}
