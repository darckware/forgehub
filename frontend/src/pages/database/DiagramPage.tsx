import { useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronRight,
  Download,
  Layers,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useDatabaseSchema } from "@/hooks/useDatabase";
import type { SchemaOut } from "@/hooks/useDatabase";
import { useSchema } from "./SchemaContext";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DiagramConfig {
  id: string;
  name: string;
  tables: string[] | "all";  // "all" = full schema
}

const STORAGE_KEY = "forgehub-db-diagrams";

const DEFAULT_DIAGRAMS: DiagramConfig[] = [
  { id: "all", name: "Full Schema", tables: "all" },
];

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

function loadDiagrams(): DiagramConfig[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_DIAGRAMS;
    const parsed: DiagramConfig[] = JSON.parse(raw);
    // always keep "all" as first entry
    if (!parsed.find((d) => d.id === "all")) parsed.unshift(DEFAULT_DIAGRAMS[0]);
    return parsed;
  } catch {
    return DEFAULT_DIAGRAMS;
  }
}

function saveDiagrams(diagrams: DiagramConfig[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(diagrams));
}

// ---------------------------------------------------------------------------
// Mermaid helpers
// ---------------------------------------------------------------------------

function buildMermaidERD(schema: SchemaOut, selectedTables: string[] | "all"): string {
  const tableSet = selectedTables === "all"
    ? new Set(schema.tables.map((t) => t.name))
    : new Set(selectedTables);

  const tables = schema.tables.filter((t) => tableSet.has(t.name));
  const lines: string[] = ["erDiagram"];

  for (const table of tables) {
    lines.push(`  ${table.name} {`);
    for (const col of table.columns) {
      const type = col.type.replace(/\s+/g, "_").replace(/[^a-zA-Z0-9_]/g, "") || "text";
      const flags = [col.pk ? "PK" : "", col.fk_to ? "FK" : ""].filter(Boolean).join(",");
      lines.push(`    ${type} ${col.name}${flags ? ` "${flags}"` : ""}`);
    }
    lines.push("  }");
  }

  // Only draw FK lines when BOTH endpoints are in the selected set
  for (const table of tables) {
    for (const fk of table.foreign_keys) {
      if (tableSet.has(fk.ref_table)) {
        lines.push(`  ${table.name} }o--|| ${fk.ref_table} : "${fk.column}"`);
      }
    }
  }

  return lines.join("\n");
}

async function renderMermaid(definition: string, container: HTMLDivElement) {
  const mod = await import("mermaid");
  const mermaid = mod.default;
  mermaid.initialize({
    startOnLoad: false,
    theme: document.documentElement.classList.contains("dark") ? "dark" : "default",
    er: { diagramPadding: 20, layoutDirection: "LR", minEntityWidth: 100, useMaxWidth: false },
    securityLevel: "loose",
  });
  const id = "db-erd-" + Date.now();
  const { svg } = await mermaid.render(id, definition);
  container.innerHTML = svg;
  const svgEl = container.querySelector("svg");
  if (svgEl) {
    svgEl.removeAttribute("width");
    svgEl.removeAttribute("height");
    svgEl.style.width = "100%";
    svgEl.style.height = "auto";
  }
}

// ---------------------------------------------------------------------------
// Table selector panel (used when editing)
// ---------------------------------------------------------------------------

