import { Brain, Network } from "lucide-react";
import { Button } from "@/components/ui/button";

export type DocumentViewMode = "note" | "graph" | "mindmap";

/** Mapa mental/Grafo icon toggle pair, shared by every file-tree screen
 * that can render its selection as a mind map or a wikilink graph
 * (Knowledge Base, Docs). Each button toggles its own mode on/off --
 * clicking the active one (or the other one) returns to "note" (the plain
 * file view), so there's no separate "Nota" button to go back with.
 * Icon-only (no grouped pill background) to match the rest of the icon
 * toolbar -- labels move to the title/aria-label tooltip. */
export function ViewModeToggle({
  viewMode,
  onViewModeChange,
  mindMapDisabled,
  labels,
}: {
  viewMode: DocumentViewMode;
  onViewModeChange: (mode: DocumentViewMode) => void;
  mindMapDisabled?: boolean;
  labels: { mindMap: string; graph: string };
}) {
  function toggle(mode: "mindmap" | "graph") {
    onViewModeChange(viewMode === mode ? "note" : mode);
  }

  return (
    <>
      <Button
        variant={viewMode === "mindmap" ? "secondary" : "outline"}
        size="icon"
        title={labels.mindMap}
        aria-label={labels.mindMap}
        onClick={() => toggle("mindmap")}
        disabled={mindMapDisabled}
      >
        <Brain className="h-4 w-4" />
      </Button>
      <Button
        variant={viewMode === "graph" ? "secondary" : "outline"}
        size="icon"
        title={labels.graph}
        aria-label={labels.graph}
        onClick={() => toggle("graph")}
      >
        <Network className="h-4 w-4" />
      </Button>
    </>
  );
}
