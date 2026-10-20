import { useEffect, useRef } from "react";
import ForceGraph3D, { type ForceGraph3DInstance } from "3d-force-graph";
import type { DocGraph, GraphNode } from "@/components/GraphView";

/** "Memory galaxy" 3D star-field variant of `GraphView` -- same data shape
 * (notes as nodes, [[wikilinks]] as edges), rendered via `3d-force-graph`
 * (three.js, same author/API family as the 2D `force-graph` package
 * GraphView already uses). Drag to orbit, scroll to zoom, click a star to
 * open it, double-click to pause the slow auto-rotate "flight". */
export function GalaxyView({
  graph,
  onSelectNode,
}: {
  graph: DocGraph;
  onSelectNode: (path: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraph3DInstance | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const fg = new ForceGraph3D(el)
      .graphData({
        nodes: graph.nodes.map((n) => ({ ...n })),
        links: graph.edges.map((e) => ({ ...e })),
      })
      .nodeId("id")
      .nodeLabel("label")
      .nodeAutoColorBy("id")
      .nodeOpacity(0.9)
      .nodeResolution(8)
      .nodeVal(() => 1.5)
      .linkColor(() => "rgba(148, 163, 184, 0.3)")
      .linkOpacity(0.35)
      .backgroundColor("#00000a")
      .showNavInfo(false)
      .onNodeClick((node) => onSelectNode(String((node as GraphNode).id)))
      .width(el.clientWidth)
      .height(el.clientHeight);
    fgRef.current = fg;

    // Slow ambient orbit ("flight") until the user double-clicks to pause it.
    const controls = fg.controls() as { autoRotate: boolean; autoRotateSpeed: number };
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.4;
    function toggleFlight() {
      controls.autoRotate = !controls.autoRotate;
    }
    el.addEventListener("dblclick", toggleFlight);

    const resizeObserver = new ResizeObserver(() => {
      fg.width(el.clientWidth).height(el.clientHeight);
    });
    resizeObserver.observe(el);

    return () => {
      el.removeEventListener("dblclick", toggleFlight);
      resizeObserver.disconnect();
      fg.pauseAnimation();
      el.replaceChildren();
      fgRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  return <div ref={containerRef} className="h-full w-full" />;
}
