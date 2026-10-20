import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, FoldVertical, Folder, PanelLeftClose, PanelLeftOpen, UnfoldVertical } from "lucide-react";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import type { DocTreeNode } from "@/components/DocTree";
import { SearchFilterInput } from "@/components/SearchFilterInput";
import { ViewModeToggle, type DocumentViewMode } from "@/components/ViewModeToggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type { DocumentViewMode };

/** Keeps matching files and their ancestor directories, so search results
 * remain navigable instead of becoming a flat list. */
export function filterDocumentTree(nodes: DocTreeNode[], query: string): DocTreeNode[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return nodes;

  const result: DocTreeNode[] = [];
  for (const node of nodes) {
    if (node.type === "file") {
      if (node.name.toLowerCase().includes(normalized) || node.path.toLowerCase().includes(normalized)) {
        result.push(node);
      }
      continue;
    }

    const children = filterDocumentTree(node.children ?? [], normalized);
    if (children.length > 0 || node.name.toLowerCase().includes(normalized)) {
      result.push({ ...node, children });
    }
  }
  return result;
}

/** Same title/path/search/view-toggle rows and two-card tree+content split
 * as `DocumentWorkspace`, but sized to sit inline in a normally-scrolling
 * page (fixed `h-[65vh]` body instead of filling a full-bleed flex
 * ancestor) -- for pages that stack a browser alongside other cards
 * (Foundation's Scripts card). Single-purpose browser pages (Docs,
 * Knowledge Base) should use `DocumentWorkspace` instead. */
export function DocumentBrowser({
  title,
  titleSuffix,
  path,
  onResetPath,
  searchValue,
  onSearchChange,
  searchPlaceholder,
  viewMode,
  onViewModeChange,
  mindMapDisabled,
  actions,
  treeExpand,
  tree,
  children,
  onBack,
  hasSelection = false,
  bodyClassName,
}: {
  title: string;
  /** Rendered at the left of the title row's second column, before the
   * action icons -- mirrors the Docs page's area switcher
   * ("selecione pasta · /root/docs"). */
  titleSuffix?: ReactNode;
  /** Folder currently being browsed, relative to the tree root -- "/" at
   * the root, "/subfolder" once one is selected as the working folder. */
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
  actions?: ReactNode;
  /** Drives the "expand all / collapse all" toggle rendered right of the
   * hide-directory button -- see `useExpandedTree` in `DocTree.tsx`. */
  treeExpand?: { allExpanded: boolean; onToggleAll: () => void };
  tree: ReactNode;
  children: ReactNode;
  /** Phone layout (below md): with a document open, the tree hides and the
   * document fills the screen with a back button that calls this -- the
   * page clears its own selection. Omit to keep the side-by-side split. */
  onBack?: () => void;
  /** Whether a document is open -- decides which half a phone shows. */
  hasSelection?: boolean;
  bodyClassName?: string;
}) {
  const { t } = useTranslation("documentBrowser");
  const [hideTree, setHideTree] = useState(false);
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 items-center gap-4 md:grid-cols-[280px_1fr]">
        <h2 className="flex items-center gap-2 text-xl font-semibold">{title}</h2>
        <div className="flex flex-wrap items-center justify-between gap-2">
          {titleSuffix}
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            {actions}
            <AssistantToggleButton size="icon" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 items-center gap-4 md:grid-cols-[280px_1fr]">
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
        <div className="flex min-w-0 flex-wrap items-center gap-2 md:flex-nowrap">
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
            // Own line on a phone -- beside the icon row it was one letter wide.
            className="min-w-0 flex-1 max-md:order-first max-md:basis-full"
          />
          <ViewModeToggle
            viewMode={viewMode}
            onViewModeChange={onViewModeChange}
            mindMapDisabled={mindMapDisabled}
            labels={{ mindMap: t("mindMap"), graph: t("graph") }}
          />
        </div>
      </div>

      <div
        className={cn(
          "grid h-[65vh] gap-4",
          hideTree ? "grid-cols-1" : "grid-cols-1 md:grid-cols-[280px_1fr]",
          bodyClassName
        )}
      >
        {/* Phone: tree until a document is picked, then the document with a
            back bar (only when the page wires onBack). Desktop unchanged. */}
        {!hideTree && (
          <Card className={cn("min-h-0 overflow-hidden", onBack && hasSelection && "max-md:hidden")}>
            <CardContent className="h-full overflow-y-auto p-2">{tree}</CardContent>
          </Card>
        )}

        <Card className={cn("flex min-h-0 flex-col overflow-hidden", onBack && !hasSelection && !hideTree && "max-md:hidden")}>
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="flex shrink-0 items-center gap-1.5 border-b border-border px-3 py-2 text-sm text-muted-foreground hover:text-foreground md:hidden"
            >
              <ChevronLeft className="h-4 w-4" />
              {t("backToTree")}
            </button>
          )}
          <CardContent
            className={cn(
              "min-h-0 flex-1",
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
