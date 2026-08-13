import { Brain, Network, Orbit } from "lucide-react";
import { Button } from "@/components/ui/button";

export type DocumentViewMode = "note" | "graph" | "mindmap" | "galaxy";

/** Mapa mental/Grafo/Galaxia icon toggle group, shared by every file-tree
 * screen that can render its selection as a mind map or a wikilink graph
 * (Knowledge Base, Docs). Each button toggles its own mode on/off --
 * clicking the active one (or another one) returns to "note" (the plain
 * file view), so there's no separate "Nota" button to go back with. The
 * "galaxy" (3D star-field) button only renders when a consumer passes
 * `galaxy` -- opt-in per screen (Knowledge Base only, so far) rather than
 * appearing everywhere this toggle is used.
 * Icon-only (no grouped pill background) to match the rest of the icon
 * toolbar -- labels move to the title/aria-label tooltip. */
export function ViewModeToggle({
  viewMode,
  onViewModeChange,
  mindMapDisabled,
  labels,
  galaxy,
}: {
  viewMode: DocumentViewMode;
  onViewModeChange: (mode: DocumentViewMode) => void;
  mindMapDisabled?: boolean;
  labels: { mindMap: string; graph: string };
  galaxy?: { label: string; disabled?: boolean };
}) {
  function toggle(mode: "mindmap" | "graph" | "galaxy") {
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
      {galaxy && (
        <Button
          variant={viewMode === "galaxy" ? "secondary" : "outline"}
          size="icon"
          title={galaxy.label}
          aria-label={galaxy.label}
          onClick={() => toggle("galaxy")}
          disabled={galaxy.disabled}
        >
          <Orbit className="h-4 w-4" />
        </Button>
      )}
    </>
  );
}
