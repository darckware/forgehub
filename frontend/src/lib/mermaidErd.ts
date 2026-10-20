import type { SchemaColumn, SchemaOut, SchemaTable } from "@/hooks/useDatabase";

/** Shared by the Database page (live Postgres introspection) and the System
 * Map's Entities view "DATA-SPEC preview" (Conception's table/field
 * elements) -- same Mermaid erDiagram renderer either way, just fed a
 * different SchemaOut source. Moved out of database/DiagramPage.tsx so
 * neither caller has to duplicate it. */
export interface BuildErdOptions {
  /** Emit entities as empty boxes (name + relations only, no attribute rows).
   * Mermaid's ER layout measures every attribute row through the DOM, so cost
   * scales with total column count, not table count: the live `company` schema
   * (102 tables / 1036 columns / 154 FKs) takes ~12s and yields a ~2.9 MB SVG
   * with columns, vs ~1.8s and ~265 KB without. `mermaid.render` blocks the main
   * thread, so that difference is the difference between a slow screen and a
   * frozen tab -- see DiagramPage.tsx's AUTO_FULL_TABLE_LIMIT. */
  compact?: boolean;
}

export function buildMermaidERD(
  schema: SchemaOut,
  selectedTables: string[] | "all",
  options: BuildErdOptions = {},
): string {
  const tableSet = selectedTables === "all"
    ? new Set(schema.tables.map((t) => t.name))
    : new Set(selectedTables);

  const tables = schema.tables.filter((t) => tableSet.has(t.name));
  const lines: string[] = ["erDiagram"];

  for (const table of tables) {
    lines.push(`  ${table.name} {`);
    if (!options.compact) {
      for (const col of table.columns) {
        const type = col.type.replace(/\s+/g, "_").replace(/[^a-zA-Z0-9_]/g, "") || "text";
        const flags = [col.pk ? "PK" : "", col.fk_to ? "FK" : ""].filter(Boolean).join(",");
        lines.push(`    ${type} ${col.name}${flags ? ` "${flags}"` : ""}`);
      }
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

/** Monotonic so two renders started in the same millisecond can't collide on
 * mermaid's temporary DOM id (Date.now() alone did). */
let renderIdSeq = 0;

/** Produce the SVG markup without touching any container. Callers that can be
 * superseded mid-flight (diagram switching, editor preview) should use this and
 * inject via `injectMermaidSvg` only after checking the result is still current
 * -- a large ERD takes seconds, so a stale promise resolving last would
 * otherwise overwrite the diagram the user actually asked for. */
export async function renderMermaidToString(definition: string): Promise<string> {
  const mod = await import("mermaid");
  const mermaid = mod.default;
  mermaid.initialize({
    startOnLoad: false,
    theme: document.documentElement.classList.contains("dark") ? "dark" : "default",
    er: { diagramPadding: 20, layoutDirection: "LR", minEntityWidth: 100, useMaxWidth: false },
    securityLevel: "loose",
  });
  const id = `erd-${Date.now()}-${++renderIdSeq}`;
  const { svg } = await mermaid.render(id, definition);
  return svg;
}

export function injectMermaidSvg(svg: string, container: HTMLDivElement) {
  container.innerHTML = svg;
  const svgEl = container.querySelector("svg");
  if (svgEl) {
    svgEl.removeAttribute("width");
    svgEl.removeAttribute("height");
    svgEl.style.width = "100%";
    svgEl.style.height = "auto";
  }
}

export async function renderMermaid(definition: string, container: HTMLDivElement) {
  injectMermaidSvg(await renderMermaidToString(definition), container);
}

export type { SchemaColumn, SchemaOut, SchemaTable };
