import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./SystemMapCanvas.css";
import { useTranslation } from "react-i18next";
import { LayoutGrid, Loader2, ShieldCheck, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useTheme } from "@/lib/theme";
import {
  useAddSystemElement,
  useAddSystemRelation,
  useDeleteSystemRelation,
  useMoveSystemElement,
  useRemoveSystemElement,
  useUpdateSystemElement,
  useValidateBlueprint,
  type BlueprintGraph,
} from "@/hooks/useSystemScope";

// dataviz skill's validated 8-slot categorical palette (references/palette.md),
// ported from the never-wired ScopeGraphDiagram.tsx this canvas replaces.
// "assurance" is the 9th family -- per the skill's own rule a 9th series is
// never a generated hue, so it folds to a neutral tone.
export const FAMILY_ORDER = [
  "business", "process", "experience", "interface", "domain",
  "application", "data", "runtime", "assurance",
] as const;

const FAMILY_COLOR: Record<string, { light: string; dark: string }> = {
  business: { light: "#2a78d6", dark: "#3987e5" },
  process: { light: "#008300", dark: "#008300" },
  experience: { light: "#e87ba4", dark: "#d55181" },
  interface: { light: "#eda100", dark: "#c98500" },
  domain: { light: "#1baf7a", dark: "#199e70" },
  application: { light: "#eb6834", dark: "#d95926" },
  data: { light: "#4a3aa7", dark: "#9085e9" },
  runtime: { light: "#e34948", dark: "#e66767" },
  assurance: { light: "#898781", dark: "#898781" },
};

export const FAMILY_TYPES: Record<string, string[]> = {
  business: ["capability", "module", "persona"],
  process: ["journey", "process", "process_step", "use_case"],
  experience: ["application", "channel", "route", "screen", "form", "report", "ui_component"],
  interface: ["api", "endpoint", "command", "query", "event", "webhook", "integration"],
  domain: ["domain_entity", "value_object", "business_rule", "authorization_rule"],
  application: ["service", "handler", "class", "method", "workflow", "job"],
  data: ["datastore", "schema", "table", "field", "index", "view", "procedure", "migration"],
  runtime: ["runtime_component", "queue", "cache", "deployment_unit", "environment_target"],
  assurance: ["test_scenario", "metric", "log_signal", "alert", "slo", "health_check"],
};

export const RELATION_TYPES = [
  "contains", "precedes", "navigates_to", "invokes", "implements", "governed_by",
  "reads", "writes", "depends_on", "persists_as", "runs_on", "deployed_to", "verified_by",
];

const NODE_WIDTH = 200;
const COL_WIDTH = 240;
const ROW_HEIGHT = 76;
const PADDING = 40;

type ElementItem = BlueprintGraph["elements"][number];
type ElementNodeData = { item: ElementItem };
type ElementFlowNode = Node<ElementNodeData, "systemElement">;

/** Shared clipboard format for both Ctrl+C/Ctrl+V duplication and pasting a
 * flow the assistant wrote out as JSON in the chat -- both paths end up
 * validating/importing through the exact same code, so the assistant never
 * needs write access of its own (see buildSystemMapContext in index.tsx). */
export interface SystemMapClipboardPayload {
  elements: {
    key: string;
    family: string;
    element_type: string;
    name: string;
    stable_key?: string;
    position?: { x: number; y: number };
  }[];
  relations?: { from: string; to: string; relation_type: string }[];
}

