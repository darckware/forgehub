import type { BlueprintGraph } from "@/hooks/useSystemScope";
import type { SchemaColumn, SchemaOut, SchemaTable } from "@/lib/mermaidErd";

/** Column-level detail for a `field` element, mirroring the screen_spec
 * pattern from the Screens/Navigation view: a small JSON block on the
 * element's spec_snapshot instead of new DB columns. `fk_ref_table` holds
 * the target table's *name* (not id) since it's meant to be read straight
 * off the field's own revision snapshot without a second lookup. */
export interface FieldSpec {
  sql_type: string;
  is_pk: boolean;
  is_fk: boolean;
  fk_ref_table: string;
}
export const EMPTY_FIELD_SPEC: FieldSpec = { sql_type: "", is_pk: false, is_fk: false, fk_ref_table: "" };

// stack/04-DATABASE-MODELING-AND-NAMING-STANDARD.md: DB identifiers are
// lower_snake_case.
const SNAKE_CASE_RE = /^[a-z][a-z0-9_]*$/;

/** Maps the Entities view's `table`/`field` elements (family="data") into
 * the same SchemaOut shape the Database page's live-introspected schema
 * uses, so the existing buildMermaidERD/renderMermaid pipeline can render
 * either one unchanged -- the entity diagram doubles as an initial
 * DATA-SPEC draft without a new renderer.
 *
 * Convention (no new relation types, no schema change): a `table` element
 * "contains" its `field` children (same relation already used for other
 * parent/child groupings on this canvas); a `depends_on`/`persists_as`
 * relation directly between two `table` elements becomes a foreign key,
 * with the FK column name defaulting to `<ref_table>_id` when the field
 * itself hasn't been modeled with an explicit fk field_spec. */
export function buildErdSchemaFromBlueprint(graph: BlueprintGraph): SchemaOut {
  const elements = graph.elements;
  const tables = elements.filter((item) => item.element.family === "data" && item.element.element_type === "table");
  const tableIds = new Set(tables.map((item) => item.element.id));
  const nameById = new Map(elements.map((item) => [item.element.id, item.element.name] as const));

  const fieldsByTable = new Map<string, typeof elements>();
  for (const rel of graph.relations) {
    if (rel.relation_type !== "contains") continue;
    const child = elements.find((item) => item.element.id === rel.to_element_id);
    if (!tableIds.has(rel.from_element_id) || !child || child.element.element_type !== "field") continue;
    const list = fieldsByTable.get(rel.from_element_id) ?? [];
    list.push(child);
    fieldsByTable.set(rel.from_element_id, list);
  }

  const tableFkRelations = graph.relations.filter((rel) =>
    (rel.relation_type === "depends_on" || rel.relation_type === "persists_as") &&
    tableIds.has(rel.from_element_id) && tableIds.has(rel.to_element_id)
  );

  const schemaTables: SchemaTable[] = tables.map((tableItem) => {
    const fields = fieldsByTable.get(tableItem.element.id) ?? [];
    const columns: SchemaColumn[] = fields.length
      ? fields.map((field) => {
          const spec = (field.revision.spec_snapshot?.field_spec ?? {}) as Partial<FieldSpec>;
          return {
            name: field.element.name,
            type: spec.sql_type || "text",
            nullable: true,
            pk: Boolean(spec.is_pk),
            fk_to: spec.is_fk && spec.fk_ref_table ? spec.fk_ref_table : null,
          };
        })
      // A table with no modeled columns yet still shows up in the preview
      // (with just an inferred id PK) so it's visible before it's fully
      // fleshed out -- consistent with the diagram being a *draft*.
      : [{ name: "id", type: "uuid", nullable: false, pk: true, fk_to: null }];

    const foreign_keys = tableFkRelations
      .filter((rel) => rel.from_element_id === tableItem.element.id)
      .map((rel) => {
        const refTable = nameById.get(rel.to_element_id) ?? "?";
        return { column: `${refTable.toLowerCase()}_id`, ref_table: refTable, ref_column: "id" };
      });

    return { name: tableItem.element.name, columns, foreign_keys };
  });

  return { tables: schemaTables };
}

/** Naming-convention warnings (never blocking) against
 * stack/04-DATABASE-MODELING-AND-NAMING-STANDARD.md -- table/field names
 * should already be lower_snake_case before this becomes a real migration
 * in a later phase. */
export function lintDataSpecNaming(graph: BlueprintGraph): string[] {
  const issues: string[] = [];
  for (const item of graph.elements) {
    if (item.element.family !== "data") continue;
    if (!["table", "field"].includes(item.element.element_type)) continue;
    if (!SNAKE_CASE_RE.test(item.element.name)) {
      issues.push(`"${item.element.name}" deveria estar em lower_snake_case (padrão de nomenclatura de banco).`);
    }
  }
  return issues;
}
