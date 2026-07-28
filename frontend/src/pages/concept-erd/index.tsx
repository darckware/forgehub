import { useState } from "react";
import { Share2, Sparkles, Database, Table, Key, FileText, CheckCircle2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface DatabaseTableSpec {
  name: string;
  description: string;
  columnsCount: number;
  columns: { name: string; type: string; isPk?: boolean; isFk?: boolean; nullable?: boolean }[];
}

const MOCK_ERD_TABLES: DatabaseTableSpec[] = [
  {
    name: "users",
    description: "Usuários do sistema e dados de autenticação",
    columnsCount: 5,
    columns: [
      { name: "id", type: "UUID", isPk: true },
      { name: "email", type: "VARCHAR(255)", nullable: false },
      { name: "password_hash", type: "VARCHAR(255)", nullable: false },
      { name: "full_name", type: "VARCHAR(255)", nullable: true },
      { name: "created_at", type: "TIMESTAMPTZ", nullable: false },
    ],
  },
  {
    name: "projects",
    description: "Projetos de desenvolvimento vinculados às aplicações",
    columnsCount: 6,
    columns: [
      { name: "id", type: "UUID", isPk: true },
      { name: "application_id", type: "UUID", isFk: true, nullable: false },
      { name: "name", type: "VARCHAR(255)", nullable: false },
      { name: "type", type: "VARCHAR(50)", nullable: false },
      { name: "status", type: "VARCHAR(50)", nullable: false },
      { name: "created_at", type: "TIMESTAMPTZ", nullable: false },
    ],
  },
  {
    name: "project_plans",
    description: "Planejamentos das sprints e lotes de execução",
    columnsCount: 7,
    columns: [
      { name: "id", type: "UUID", isPk: true },
      { name: "project_id", type: "UUID", isFk: true, nullable: false },
      { name: "name", type: "VARCHAR(255)", nullable: false },
      { name: "start_date", type: "DATE", nullable: true },
      { name: "end_date", type: "DATE", nullable: true },
      { name: "actual_start_date", type: "DATE", nullable: true },
      { name: "actual_end_date", type: "DATE", nullable: true },
    ],
  },
];

export default function ConceptErdViewerPage() {
  const [selectedTable, setSelectedTable] = useState<DatabaseTableSpec>(MOCK_ERD_TABLES[0]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Share2 className="h-6 w-6 text-primary" />
            Diagrama ERD & Modelagem do Banco de Dados
          </h1>
          <p className="text-sm text-muted-foreground">
            Visualizador de modelagem relacional (gerado autonomamente pela IA na Fase de Conceito).
          </p>
        </div>
        <Badge variant="outline" className="flex items-center gap-1 border-primary/30 text-primary">
          <Sparkles className="h-3.5 w-3.5" />
          Fase 2: Inspeção do Banco
        </Badge>
      </div>

      <div className="grid gap-6 md:grid-cols-[280px_1fr]">
        {/* Lista de Tabelas Geradas */}
        <Card>
          <CardHeader className="p-4">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Database className="h-4 w-4" />
              Telas & Tabelas ({MOCK_ERD_TABLES.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-2 space-y-1">
            {MOCK_ERD_TABLES.map((table) => (
              <button
                key={table.name}
                type="button"
                onClick={() => setSelectedTable(table)}
                className={`flex w-full flex-col items-start gap-1 rounded-md p-3 text-left transition-colors ${
                  selectedTable.name === table.name ? "bg-primary/10 border border-primary/30" : "hover:bg-accent"
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="text-xs font-mono font-semibold text-primary">{table.name}</span>
                  <Badge variant="secondary" className="text-[10px]">
                    {table.columnsCount} colunas
                  </Badge>
                </div>
                <span className="text-[11px] text-muted-foreground line-clamp-1">{table.description}</span>
              </button>
            ))}
          </CardContent>
        </Card>

        {/* Inspeção de Colunas e Diagrama Visual */}
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-bold font-mono flex items-center gap-2">
                  <Table className="h-4 w-4 text-primary" />
                  Tabela: {selectedTable.name}
                </CardTitle>
                <Badge variant="outline" className="text-xs">
                  {selectedTable.columnsCount} colunas definidas
                </Badge>
              </div>
              <CardDescription className="text-xs">{selectedTable.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="rounded-md border">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/50 border-b font-semibold text-muted-foreground">
                    <tr>
                      <th className="p-2.5">Coluna</th>
                      <th className="p-2.5">Tipo de Dado</th>
                      <th className="p-2.5">Atributos</th>
                      <th className="p-2.5">Nulo?</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {selectedTable.columns.map((col) => (
                      <tr key={col.name} className="hover:bg-muted/20">
                        <td className="p-2.5 font-mono font-medium flex items-center gap-1.5">
                          {col.isPk && <Key className="h-3 w-3 text-amber-500" />}
                          {col.isFk && <Key className="h-3 w-3 text-sky-500" />}
                          {col.name}
                        </td>
                        <td className="p-2.5 font-mono text-muted-foreground">{col.type}</td>
                        <td className="p-2.5">
                          {col.isPk && <Badge className="text-[10px] bg-amber-500/10 text-amber-600 border-amber-500/30">PK</Badge>}
                          {col.isFk && <Badge className="text-[10px] bg-sky-500/10 text-sky-600 border-sky-500/30">FK</Badge>}
                        </td>
                        <td className="p-2.5 text-muted-foreground">{col.nullable ? "Sim" : "Não"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Diagrama Visual Mermaid Representativo */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <FileText className="h-4 w-4 text-primary" />
                Especificação em Mermaid (DATABASE_SPEC.md)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="rounded-md bg-muted p-4 font-mono text-xs overflow-x-auto border">
{`erDiagram
    users ||--o{ projects : "cria"
    applications ||--|{ projects : "engloba"
    projects ||--|{ project_plans : "possui"

    users {
        uuid id PK
        string email
        string password_hash
    }

    projects {
        uuid id PK
        uuid application_id FK
        string name
        string type
    }`}
              </pre>
              <div className="flex justify-end mt-4">
                <Button size="sm" className="text-xs flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Aprovar Modelagem do Banco de Dados
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
