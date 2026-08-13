import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Code2, FoldVertical, Folder, PanelLeftClose, PanelLeftOpen, UnfoldVertical } from "lucide-react";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { SearchFilterInput } from "@/components/SearchFilterInput";
import { ViewModeToggle, type DocumentViewMode } from "@/components/ViewModeToggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type { DocumentViewMode };

/** Full-bleed file-browser page shell -- the exact structure of the Docs
 * page (title row, path/search/view-toggle row, tree+content as two
 * separate cards), extracted so other single-purpose browser pages (the
 * Knowledge Base) render identically instead of drifting into their own
 * boxed-Card layout. Pages using this must be added to AppLayout's
 * `isFullBleed` list -- it fills its flex-column ancestor's height rather
 * than sitting inside the standard page padding. Multi-section pages that
 * stack a browser alongside other cards (Foundation) should keep using the
 * boxed `DocumentBrowser` instead. */
export function DocumentWorkspace({
  title,
  titleIcon,
  titleSuffix,
  path,
  onResetPath,
  searchValue,
  onSearchChange,
  searchPlaceholder,
  viewMode,
  onViewModeChange,
  mindMapDisabled,
  showGalaxy,
  galaxyDisabled,
  rawView,
  onRawViewChange,
  rawViewDisabled,
  actions,
  assistantOpenTitle,
  treeExpand,
  tree,
  children,
  className,
}: {
  title: string;
  titleIcon?: ReactNode;
  /** Rendered at the left of the title row's second column, before the
   * action icons -- mirrors the Docs page's area switcher
   * ("selecione pasta · /root/docs"). */
  titleSuffix?: ReactNode;
  /** Folder currently being browsed, relative to the tree root -- "/" at
   * the root, "/subfolder" once one is selected as the working folder.
   * Deliberately not the absolute host path (already shown elsewhere,
   * e.g. the title row) to keep this row short and stable. */
  path: string;
  /** Makes the folder icon a "go to root" button -- clicking it resets the
   * working folder, replacing the old separate "usar raiz" text link. */
  onResetPath?: () => void;
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder: string;
  viewMode: DocumentViewMode;
  onViewModeChange: (mode: DocumentViewMode) => void;
  mindMapDisabled?: boolean;
  /** Renders the 3D "memory galaxy" button in the mind map/graph group --
   * opt-in, omit (or leave false) to not render it (see `ViewModeToggle`). */
  showGalaxy?: boolean;
  galaxyDisabled?: boolean;
  /** Raw-source toggle, rendered to the left of the mind map/graph
   * buttons -- independent of viewMode (mirrors the Docs page's "view
   * file" button). Omit to not render it. */
  rawView?: boolean;
  onRawViewChange?: (value: boolean) => void;
  rawViewDisabled?: boolean;
  actions?: ReactNode;
  assistantOpenTitle?: string;
  /** Drives the "expand all / collapse all" toggle rendered right of the
   * hide-directory button -- omit on pages whose tree doesn't come from
   * `useExpandedTree` (none currently, but keeps this shell reusable for a
   * future read-only tree). */
  treeExpand?: { allExpanded: boolean; onToggleAll: () => void };
  tree: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const { t } = useTranslation("documentBrowser");
  const [hideTree, setHideTree] = useState(false);
  return (
    <div className={cn("flex min-h-0 w-full flex-1 flex-col gap-4 p-6", className)}>
      <div className="grid grid-cols-[280px_1fr] items-center gap-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          {titleIcon}
          {title}
        </h1>
        <div className="flex flex-wrap items-center justify-between gap-2">
          {titleSuffix}
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            {actions}
            <AssistantToggleButton size="icon" openTitle={assistantOpenTitle} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-[280px_1fr] items-center gap-4">
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <button
            type="button"
            title={t("useRoot")}
            aria-label={t("useRoot")}
            onClick={onResetPath}
            disabled={!onResetPath}
            className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground disabled:pointer-events-none"
          >
            <Folder className="h-3.5 w-3.5" />
          </button>
          <span className="flex min-w-0 flex-wrap items-center gap-1.5">
            <code className="break-all text-foreground">{path}</code>
          </span>
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            title={hideTree ? t("showTree") : t("hideTree")}
            aria-label={hideTree ? t("showTree") : t("hideTree")}
            onClick={() => setHideTree((v) => !v)}
          >
            {hideTree ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </Button>
          {treeExpand && (
            <Button
              variant="outline"
              size="icon"
              title={treeExpand.allExpanded ? t("collapseAll") : t("expandAll")}
              aria-label={treeExpand.allExpanded ? t("collapseAll") : t("expandAll")}
              onClick={treeExpand.onToggleAll}
            >
              {treeExpand.allExpanded ? <FoldVertical className="h-4 w-4" /> : <UnfoldVertical className="h-4 w-4" />}
            </Button>
          )}
          <SearchFilterInput
            value={searchValue}
            onChange={onSearchChange}
            placeholder={searchPlaceholder}
            className="flex-1"
          />
          {onRawViewChange && (
            <Button
              size="icon"
              variant={rawView ? "secondary" : "outline"}
              title={t("viewFile")}
              aria-label={t("viewFile")}
              disabled={rawViewDisabled}
              onClick={() => onRawViewChange(!rawView)}
            >
              <Code2 className="h-4 w-4" />
            </Button>
          )}
          <ViewModeToggle
            viewMode={viewMode}
            onViewModeChange={onViewModeChange}
            mindMapDisabled={mindMapDisabled}
            labels={{ mindMap: t("mindMap"), graph: t("graph") }}
            galaxy={showGalaxy ? { label: t("galaxy"), disabled: galaxyDisabled } : undefined}
          />
        </div>
      </div>

      <div className={cn("grid min-h-0 flex-1 gap-4", hideTree ? "grid-cols-1" : "grid-cols-[280px_1fr]")}>
        {!hideTree && (
          <Card className="min-h-0 overflow-hidden">
            <CardContent className="h-full overflow-y-auto p-2">{tree}</CardContent>
          </Card>
        )}

        <Card className="min-h-0 overflow-hidden">
          <CardContent
            className={cn(
              "h-full",
              viewMode === "note" ? "flex flex-col gap-2 overflow-y-auto p-4" : "overflow-hidden p-0"
            )}
          >
            {children}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