function validateClipboardPayload(raw: unknown): SystemMapClipboardPayload | null {
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as Record<string, unknown>).elements)) return null;
  const elements: SystemMapClipboardPayload["elements"] = [];
  for (const item of (raw as Record<string, unknown>).elements as unknown[]) {
    if (!item || typeof item !== "object") continue;
    const el = item as Record<string, unknown>;
    const family = typeof el.family === "string" ? el.family : "";
    const elementType = typeof el.element_type === "string" ? el.element_type : "";
    const name = typeof el.name === "string" ? el.name.trim() : "";
    if (!FAMILY_TYPES[family]?.includes(elementType) || !name) continue;
    const rawPosition = el.position as { x?: unknown; y?: unknown } | undefined;
    elements.push({
      key: typeof el.key === "string" && el.key ? el.key : `e${elements.length + 1}`,
      family, element_type: elementType, name,
      stable_key: typeof el.stable_key === "string" && el.stable_key ? el.stable_key : undefined,
      position: rawPosition && typeof rawPosition.x === "number" && typeof rawPosition.y === "number"
        ? { x: rawPosition.x, y: rawPosition.y } : undefined,
    });
  }
  if (elements.length === 0) return null;
  const validKeys = new Set(elements.map((el) => el.key));
  const relations: NonNullable<SystemMapClipboardPayload["relations"]> = [];
  const rawRelations = (raw as Record<string, unknown>).relations;
  if (Array.isArray(rawRelations)) {
    for (const item of rawRelations) {
      if (!item || typeof item !== "object") continue;
      const rel = item as Record<string, unknown>;
      const from = typeof rel.from === "string" ? rel.from : "";
      const to = typeof rel.to === "string" ? rel.to : "";
      const relationType = typeof rel.relation_type === "string" ? rel.relation_type : "";
      if (!validKeys.has(from) || !validKeys.has(to) || !RELATION_TYPES.includes(relationType)) continue;
      relations.push({ from, to, relation_type: relationType });
    }
  }
  return { elements, relations };
}

/** Positions for payload elements missing an explicit position (e.g. an
 * AI-authored paste, which never has canvas coordinates) -- same
 * column-per-family idea as fallbackPosition, scoped to just this payload. */
