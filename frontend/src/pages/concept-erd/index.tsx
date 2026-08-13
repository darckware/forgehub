import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Database, Key, Share2, Table } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { buildMermaidERD, renderMermaid, type SchemaTable } from "@/lib/mermaidErd";
import { buildErdSchemaFromBlueprint } from "@/pages/system-map/dataSpec";
import { useProjects } from "@/hooks/useProject";
import { useBlueprintGraph, useProjectScopes, useValidateBlueprint } from "@/hooks/useSystemScope";
import { useScreens } from "@/hooks/useScreenRegistry";

export default function ConceptErdViewerPage() {
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const scopes = useProjectScopes(projectId);
  const [scopeId, setScopeId] = useState("");
  useEffect(() => setScopeId(scopes.data?.[0]?.id || ""), [scopes.data]);

  // Screens and their derived table/field elements all live in the same
  // "screens revision" (see api/routes/system_scope.py) -- any screen's
  // revision id points at it, so we don't need a dedicated lookup endpoint.
  const screens = useScreens(scopeId);
  const revisionId = screens.data?.[0]?.revision.blueprint_revision_id ?? null;
  const graph = useBlueprintGraph(revisionId);
  const validate = useValidateBlueprint();

  const schema = graph.data ? buildErdSchemaFromBlueprint(graph.data) : null;
  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null);
  useEffect(() => setSelectedTable(schema?.tables[0] ?? null), [schema]);

  const diagramRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!schema || !diagramRef.current) return;
    if (schema.tables.length === 0) { diagramRef.current.innerHTML = ""; return; }
    renderMermaid(buildMermaidERD(schema, "all"), diagramRef.current).catch(() => {});
  }, [schema]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><Share2 className="h-6 w-6" />Modelagem de Banco (Concepção)</h1>
          <p className="text-sm text-muted-foreground">
            Modelo relacional derivado das telas cadastradas em Telas & Regras de Negócio -- proposta editável, não introspecção do banco físico.
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="grid gap-4 pt-6 md:grid-cols-2">
          <div>
            <Label>Projeto</Label>
            <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Selecione um projeto...</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>
          <div>
            <Label>Escopo</Label>
            <Select value={scopeId} onChange={(e) => setScopeId(e.target.value)} disabled={!projectId}>
              <option value="">Selecione um escopo...</option>
              {scopes.data?.map((s) => <option key={s.id} value={s.id}>Revisão {s.revision} · {s.status}</option>)}
            </Select>
          </div>
        </CardContent>
      </Card>

      {!schema || schema.tables.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            {scopeId
              ? <>Nenhuma tabela derivada ainda. Cadastre telas com atributos e rode "Derivar Banco de Dados" em <Link to="/screen-inspector" className="text-primary hover:underline">Telas & Regras de Negócio</Link>.</>
              : "Selecione um projeto e um escopo."}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-[280px_1fr]">
          <Card>
            <CardHeader className="p-4">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Database className="h-4 w-4" />
                Tabelas ({schema.tables.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="p-2 space-y-1">
              {schema.tables.map((table) => (
                <button
                  key={table.name}
                  type="button"
                  onClick={() => setSelectedTable(table)}
                  className={`flex w-full flex-col items-start gap-1 rounded-md p-3 text-left transition-colors ${selectedTable?.name === table.name ? "bg-primary/10 border border-primary/30" : "hover:bg-accent"}`}
                >
                  <span className="text-xs font-mono font-semibold text-primary">{table.name}</span>
                  <Badge variant="secondary" className="text-[10px]">{table.columns.length} colunas</Badge>
                </button>
              ))}
            </CardContent>
          </Card>

          <div className="space-y-6">
            {selectedTable && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-bold font-mono flex items-center gap-2">
                    <Table className="h-4 w-4 text-primary" />
                    Tabela: {selectedTable.name}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="rounded-md border">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-muted/50 border-b font-semibold text-muted-foreground">
                        <tr><th className="p-2.5">Coluna</th><th className="p-2.5">Tipo</th><th className="p-2.5">Atributos</th></tr>
                      </thead>
                      <tbody className="divide-y">
                        {selectedTable.columns.map((col) => (
                          <tr key={col.name} className="hover:bg-muted/20">
                            <td className="p-2.5 font-mono font-medium flex items-center gap-1.5">
                              {(col.pk || col.fk_to) && <Key className="h-3 w-3 text-amber-500" />}
                              {col.name}
                            </td>
                            <td className="p-2.5 font-mono text-muted-foreground">{col.type}</td>
                            <td className="p-2.5">
                              {col.pk && <Badge className="text-[10px] bg-amber-500/10 text-amber-600 border-amber-500/30">PK</Badge>}
                              {col.fk_to && <Badge className="text-[10px] bg-sky-500/10 text-sky-600 border-sky-500/30">FK → {col.fk_to}</Badge>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-sm font-semibold">Diagrama</CardTitle></CardHeader>
              <CardContent>
                <div ref={diagramRef} className="w-full overflow-auto" />
                <div className="flex justify-end mt-4">
                  <Button
                    size="sm" className="text-xs flex items-center gap-1.5"
                    disabled={!revisionId || validate.isPending}
                    onClick={() => revisionId && validate.mutate(revisionId)}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Aprovar Modelagem do Banco de Dados
                  </Button>
                </div>
                {validate.data && (
                  <p className={`mt-2 text-xs ${validate.data.valid ? "text-emerald-600" : "text-destructive"}`}>
                    {validate.data.valid ? "Modelagem validada." : `${validate.data.issues.length} problema(s) encontrado(s).`}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