function TableSelector({
  allTables,
  selected,
  onChange,
}: {
  allTables: string[];
  selected: string[];
  onChange: (t: string[]) => void;
}) {
  const [search, setSearch] = useState("");
  const filtered = allTables.filter((t) => t.toLowerCase().includes(search.toLowerCase()));
  const toggle = (t: string) =>
    onChange(selected.includes(t) ? selected.filter((s) => s !== t) : [...selected, t]);

  return (
    <div className="flex flex-col gap-2 h-full min-h-0">
      <div className="relative shrink-0">
        <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search table..."
          className="h-7 pl-6 text-xs"
        />
      </div>
      <div className="flex gap-1 shrink-0">
        <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={() => onChange(allTables)}>
          All
        </Button>
        <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={() => onChange([])}>
          None
        </Button>
        <span className="ml-auto text-[10px] text-muted-foreground self-center">{selected.length}/{allTables.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-0.5 min-h-0">
        {filtered.map((t) => {
          const isSelected = selected.includes(t);
          return (
            <button
              key={t}
              type="button"
              onClick={() => toggle(t)}
              className={cn(
                "w-full flex items-center gap-2 px-2 py-1 rounded text-xs text-left transition-colors hover:bg-accent",
                isSelected && "bg-accent/60"
              )}
            >
              <div className={cn(
                "h-3.5 w-3.5 rounded border shrink-0 flex items-center justify-center",
                isSelected ? "bg-primary border-primary" : "border-muted-foreground/40"
              )}>
                {isSelected && <Check className="h-2.5 w-2.5 text-primary-foreground" />}
              </div>
              <span className="font-mono truncate">{t}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DiagramPage() {
  const { schema: selectedSchema, instance, db } = useSchema();
  const { data: schema, isLoading: schemaLoading, refetch, isFetching } = useDatabaseSchema(selectedSchema, instance, db);

  const [diagrams, setDiagrams] = useState<DiagramConfig[]>(loadDiagrams);
  const [activeId, setActiveId] = useState<string>("all");
  const [editing, setEditing] = useState<string | null>(null); // diagram id being edited
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [editTables, setEditTables] = useState<string[]>([]);
  const [zoom, setZoom] = useState(0.75);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);

  const svgRef = useRef<HTMLDivElement>(null);
  const activeDiagram = diagrams.find((d) => d.id === activeId) ?? diagrams[0];
  const allTables = schema?.tables.map((t) => t.name) ?? [];

  // Persist on change
  useEffect(() => { saveDiagrams(diagrams); }, [diagrams]);

  // Re-render when active diagram or schema changes
  useEffect(() => {
    if (!schema || !svgRef.current || editing || creating) return;
    setRenderError(null);
    setRendering(true);
    const definition = buildMermaidERD(schema, activeDiagram.tables);
    renderMermaid(definition, svgRef.current)
      .then(() => setRendering(false))
      .catch((e) => { setRenderError(String(e)); setRendering(false); });
  }, [schema, activeId, editing, creating, activeDiagram]);

  const startCreate = () => {
    setCreating(true);
    setEditing(null);
    setNewName("");
    setEditTables([]);
  };

  const startEdit = (d: DiagramConfig) => {
    setEditing(d.id);
    setCreating(false);
    setNewName(d.name);
    setEditTables(d.tables === "all" ? allTables : [...d.tables]);
  };

  const cancelEdit = () => { setEditing(null); setCreating(false); };

  const saveDiagram = () => {
    if (creating) {
      const id = `diag-${Date.now()}`;
      const next = [...diagrams, { id, name: newName || "New Diagram", tables: editTables }];
      setDiagrams(next);
      setActiveId(id);
    } else if (editing) {
      setDiagrams((prev) => prev.map((d) => d.id === editing
        ? { ...d, name: newName || d.name, tables: editTables } : d));
    }
    cancelEdit();
  };

  const deleteDiagram = (id: string) => {
    if (id === "all") return;
    setDiagrams((prev) => prev.filter((d) => d.id !== id));
    if (activeId === id) setActiveId("all");
  };

  const handleDownload = () => {
    const svg = svgRef.current?.querySelector("svg");
    if (!svg) return;
    const blob = new Blob([svg.outerHTML], { type: "image/svg+xml" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob),
      download: `${activeDiagram.name.replace(/\s+/g, "-")}.svg`,
    });
    a.click();
  };

  const isEditMode = editing !== null || creating;
  const editDiagram = editing ? diagrams.find((d) => d.id === editing) : null;

  return (
    <div className="flex h-full min-h-0">
      {/* Left panel — diagram list */}
      <div className="w-56 shrink-0 border-r border-border flex flex-col h-full bg-card">
        <div className="p-3 border-b border-border">
          <Button size="sm" className="w-full gap-1.5 text-xs h-7" onClick={startCreate}>
            <Plus className="h-3.5 w-3.5" /> New Diagram
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto py-1">
          {diagrams.map((d) => {
            const isActive = d.id === activeId && !isEditMode;
            const isBeingEdited = editing === d.id;
            const count = d.tables === "all" ? allTables.length : d.tables.length;
            return (
              <div
                key={d.id}
                className={cn(
                  "group flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors hover:bg-accent",
                  isActive && "bg-accent",
                  isBeingEdited && "bg-primary/10"
                )}
                onClick={() => { if (!isBeingEdited) { setActiveId(d.id); cancelEdit(); } }}
              >
                <Layers className={cn("h-3.5 w-3.5 shrink-0", isActive ? "text-primary" : "text-muted-foreground")} />
                <div className="flex-1 min-w-0">
                  <p className={cn("text-xs truncate", isActive && "font-medium")}>{d.name}</p>
                  <p className="text-[10px] text-muted-foreground">{count} table(s)</p>
                </div>
                {isActive && <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />}
                {d.id !== "all" && (
                  <div className="hidden group-hover:flex items-center gap-0.5">
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); startEdit(d); }}
                      className="h-5 w-5 flex items-center justify-center rounded hover:bg-muted text-muted-foreground"
                    >
                      <Pencil className="h-2.5 w-2.5" />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); deleteDiagram(d.id); }}
                      className="h-5 w-5 flex items-center justify-center rounded hover:bg-muted text-destructive"
                    >
                      <Trash2 className="h-2.5 w-2.5" />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Main area */}
      <div className="flex-1 min-w-0 flex flex-col h-full min-h-0">
        {isEditMode ? (
          /* ── Editor mode ── */
          <div className="flex flex-col h-full min-h-0">
            {/* Edit header */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-border shrink-0">
              <div className="flex-1">
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={creating ? "Diagram name..." : editDiagram?.name}
                  className="h-8 max-w-xs text-sm font-medium"
                  autoFocus
                  onKeyDown={(e) => e.key === "Enter" && saveDiagram()}
                />
              </div>
              <span className="text-xs text-muted-foreground">{editTables.length} table(s) selected</span>
              <Button size="sm" variant="ghost" onClick={cancelEdit} className="h-7 gap-1 text-xs">
                <X className="h-3.5 w-3.5" /> Cancel
              </Button>
              <Button size="sm" onClick={saveDiagram} className="h-7 gap-1 text-xs" disabled={!newName.trim()}>
                <Check className="h-3.5 w-3.5" /> Save
              </Button>
            </div>
            {/* Table selector + live preview side-by-side */}
            <div className="flex flex-1 min-h-0 gap-0">
              <div className="w-64 shrink-0 border-r border-border p-3 flex flex-col min-h-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Select Tables</p>
                {schemaLoading ? (
                  <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading...
                  </div>
                ) : (
                  <TableSelector allTables={allTables} selected={editTables} onChange={setEditTables} />
                )}
              </div>
              {/* Live preview of selection */}
              <div className="flex-1 min-w-0 overflow-auto p-4 bg-muted/10">
                {editTables.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                    Select at least one table to preview the diagram
                  </div>
                ) : schema ? (
                  <DiagramPreview schema={schema} tables={editTables} />
                ) : null}
              </div>
            </div>
          </div>
        ) : (
          /* ── View mode ── */
          <>
            <div className="flex items-center gap-2 px-4 py-2 border-b border-border shrink-0">
              <span className="text-xs font-medium flex-1">
                {activeDiagram.name}
                <Badge variant="outline" className="ml-2 text-[10px]">
                  {activeDiagram.tables === "all" ? allTables.length : activeDiagram.tables.length} tables
                </Badge>
              </span>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setZoom((z) => Math.max(0.2, z - 0.15))} title="Zoom out">
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
              <span className="text-xs text-muted-foreground w-10 text-center">{Math.round(zoom * 100)}%</span>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setZoom((z) => Math.min(2, z + 0.15))} title="Zoom in">
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 gap-1 text-xs" onClick={() => refetch()} disabled={isFetching}>
                <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
              </Button>
              {activeDiagram.id !== "all" && (
                <Button size="sm" variant="ghost" className="h-7 px-2 gap-1 text-xs" onClick={() => startEdit(activeDiagram)}>
                  <Pencil className="h-3.5 w-3.5" /> Edit
                </Button>
              )}
              <Button size="sm" variant="outline" className="h-7 px-2 gap-1 text-xs" onClick={handleDownload}>
                <Download className="h-3.5 w-3.5" /> SVG
              </Button>
            </div>

            <div className="flex-1 min-h-0 overflow-auto bg-muted/10 relative p-4">
              {schemaLoading ? (
                <div className="flex items-center justify-center h-full gap-2 text-muted-foreground">
                  <Loader2 className="h-5 w-5 animate-spin" /> Loading schema...
                </div>
              ) : renderError ? (
                <div className="flex items-center justify-center h-full">
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 max-w-lg">
                    <p className="text-sm text-destructive font-medium mb-1">Render error</p>
                    <pre className="text-xs text-muted-foreground whitespace-pre-wrap">{renderError}</pre>
                  </div>
                </div>
              ) : (
                <>
                  {rendering && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/40 z-10">
                      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                  )}
                  <div
                    ref={svgRef}
                    style={{ transform: `scale(${zoom})`, transformOrigin: "top left", transition: "transform 0.15s" }}
                    className="w-full"
                  />
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live preview component (renders a small diagram for the editor)
// ---------------------------------------------------------------------------

function DiagramPreview({ schema, tables }: { schema: SchemaOut; tables: string[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!ref.current || tables.length === 0) return;
    setErr(null);
    const definition = buildMermaidERD(schema, tables);
    renderMermaid(definition, ref.current).catch((e) => setErr(String(e)));
  }, [schema, tables]);

  if (err) {
    return <p className="text-xs text-destructive">{err}</p>;
  }
  return <div ref={ref} className="w-full" />;
}
