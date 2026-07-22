import type { SchemaColumn, SchemaOut, SchemaTable } from "@/hooks/useDatabase";

/** Shared by the Database page (live Postgres introspection) and the System
 * Map's Entities view "DATA-SPEC preview" (Conception's table/field
 * elements) -- same Mermaid erDiagram renderer either way, just fed a
 * different SchemaOut source. Moved out of database/DiagramPage.tsx so
 * neither caller has to duplicate it. */
export function buildMermaidERD(schema: SchemaOut, selectedTables: string[] | "all"): string {
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

export async function renderMermaid(definition: string, container: HTMLDivElement) {
  const mod = await import("mermaid");
  const mermaid = mod.default;
  mermaid.initialize({
    startOnLoad: false,
    theme: document.documentElement.classList.contains("dark") ? "dark" : "default",
    er: { diagramPadding: 20, layoutDirection: "LR", minEntityWidth: 100, useMaxWidth: false },
    securityLevel: "loose",
  });
  const id = "erd-" + Date.now();
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

export type { SchemaColumn, SchemaOut, SchemaTable };
