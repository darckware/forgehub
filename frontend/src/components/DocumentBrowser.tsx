import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Brain, FileText, Network, Search } from "lucide-react";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import type { DocTreeNode } from "@/components/DocTree";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type DocumentViewMode = "note" | "graph" | "mindmap";

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

export function DocumentBrowser({
  title,
  searchValue,
  onSearchChange,
  searchPlaceholder,
  viewMode,
  onViewModeChange,
  mindMapDisabled,
  actions,
  tree,
  children,
  bodyClassName,
}: {
  title: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder: string;
  viewMode: DocumentViewMode;
  onViewModeChange: (mode: DocumentViewMode) => void;
  mindMapDisabled?: boolean;
  actions?: ReactNode;
  tree: ReactNode;
  children: ReactNode;
  bodyClassName?: string;
}) {
  const { t } = useTranslation("documentBrowser");
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold">{title}</h2>
          <div className="relative min-w-[16rem] flex-1">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchValue}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder={searchPlaceholder}
              className="pl-8"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1 rounded-md bg-muted p-0.5">
              <Button
                variant={viewMode === "note" ? "secondary" : "ghost"}
                size="sm"
                className={cn("h-7", viewMode === "note" && "shadow-sm")}
                onClick={() => onViewModeChange("note")}
              >
                <FileText className="mr-2 h-3.5 w-3.5" />
                {t("note")}
              </Button>
              <Button
                variant={viewMode === "mindmap" ? "secondary" : "ghost"}
                size="sm"
                className={cn("h-7", viewMode === "mindmap" && "shadow-sm")}
                onClick={() => onViewModeChange("mindmap")}
                disabled={mindMapDisabled}
              >
                <Brain className="mr-2 h-3.5 w-3.5" />
                {t("mindMap")}
              </Button>
              <Button
                variant={viewMode === "graph" ? "secondary" : "ghost"}
                size="sm"
                className={cn("h-7", viewMode === "graph" && "shadow-sm")}
                onClick={() => onViewModeChange("graph")}
              >
                <Network className="mr-2 h-3.5 w-3.5" />
                {t("graph")}
              </Button>
            </div>
            {actions}
            <AssistantToggleButton size="sm" />
          </div>
        </div>

        <div className={cn("flex h-[65vh] gap-4 overflow-hidden rounded-lg border border-border", bodyClassName)}>
          <aside className="flex w-72 shrink-0 flex-col overflow-y-auto border-r border-border p-2">
            {tree}
          </aside>
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
        </div>
      </CardContent>
    </Card>
  );
}