function layoutPayloadElements(elements: SystemMapClipboardPayload["elements"]): Map<string, { x: number; y: number }> {
  const columns = FAMILY_ORDER.filter((family) => elements.some((el) => el.family === family));
  const rowByFamily: Record<string, number> = {};
  const positions = new Map<string, { x: number; y: number }>();
  for (const el of elements) {
    if (el.position) { positions.set(el.key, el.position); continue; }
    const colIndex = Math.max(0, columns.indexOf(el.family as (typeof FAMILY_ORDER)[number]));
    const row = rowByFamily[el.family] ?? 0;
    rowByFamily[el.family] = row + 1;
    positions.set(el.key, { x: colIndex * COL_WIDTH, y: row * ROW_HEIGHT });
  }
  return positions;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Deterministic column-per-family fallback for elements with no saved
 * spec_snapshot.position (legacy elements, or anything created before this
 * feature) -- ported from the layout math in the never-wired ScopeGraphDiagram. */
function fallbackPosition(item: ElementItem, elements: ElementItem[]): { x: number; y: number } {
  const columns = FAMILY_ORDER.filter((family) => elements.some((el) => el.element.family === family));
  const colIndex = Math.max(0, columns.indexOf(item.element.family as (typeof FAMILY_ORDER)[number]));
  const siblings = elements.filter((el) => el.element.family === item.element.family);
  const rowIndex = Math.max(0, siblings.findIndex((el) => el.element.id === item.element.id));
  return { x: PADDING + colIndex * COL_WIDTH, y: PADDING + rowIndex * ROW_HEIGHT };
}

/** Same column-per-family layout as fallbackPosition, computed once for the
 * whole graph -- used by the "auto-arrange" toolbar action, which resets
 * every element's position regardless of what's currently saved. */
function computeAutoLayout(elements: ElementItem[]): Map<string, { x: number; y: number }> {
  const columns = FAMILY_ORDER.filter((family) => elements.some((el) => el.element.family === family));
  const rowByFamily: Record<string, number> = {};
  const positions = new Map<string, { x: number; y: number }>();
  for (const item of elements) {
    const colIndex = Math.max(0, columns.indexOf(item.element.family as (typeof FAMILY_ORDER)[number]));
    const row = rowByFamily[item.element.family] ?? 0;
    rowByFamily[item.element.family] = row + 1;
    positions.set(item.element.id, { x: PADDING + colIndex * COL_WIDTH, y: PADDING + row * ROW_HEIGHT });
  }
  return positions;
}

function readPosition(item: ElementItem, elements: ElementItem[]): { x: number; y: number } {
  const saved = item.revision.spec_snapshot?.position as { x?: number; y?: number } | undefined;
  if (saved && typeof saved.x === "number" && typeof saved.y === "number") return { x: saved.x, y: saved.y };
  return fallbackPosition(item, elements);
}

function SystemElementNode({ data, selected }: NodeProps<ElementFlowNode>) {
  const { resolvedTheme } = useTheme();
  const { element } = data.item;
  const color = (FAMILY_COLOR[element.family] ?? FAMILY_COLOR.assurance)[resolvedTheme];
  return (
    <div
      className="overflow-hidden rounded-md border bg-card shadow-sm"
      style={{ width: NODE_WIDTH, borderColor: selected ? color : undefined }}
    >
      <Handle type="target" position={Position.Left} style={{ background: color }} />
      <div className="flex">
        <div className="w-1 shrink-0" style={{ background: color }} />
        <div className="min-w-0 flex-1 px-3 py-2">
          <p className="truncate text-xs font-medium">{element.name}</p>
          <p className="truncate text-[10px] text-muted-foreground">{element.element_type} · {element.stable_key}</p>
        </div>
      </div>
      <Handle type="source" position={Position.Right} style={{ background: color }} />
    </div>
  );
}

const nodeTypes = { systemElement: SystemElementNode };

interface SystemMapCanvasProps {
  revisionId: string;
  graph: BlueprintGraph | undefined;
  isLoading: boolean;
  readOnly: boolean;
}

function CanvasInner({ revisionId, graph, isLoading, readOnly }: SystemMapCanvasProps) {
  const { t } = useTranslation("systemMap");
  const wrapperRef = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition, fitView } = useReactFlow();
  const addElement = useAddSystemElement();
  const moveElement = useMoveSystemElement();
  const updateElement = useUpdateSystemElement();
  const removeElement = useRemoveSystemElement();
  const addRelation = useAddSystemRelation();
  const deleteRelation = useDeleteSystemRelation();
  const validate = useValidateBlueprint();

  const [nodes, setNodes, onNodesChange] = useNodesState<ElementFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [pendingCreate, setPendingCreate] = useState<{
    family: string; screen: { x: number; y: number }; flow: { x: number; y: number };
    element_type: string; name: string; stable_key: string; stableKeyTouched: boolean;
  } | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<{ id: string; screen: { x: number; y: number }; relation_type: string } | null>(null);
  const [pendingEdit, setPendingEdit] = useState<{
    elementId: string; screen: { x: number; y: number };
    family: string; element_type: string; name: string; stable_key: string;
  } | null>(null);
  const [pasteStatus, setPasteStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  useEffect(() => { nodesRef.current = nodes; }, [nodes]);
  useEffect(() => { edgesRef.current = edges; }, [edges]);

  useEffect(() => {
    if (!pasteStatus) return;
    const timer = setTimeout(() => setPasteStatus(null), 5000);
    return () => clearTimeout(timer);
  }, [pasteStatus]);

  useEffect(() => {
    const elements = graph?.elements ?? [];
    setNodes(elements.map((item) => ({
      id: item.element.id,
      type: "systemElement",
      position: readPosition(item, elements),
      data: { item },
      draggable: !readOnly,
      connectable: !readOnly,
    })));
    setEdges((graph?.relations ?? []).map((rel) => ({
      id: rel.id,
      source: rel.from_element_id,
      target: rel.to_element_id,
      label: rel.relation_type,
      selectable: !readOnly,
      labelStyle: { fontSize: 10 },
      labelBgStyle: { fillOpacity: 0.85 },
    })));
  }, [graph, readOnly, setNodes, setEdges]);

  const onNodeDoubleClick = useCallback((event: React.MouseEvent, node: ElementFlowNode) => {
    if (readOnly) return;
    const bounds = wrapperRef.current?.getBoundingClientRect();
    const { element } = node.data.item;
    setPendingEdit({
      elementId: element.id,
      screen: { x: event.clientX - (bounds?.left ?? 0), y: event.clientY - (bounds?.top ?? 0) },
      family: element.family,
      element_type: element.element_type,
      name: element.name,
      stable_key: element.stable_key,
    });
  }, [readOnly]);

  const confirmEdit = () => {
    if (!pendingEdit) return;
    updateElement.mutate({
      revisionId, elementId: pendingEdit.elementId,
      name: pendingEdit.name, family: pendingEdit.family, element_type: pendingEdit.element_type, stable_key: pendingEdit.stable_key,
    }, { onSuccess: () => setPendingEdit(null) });
  };

  const deleteEditingElement = () => {
    if (!pendingEdit) return;
    removeElement.mutate({ revisionId, elementId: pendingEdit.elementId }, { onSuccess: () => setPendingEdit(null) });
  };

  const [arranging, setArranging] = useState(false);
  const autoArrange = useCallback(async () => {
    if (readOnly || !graph?.elements.length) return;
    const positions = computeAutoLayout(graph.elements);
    setNodes((prev) => prev.map((node) => {
      const position = positions.get(node.id);
      return position ? { ...node, position } : node;
    }));
    requestAnimationFrame(() => fitView({ duration: 300 }));
    setArranging(true);
    try {
      await Promise.all(graph.elements.map((item) => {
        const position = positions.get(item.element.id);
        return position ? moveElement.mutateAsync({ revisionId, elementId: item.element.id, spec_snapshot: { position } }) : Promise.resolve();
      }));
    } finally {
      setArranging(false);
    }
  }, [readOnly, graph, revisionId, moveElement, setNodes, fitView]);

  const onNodeDragStop = useCallback((_event: unknown, node: ElementFlowNode) => {
    if (readOnly) return;
    moveElement.mutate({ revisionId, elementId: node.id, spec_snapshot: { position: { x: node.position.x, y: node.position.y } } });
  }, [readOnly, revisionId, moveElement]);

  const onConnect = useCallback((connection: Connection) => {
    if (readOnly || !connection.source || !connection.target) return;
    addRelation.mutate({ revisionId, from_element_id: connection.source, to_element_id: connection.target, relation_type: "depends_on" });
  }, [readOnly, revisionId, addRelation]);

  const onEdgeClick = useCallback((event: React.MouseEvent, edge: Edge) => {
    if (readOnly) return;
    const bounds = wrapperRef.current?.getBoundingClientRect();
    setSelectedEdge({
      id: edge.id,
      screen: { x: event.clientX - (bounds?.left ?? 0), y: event.clientY - (bounds?.top ?? 0) },
      relation_type: (edge.label as string) ?? "depends_on",
    });
  }, [readOnly]);

  const onNodesDelete = useCallback((deleted: ElementFlowNode[]) => {
    if (readOnly) return;
    for (const node of deleted) removeElement.mutate({ revisionId, elementId: node.id });
  }, [readOnly, revisionId, removeElement]);

  const importPayload = useCallback(async (payload: SystemMapClipboardPayload) => {
    const bounds = wrapperRef.current?.getBoundingClientRect();
    const anchor = bounds
      ? screenToFlowPosition({ x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2 })
      : { x: 0, y: 0 };
    const positions = layoutPayloadElements(payload.elements);
    const keyToId = new Map<string, string>();
    let elementsCreated = 0;
    await Promise.all(payload.elements.map(async (el) => {
      const position = positions.get(el.key) ?? { x: 0, y: 0 };
      const stableKey = el.stable_key || `${el.element_type}.${slugify(el.name)}-${Math.random().toString(36).slice(2, 6)}`;
      try {
        const result = await addElement.mutateAsync({
          revisionId, stable_key: stableKey, family: el.family, element_type: el.element_type, name: el.name,
          spec_snapshot: { position: { x: anchor.x + position.x, y: anchor.y + position.y } },
        }) as { element: { id: string } };
        keyToId.set(el.key, result.element.id);
        elementsCreated += 1;
      } catch { /* skipped -- surfaced in the summary count below */ }
    }));
    let relationsCreated = 0;
    if (payload.relations?.length) {
      await Promise.all(payload.relations.map(async (rel) => {
        const from = keyToId.get(rel.from);
        const to = keyToId.get(rel.to);
        if (!from || !to) return;
        try {
          await addRelation.mutateAsync({ revisionId, from_element_id: from, to_element_id: to, relation_type: rel.relation_type });
          relationsCreated += 1;
        } catch { /* skipped */ }
      }));
    }
    setPasteStatus(elementsCreated > 0
      ? { ok: true, message: t("canvas.pasteSuccess", { elements: elementsCreated, relations: relationsCreated }) }
      : { ok: false, message: t("canvas.pasteInvalid") });
  }, [addElement, addRelation, revisionId, screenToFlowPosition, t]);

  useEffect(() => {
    if (readOnly) return;
    function isEditableTarget(target: EventTarget | null) {
      return target instanceof HTMLElement && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
    }
    function handleCopy(event: ClipboardEvent) {
      if (isEditableTarget(event.target)) return;
      const selected = nodesRef.current.filter((node) => node.selected);
      if (selected.length === 0) return;
      event.preventDefault();
      const idToKey = new Map(selected.map((node, i) => [node.id, `e${i + 1}`]));
      const minX = Math.min(...selected.map((node) => node.position.x));
      const minY = Math.min(...selected.map((node) => node.position.y));
      const payload: SystemMapClipboardPayload = {
        elements: selected.map((node) => ({
          key: idToKey.get(node.id) as string,
          family: node.data.item.element.family,
          element_type: node.data.item.element.element_type,
          name: node.data.item.element.name,
          position: { x: node.position.x - minX, y: node.position.y - minY },
        })),
        relations: edgesRef.current
          .filter((edge) => idToKey.has(edge.source) && idToKey.has(edge.target))
          .map((edge) => ({ from: idToKey.get(edge.source) as string, to: idToKey.get(edge.target) as string, relation_type: (edge.label as string) ?? "depends_on" })),
      };
      event.clipboardData?.setData("text/plain", JSON.stringify(payload));
    }
    function handlePaste(event: ClipboardEvent) {
      if (isEditableTarget(event.target)) return;
      const text = event.clipboardData?.getData("text/plain") ?? "";
      if (!text.trim().startsWith("{")) return;
      event.preventDefault();
      let raw: unknown;
      try { raw = JSON.parse(text); } catch { setPasteStatus({ ok: false, message: t("canvas.pasteInvalid") }); return; }
      const payload = validateClipboardPayload(raw);
      if (!payload) { setPasteStatus({ ok: false, message: t("canvas.pasteInvalid") }); return; }
      void importPayload(payload);
    }
    document.addEventListener("copy", handleCopy);
    document.addEventListener("paste", handlePaste);
    return () => {
      document.removeEventListener("copy", handleCopy);
      document.removeEventListener("paste", handlePaste);
    };
  }, [readOnly, importPayload, t]);

  const onDragOver = useCallback((event: React.DragEvent) => {
    if (readOnly) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, [readOnly]);

  const onDrop = useCallback((event: React.DragEvent) => {
    if (readOnly) return;
    event.preventDefault();
    const family = event.dataTransfer.getData("application/x-systemmap-family");
    if (!family) return;
    const bounds = wrapperRef.current?.getBoundingClientRect();
    const flow = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    setPendingCreate({
      family,
      screen: { x: event.clientX - (bounds?.left ?? 0), y: event.clientY - (bounds?.top ?? 0) },
      flow,
      element_type: FAMILY_TYPES[family]?.[0] ?? "",
      name: "",
      stable_key: "",
      stableKeyTouched: false,
    });
  }, [readOnly, screenToFlowPosition]);

  const confirmCreate = () => {
    if (!pendingCreate) return;
    addElement.mutate({
      revisionId,
      stable_key: pendingCreate.stable_key,
      family: pendingCreate.family,
      element_type: pendingCreate.element_type,
      name: pendingCreate.name,
      spec_snapshot: { position: pendingCreate.flow },
    }, { onSuccess: () => setPendingCreate(null) });
  };

  const confirmRelationType = () => {
    if (!selectedEdge) return;
    // Relation type can't be edited in place on the backend -- remove and
    // recreate is the simplest correct way to change it from this popover.
    const edge = edges.find((item) => item.id === selectedEdge.id);
    if (!edge) { setSelectedEdge(null); return; }
    deleteRelation.mutate({ revisionId, relationId: selectedEdge.id }, {
      onSuccess: () => {
        addRelation.mutate({ revisionId, from_element_id: edge.source, to_element_id: edge.target, relation_type: selectedEdge.relation_type });
        setSelectedEdge(null);
      },
    });
  };

  const removeSelectedEdge = () => {
    if (!selectedEdge) return;
    deleteRelation.mutate({ revisionId, relationId: selectedEdge.id }, { onSuccess: () => setSelectedEdge(null) });
  };

  return (
    <div className="space-y-3">
      {!readOnly && (
        <p className="text-xs text-muted-foreground">{t("canvas.copyPasteHint")}</p>
      )}

      {pasteStatus && (
        <p className={`rounded-md border p-2 text-xs ${pasteStatus.ok ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400" : "border-destructive/40 bg-destructive/5 text-destructive"}`}>
          {pasteStatus.message}
        </p>
      )}

      {!readOnly && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 p-2">
          <span className="mr-1 text-xs text-muted-foreground">{t("canvas.paletteHint")}</span>
          {FAMILY_ORDER.map((family) => {
            const color = FAMILY_COLOR[family].light;
            return (
              <div
                key={family}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData("application/x-systemmap-family", family);
                  e.dataTransfer.effectAllowed = "move";
                }}
                className="cursor-grab select-none rounded-full border px-2.5 py-1 text-xs font-medium active:cursor-grabbing"
                style={{ borderColor: color, color }}
              >
                {family}
              </div>
            );
          })}
          <Button
            size="sm"
            variant="outline"
            className="ml-auto gap-1.5"
            onClick={autoArrange}
            disabled={arranging || !graph?.elements.length}
            title={t("canvas.autoArrange")}
          >
            {arranging ? <Loader2 className="h-4 w-4 animate-spin" /> : <LayoutGrid className="h-4 w-4" />}
            {t("canvas.autoArrange")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={() => validate.mutate(revisionId)}
            disabled={validate.isPending}
          >
            {validate.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            {t("scopeGraph.validateButton")}
          </Button>
        </div>
      )}

      {readOnly && (
        <p className="rounded-md border bg-muted/30 p-2 text-xs text-muted-foreground">{t("canvas.readOnlyHint")}</p>
      )}

      {validate.data && (
        <div className={`rounded-md border p-3 text-sm ${validate.data.valid ? "border-emerald-500/40 bg-emerald-500/5" : "border-destructive/40 bg-destructive/5"}`}>
          <p className="font-medium">{validate.data.valid ? t("scopeGraph.valid") : t("scopeGraph.invalid")}</p>
          {validate.data.issues.map((issue, i) => (
            <p key={i} className="mt-1 text-xs text-muted-foreground">{issue.severity}: {issue.message}</p>
          ))}
        </div>
      )}

      <div ref={wrapperRef} className="relative h-[600px] rounded-md border" onDragOver={onDragOver} onDrop={onDrop}>
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : nodes.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {t("scopeGraph.empty")}
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeDragStop={onNodeDragStop}
            onNodeDoubleClick={onNodeDoubleClick}
            onConnect={onConnect}
            onEdgeClick={onEdgeClick}
            onNodesDelete={onNodesDelete}
            onPaneClick={() => setSelectedEdge(null)}
            nodeTypes={nodeTypes}
            nodesDraggable={!readOnly}
            nodesConnectable={!readOnly}
            elementsSelectable={!readOnly}
            deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
            proOptions={{ hideAttribution: true }}
            fitView
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}

        {pendingCreate && (
          <Card
            className="absolute z-10 w-72 shadow-lg"
            style={{ left: Math.min(pendingCreate.screen.x, (wrapperRef.current?.clientWidth ?? 400) - 300), top: Math.min(pendingCreate.screen.y, (wrapperRef.current?.clientHeight ?? 400) - 260) }}
          >
            <CardContent className="space-y-3 pt-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">{t("addElement.title")}</p>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setPendingCreate(null)}><X className="h-3.5 w-3.5" /></Button>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("addElement.fields.type")}</Label>
                <Select
                  value={pendingCreate.element_type}
                  onChange={(e) => setPendingCreate({ ...pendingCreate, element_type: e.target.value })}
                >
                  {(FAMILY_TYPES[pendingCreate.family] ?? []).map((type) => <option key={type}>{type}</option>)}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("addElement.fields.name")}</Label>
                <Input
                  autoFocus
                  value={pendingCreate.name}
                  onChange={(e) => {
                    const name = e.target.value;
                    setPendingCreate((prev) => prev && ({
                      ...prev,
                      name,
                      stable_key: prev.stableKeyTouched ? prev.stable_key : `${prev.element_type}.${slugify(name)}`,
                    }));
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("addElement.fields.stableKey")}</Label>
                <Input
                  placeholder={t("addElement.stableKeyPlaceholder")}
                  value={pendingCreate.stable_key}
                  onChange={(e) => setPendingCreate({ ...pendingCreate, stable_key: e.target.value, stableKeyTouched: true })}
                />
              </div>
              <Button className="w-full" size="sm" disabled={!pendingCreate.name || !pendingCreate.stable_key || addElement.isPending} onClick={confirmCreate}>
                {addElement.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
                {t("addElement.button")}
              </Button>
            </CardContent>
          </Card>
        )}

        {pendingEdit && (
          <Card
            className="absolute z-10 w-72 shadow-lg"
            style={{ left: Math.min(pendingEdit.screen.x, (wrapperRef.current?.clientWidth ?? 400) - 300), top: Math.min(pendingEdit.screen.y, (wrapperRef.current?.clientHeight ?? 400) - 300) }}
          >
            <CardContent className="space-y-3 pt-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">{t("canvas.editTitle")}</p>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setPendingEdit(null)}><X className="h-3.5 w-3.5" /></Button>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("addElement.fields.layer")}</Label>
                <Select
                  value={pendingEdit.family}
                  onChange={(e) => {
                    const family = e.target.value;
                    setPendingEdit((prev) => prev && ({ ...prev, family, element_type: FAMILY_TYPES[family]?.[0] ?? "" }));
                  }}
                >
                  {FAMILY_ORDER.map((family) => <option key={family}>{family}</option>)}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("addElement.fields.type")}</Label>
                <Select
                  value={pendingEdit.element_type}
                  onChange={(e) => setPendingEdit({ ...pendingEdit, element_type: e.target.value })}
                >
                  {(FAMILY_TYPES[pendingEdit.family] ?? []).map((type) => <option key={type}>{type}</option>)}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("addElement.fields.name")}</Label>
                <Input
                  autoFocus
                  value={pendingEdit.name}
                  onChange={(e) => setPendingEdit({ ...pendingEdit, name: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("addElement.fields.stableKey")}</Label>
                <Input
                  value={pendingEdit.stable_key}
                  onChange={(e) => setPendingEdit({ ...pendingEdit, stable_key: e.target.value })}
                />
              </div>
              <div className="flex gap-2">
                <Button size="sm" className="flex-1" disabled={!pendingEdit.name || !pendingEdit.stable_key || updateElement.isPending} onClick={confirmEdit}>
                  {updateElement.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
                  {t("canvas.save")}
                </Button>
                <Button size="sm" variant="outline" onClick={deleteEditingElement} disabled={removeElement.isPending} title={t("canvas.removeElement")}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {selectedEdge && (
          <Card
            className="absolute z-10 w-56 shadow-lg"
            style={{ left: Math.min(selectedEdge.screen.x, (wrapperRef.current?.clientWidth ?? 300) - 240), top: Math.min(selectedEdge.screen.y, (wrapperRef.current?.clientHeight ?? 300) - 140) }}
          >
            <CardContent className="space-y-3 pt-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">{t("connectElements.relationType")}</p>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setSelectedEdge(null)}><X className="h-3.5 w-3.5" /></Button>
              </div>
              <Select
                value={selectedEdge.relation_type}
                onChange={(e) => setSelectedEdge({ ...selectedEdge, relation_type: e.target.value })}
              >
                {RELATION_TYPES.map((type) => <option key={type}>{type}</option>)}
              </Select>
              <div className="flex gap-2">
                <Button size="sm" className="flex-1" onClick={confirmRelationType} disabled={deleteRelation.isPending || addRelation.isPending}>
                  {t("connectElements.button")}
                </Button>
                <Button size="sm" variant="outline" onClick={removeSelectedEdge} disabled={deleteRelation.isPending}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

export function SystemMapCanvas(props: SystemMapCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
