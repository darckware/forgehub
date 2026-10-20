import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CheckCircle2,
  Database,
  Key,
  Share2,
  Table as TableIcon,
  Plus,
  Trash2,
  Loader2,
  Wand2,
  FileText,
  Layers,
  Sparkles,
  Copy,
  Check,
  Code,
  Eye,
  Columns,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Markdown } from "@/components/Markdown";
import { buildMermaidERD, renderMermaid } from "@/lib/mermaidErd";
import { buildErdSchemaFromBlueprint, lintDataSpecNaming } from "@/pages/system-map/dataSpec";
import { useProjects } from "@/hooks/useProject";
import {
  useBlueprintGraph,
  useEnsureProjectScope,
  useProjectScopes,
  useValidateBlueprint,
  useCreateTable,
  useAddTableColumn,
  useDeleteTable,
} from "@/hooks/useSystemScope";
import {
  useDatabaseDoc,
  useDeriveDatabase,
  useSaveDatabaseDoc,
  useScreens,
} from "@/hooks/useScreenRegistry";

const SQL_TYPES = [
  "uuid",
  "text",
  "varchar",
  "integer",
  "bigint",
  "boolean",
  "timestamptz",
  "numeric",
  "jsonb",
  "float",
];

export default function ConceptErdViewerPage() {
  const { t, i18n } = useTranslation(["conceptErd", "screenInspector"]);
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const scopes = useProjectScopes(projectId);
  const ensureScope = useEnsureProjectScope();
  const [scopeId, setScopeId] = useState("");
  useEffect(() => setScopeId(scopes.data?.[0]?.id || ""), [scopes.data]);

  const activeProject = projects.data?.find((p) => p.id === projectId);
  const screens = useScreens(scopeId);
  const deriveDatabase = useDeriveDatabase();

  // Tabs state: "modeling" vs "markdown"
  const [mainTab, setMainTab] = useState("modeling");

  // Screens revision ID
  const screensRevisionId = screens.data?.[0]?.revision.blueprint_revision_id ?? null;
  const graph = useBlueprintGraph(screensRevisionId);
  const validate = useValidateBlueprint();

  const createTable = useCreateTable();
  const addColumn = useAddTableColumn();
  const deleteTable = useDeleteTable();

  // Selected table state
  const schema = graph.data ? buildErdSchemaFromBlueprint(graph.data) : null;
  const namingIssues = graph.data ? lintDataSpecNaming(graph.data) : [];
  const [selectedTableName, setSelectedTableName] = useState<string | null>(null);

  useEffect(() => {
    if (schema?.tables && schema.tables.length > 0) {
      if (!schema.tables.some((t) => t.name === selectedTableName)) {
        setSelectedTableName(schema.tables[0].name);
      }
    } else {
      setSelectedTableName(null);
    }
  }, [schema, selectedTableName]);

  const selectedTable = schema?.tables.find((t) => t.name === selectedTableName) ?? null;

  const selectedTableElement = useMemo(() => {
    if (!graph.data || !selectedTableName) return null;
    return graph.data.elements.find(
      (e) => e.element.family === "data" && e.element.element_type === "table" && e.element.name === selectedTableName
    );
  }, [graph.data, selectedTableName]);

  // Mermaid Diagram Render
  const diagramRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!schema || !diagramRef.current) return;
    if (schema.tables.length === 0) {
      diagramRef.current.innerHTML = "";
      return;
    }
    renderMermaid(buildMermaidERD(schema, "all"), diagramRef.current).catch(() => {});
  }, [schema, mainTab]);

  // Modal / Form state for New Table
  const [newTableName, setNewTableName] = useState("");
  const [newTableDesc, setNewTableDesc] = useState("");
  const [showNewTableForm, setShowNewTableForm] = useState(false);

  // Form state for New Column
  const [newColName, setNewColName] = useState("");
  const [newColType, setNewColType] = useState("text");
  const [newColIsPk, setNewColIsPk] = useState(false);
  const [newColIsFk, setNewColIsFk] = useState(false);
  const [newColFkTable, setNewColFkTable] = useState("");
  const [showNewColForm, setShowNewColForm] = useState(false);

  // Database Markdown Documentation data
  const databaseDoc = useDatabaseDoc(scopeId);
  const saveDatabaseDoc = useSaveDatabaseDoc();
  const [docContent, setDocContent] = useState("");
  const [mdTab, setMdTab] = useState<"edit" | "preview" | "split">("split");
  const [copiedPath, setCopiedPath] = useState(false);
  const [copiedPrompt, setCopiedPrompt] = useState(false);

  useEffect(() => {
    if (databaseDoc.data) {
      setDocContent(databaseDoc.data.content || "");
    }
  }, [databaseDoc.data]);

  const docFilePath =
    databaseDoc.data?.file_path ||
    `projects/${activeProject?.name.toLowerCase().replace(/[^a-z0-9_-]+/g, "-") ?? t("screenInspector:common.project")}/database/data-model.md`;

  const handleCopyPath = async () => {
    await navigator.clipboard.writeText(docFilePath);
    setCopiedPath(true);
    setTimeout(() => setCopiedPath(false), 2000);
  };

  const handleCopyAgentPrompt = async () => {
    const tablesList = schema?.tables.map((table) => `- ${table.name} (${t("tables.columnsCount", { count: table.columns.length })})`).join("\n") || t("prompt.noTables");
    const prompt = t("prompt.template", { name: activeProject?.name ?? "", path: docFilePath, tables: tablesList });
    await navigator.clipboard.writeText(prompt);
    setCopiedPrompt(true);
    setTimeout(() => setCopiedPrompt(false), 2000);
  };

  const handleCreateTable = async () => {
    const name = newTableName.trim();
    if (!name || !scopeId) return;
    await createTable.mutateAsync({
      scopeId,
      name,
      description: newTableDesc.trim() || undefined,
    });
    setNewTableName("");
    setNewTableDesc("");
    setShowNewTableForm(false);
    setSelectedTableName(name);
  };

  const handleAddColumn = async () => {
    if (!selectedTableElement || !scopeId || !newColName.trim()) return;
    await addColumn.mutateAsync({
      scopeId,
      tableId: selectedTableElement.element.id,
      name: newColName.trim(),
      sql_type: newColType,
      is_pk: newColIsPk,
      is_fk: newColIsFk,
      fk_ref_table: newColIsFk ? newColFkTable.trim() : "",
      nullable: !newColIsPk,
    });
    setNewColName("");
    setNewColType("text");
    setNewColIsPk(false);
    setNewColIsFk(false);
    setNewColFkTable("");
    setShowNewColForm(false);
  };

  const handleDeleteTable = async () => {
    if (!selectedTableElement || !scopeId) return;
    if (confirm(t("tables.deleteConfirm", { name: selectedTableName }))) {
      await deleteTable.mutateAsync({
        scopeId,
        tableId: selectedTableElement.element.id,
      });
      setSelectedTableName(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header com Contextualização */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b pb-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent">
            <Share2 className="h-6 w-6 text-primary" />
            {t("page.title")}
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-3xl leading-relaxed">
            {t("page.description")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!scopeId || deriveDatabase.isPending}
            onClick={() => scopeId && deriveDatabase.mutate(scopeId)}
            className="gap-1.5 text-xs"
          >
            {deriveDatabase.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4 text-primary" />}
            {t("page.deriveFromScreens")}
          </Button>
          <Link
            to="/screen-inspector"
            className="inline-flex items-center gap-1.5 text-xs rounded-md border border-input bg-background px-3 py-1.5 font-medium hover:bg-accent"
          >
            <Layers className="h-4 w-4 text-primary" />
            {t("page.screensAndRules")}
          </Link>
        </div>
      </div>

      {/* Seletores de Projeto e Escopo */}
      <Card className="border-border/60 bg-card/60">
        <CardContent className="grid gap-4 py-4 md:grid-cols-2">
          <div>
            <Label className="text-xs font-semibold text-muted-foreground">{t("screenInspector:selectors.project")}</Label>
            <Select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="mt-1">
              <option value="">{t("screenInspector:selectors.selectProject")}</option>
              {projects.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label className="text-xs font-semibold text-muted-foreground">{t("screenInspector:selectors.scope")}</Label>
            <Select value={scopeId} onChange={(e) => setScopeId(e.target.value)} disabled={!projectId} className="mt-1">
              <option value="">{t("screenInspector:selectors.selectScope")}</option>
              {scopes.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {t("screenInspector:selectors.revision", { revision: s.revision, status: s.status })}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      {!projectId ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            <Database className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" />
            {t("empty.selectProject")}
          </CardContent>
        </Card>
      ) : !scopeId ? (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="py-10 text-center space-y-3">
            <Database className="mx-auto h-10 w-10 text-primary" />
            <h3 className="text-sm font-bold">{t("empty.noScopeTitle")}</h3>
            <p className="text-xs text-muted-foreground max-w-md mx-auto">
              {t("empty.noScopeDescription")}
            </p>
            <Button
              onClick={() => ensureScope.mutate(projectId)}
              disabled={ensureScope.isPending}
              className="text-xs gap-1.5"
            >
              {ensureScope.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {t("screenInspector:empty.initializeScope")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        /* Abas Principais: Modelagem Visual ERD vs Arquivo MD */
        <Tabs value={mainTab} onValueChange={setMainTab} className="space-y-4">
          <TabsList className="grid grid-cols-2 w-full max-w-md bg-muted/60 p-1">
            <TabsTrigger value="modeling" className="gap-1.5 text-xs">
              <Database className="h-3.5 w-3.5" />
              {t("tabs.modeling")}
            </TabsTrigger>
            <TabsTrigger value="markdown" className="gap-1.5 text-xs">
              <FileText className="h-3.5 w-3.5" />
              {t("tabs.documentation")}
            </TabsTrigger>
          </TabsList>

          {/* ================= ABA 1: MODELAGEM E DIAGRAMA ERD ================= */}
          <TabsContent value="modeling" className="space-y-6">
            <div className="grid gap-6 xl:grid-cols-[300px_1fr]">
              {/* Coluna Lateral: Lista de Tabelas e Ação de Criar Tabela */}
              <div className="space-y-4">
                <Card className="border-border/70 shadow-xs">
                  <CardHeader className="p-3 border-b flex flex-row items-center justify-between space-y-0">
                    <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
                      <Database className="h-4 w-4 text-primary" />
                      {t("tables.title", { count: schema?.tables.length ?? 0 })}
                    </CardTitle>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs gap-1"
                      onClick={() => setShowNewTableForm((v) => !v)}
                    >
                      <Plus className="h-3.5 w-3.5" /> {t("tables.new")}
                    </Button>
                  </CardHeader>
                  <CardContent className="p-3 space-y-2">
                    {showNewTableForm && (
                      <div className="p-3 rounded-lg border border-primary/40 bg-primary/5 space-y-2.5">
                        <Label className="text-xs font-bold text-primary">{t("tables.register")}</Label>
                        <Input
                          className="h-8 text-xs font-mono"
                          placeholder={t("tables.namePlaceholder")}
                          value={newTableName}
                          onChange={(e) => setNewTableName(e.target.value)}
                        />
                        <Input
                          className="h-8 text-xs"
                          placeholder={t("tables.descriptionPlaceholder")}
                          value={newTableDesc}
                          onChange={(e) => setNewTableDesc(e.target.value)}
                        />
                        <div className="flex gap-2 justify-end pt-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 text-xs"
                            onClick={() => setShowNewTableForm(false)}
                          >
                            {t("actions.cancel")}
                          </Button>
                          <Button
                            size="sm"
                            className="h-7 text-xs gap-1"
                            disabled={!newTableName.trim() || createTable.isPending}
                            onClick={handleCreateTable}
                          >
                            {createTable.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                            {t("tables.create")}
                          </Button>
                        </div>
                      </div>
                    )}

                    {schema?.tables.length === 0 ? (
                      <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-md">
                        {t("tables.empty")}
                      </div>
                    ) : (
                      <div className="space-y-1.5 max-h-[500px] overflow-y-auto pr-1">
                        {schema?.tables.map((table) => {
                          const isSelected = selectedTableName === table.name;
                          return (
                            <button
                              key={table.name}
                              type="button"
                              onClick={() => setSelectedTableName(table.name)}
                              className={`flex w-full items-center justify-between rounded-md p-2.5 text-left text-xs transition-all ${
                                isSelected
                                  ? "bg-primary/10 border border-primary/40 font-semibold shadow-xs"
                                  : "hover:bg-accent/50 border border-border/50"
                              }`}
                            >
                              <span className="font-mono text-xs text-primary truncate max-w-[170px]">
                                {table.name}
                              </span>
                              <Badge variant="secondary" className="text-[10px] px-1.5 h-4">
                                {t("tables.columnsShort", { count: table.columns.length })}
                              </Badge>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {namingIssues.length > 0 && (
                  <Card className="border-amber-500/30 bg-amber-500/5">
                    <CardHeader className="p-3 pb-1">
                      <CardTitle className="text-xs font-semibold text-amber-600">{t("tables.namingWarnings")}</CardTitle>
                    </CardHeader>
                    <CardContent className="p-3 pt-1 text-[11px] text-muted-foreground space-y-1">
                      {namingIssues.map((msg, i) => (
                        <p key={i}>• {msg}</p>
                      ))}
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Área Principal: Detalhes da Tabela e Diagrama ERD */}
              <div className="space-y-6 min-w-0">
                {selectedTable ? (
                  <Card className="border-border/70 shadow-xs">
                    <CardHeader className="p-4 border-b flex flex-row items-center justify-between space-y-0">
                      <div>
                        <CardTitle className="text-base font-bold font-mono flex items-center gap-2">
                          <TableIcon className="h-4 w-4 text-primary" />
                          {selectedTable.name}
                        </CardTitle>
                        <CardDescription className="text-xs">
                          {t("tables.columnsRegistered", { count: selectedTable.columns.length })}
                        </CardDescription>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 text-xs gap-1"
                          onClick={() => setShowNewColForm((v) => !v)}
                        >
                          <Plus className="h-3.5 w-3.5" /> {t("columns.add")}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 text-xs text-destructive hover:bg-destructive/10"
                          onClick={handleDeleteTable}
                          title={t("tables.delete")}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </CardHeader>

                    <CardContent className="p-4 space-y-4">
                      {showNewColForm && (
                        <div className="p-3.5 rounded-lg border border-primary/30 bg-primary/5 space-y-3">
                          <div className="font-semibold text-xs text-primary">{t("columns.newInTable", { name: selectedTable.name })}</div>
                          <div className="grid gap-3 sm:grid-cols-3">
                            <div>
                              <Label className="text-[11px] text-muted-foreground">{t("columns.name")}</Label>
                              <Input
                                className="h-8 text-xs font-mono mt-1"
                                placeholder={t("columns.namePlaceholder")}
                                value={newColName}
                                onChange={(e) => setNewColName(e.target.value)}
                              />
                            </div>
                            <div>
                              <Label className="text-[11px] text-muted-foreground">{t("columns.sqlType")}</Label>
                              <Select
                                className="h-8 text-xs mt-1"
                                value={newColType}
                                onChange={(e) => setNewColType(e.target.value)}
                              >
                                {SQL_TYPES.map((t) => (
                                  <option key={t} value={t}>
                                    {t}
                                  </option>
                                ))}
                              </Select>
                            </div>
                            <div className="flex flex-col justify-end gap-2">
                              <div className="flex items-center gap-3">
                                <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                                  <input
                                    type="checkbox"
                                    className="rounded text-primary h-3.5 w-3.5"
                                    checked={newColIsPk}
                                    onChange={(e) => setNewColIsPk(e.target.checked)}
                                  />
                                  <span>PK</span>
                                </label>
                                <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                                  <input
                                    type="checkbox"
                                    className="rounded text-primary h-3.5 w-3.5"
                                    checked={newColIsFk}
                                    onChange={(e) => setNewColIsFk(e.target.checked)}
                                  />
                                  <span>FK</span>
                                </label>
                              </div>
                              {newColIsFk && (
                                <Input
                                  className="h-7 text-xs font-mono"
                                  placeholder={t("columns.referenceTable")}
                                  value={newColFkTable}
                                  onChange={(e) => setNewColFkTable(e.target.value)}
                                />
                              )}
                            </div>
                          </div>

                          <div className="flex justify-end gap-2 pt-1">
                            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowNewColForm(false)}>
                              {t("actions.cancel")}
                            </Button>
                            <Button size="sm" className="h-7 text-xs gap-1" disabled={!newColName.trim() || addColumn.isPending} onClick={handleAddColumn}>
                              {addColumn.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                              {t("columns.save")}
                            </Button>
                          </div>
                        </div>
                      )}

                      <div className="rounded-md border overflow-hidden">
                        <table className="w-full text-left text-xs">
                          <thead className="bg-muted/50 border-b font-semibold text-muted-foreground">
                            <tr>
                              <th className="p-2.5">{t("columns.column")}</th>
                              <th className="p-2.5">{t("columns.sqlType")}</th>
                              <th className="p-2.5">{t("columns.attributes")}</th>
                            </tr>
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
                ) : null}

                {/* Diagrama Visual Mermaid ERD */}
                <Card className="border-border/70 shadow-xs">
                  <CardHeader className="p-4 border-b flex flex-row items-center justify-between space-y-0">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <Share2 className="h-4 w-4 text-primary" />
                      {t("diagram.title")}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs gap-1.5"
                        disabled={!screensRevisionId || validate.isPending}
                        onClick={() => screensRevisionId && validate.mutate(screensRevisionId)}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                        {t("diagram.validate")}
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="p-4">
                    {schema?.tables.length === 0 ? (
                      <div className="py-12 text-center text-xs text-muted-foreground">
                        {t("diagram.empty")}
                      </div>
                    ) : (
                      <div ref={diagramRef} className="w-full overflow-x-auto min-h-[300px] flex justify-center p-2" />
                    )}

                    {validate.data && (
                      <div className={`mt-4 p-3 rounded-lg border text-xs ${validate.data.valid ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "border-destructive/30 bg-destructive/10 text-destructive"}`}>
                        {validate.data.valid
                          ? t("diagram.valid")
                          : t("diagram.issues", { count: validate.data.issues.length })}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          {/* ================= ABA 2: DOCUMENTAÇÃO DO BANCO (.MD) ================= */}
          <TabsContent value="markdown" className="space-y-4">
            {/* Card de Localização do Arquivo e Atalhos para o Agente */}
            <Card className="border-primary/20 bg-primary/5">
              <CardContent className="p-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-3 text-xs">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-primary">{t("screenInspector:rules.fileLocation")}</span>
                    <code className="rounded bg-background/80 px-2 py-0.5 font-mono text-[11px] border">
                      {docFilePath}
                    </code>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {t("documentation.description")}
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs gap-1.5 bg-background"
                    onClick={handleCopyPath}
                  >
                    {copiedPath ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedPath ? t("screenInspector:rules.pathCopied") : t("screenInspector:rules.copyPath")}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-8 text-xs gap-1.5"
                    onClick={handleCopyAgentPrompt}
                  >
                    {copiedPrompt ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Sparkles className="h-3.5 w-3.5 text-primary" />}
                    {copiedPrompt ? t("screenInspector:rules.promptCopied") : t("screenInspector:rules.copyPrompt")}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Editor e Visualizador de Markdown do Banco */}
            <Card className="border-border/70">
              <CardHeader className="p-4 border-b flex flex-row items-center justify-between space-y-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">{t("screenInspector:rules.view")}</span>
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant={mdTab === "edit" ? "default" : "outline"}
                      className="h-7 text-xs"
                      onClick={() => setMdTab("edit")}
                    >
                      <Code className="mr-1 h-3.5 w-3.5" /> {t("screenInspector:rules.edit")}
                    </Button>
                    <Button
                      size="sm"
                      variant={mdTab === "preview" ? "default" : "outline"}
                      className="h-7 text-xs"
                      onClick={() => setMdTab("preview")}
                    >
                      <Eye className="mr-1 h-3.5 w-3.5" /> {t("screenInspector:rules.rendered")}
                    </Button>
                    <Button
                      size="sm"
                      variant={mdTab === "split" ? "default" : "outline"}
                      className="h-7 text-xs"
                      onClick={() => setMdTab("split")}
                    >
                      <Columns className="mr-1 h-3.5 w-3.5" /> {t("screenInspector:rules.sideBySide")}
                    </Button>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {databaseDoc.data?.updated_at && (
                    <span className="text-[10px] text-muted-foreground">
                      {t("screenInspector:rules.savedAt", { date: new Date(databaseDoc.data.updated_at).toLocaleString(i18n.language) })}
                    </span>
                  )}
                  <Button
                    size="sm"
                    disabled={saveDatabaseDoc.isPending}
                    onClick={() => saveDatabaseDoc.mutate({ scopeId, content: docContent })}
                    className="h-7 text-xs gap-1.5"
                  >
                    {saveDatabaseDoc.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {t("documentation.save")}
                  </Button>
                </div>
              </CardHeader>

              <CardContent className="p-4">
                {databaseDoc.isLoading ? (
                  <div className="py-12 text-center text-xs text-muted-foreground">
                    <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-primary" />
                    {t("documentation.loading")}
                  </div>
                ) : (
                  <div className="space-y-4">
                    {mdTab === "edit" && (
                      <Textarea
                        rows={20}
                        className="resize-none bg-muted/20 font-mono text-xs leading-relaxed"
                        placeholder={t("documentation.editorPlaceholder")}
                        value={docContent}
                        onChange={(e) => setDocContent(e.target.value)}
                      />
                    )}

                    {mdTab === "preview" && (
                      <div className="rounded-md border p-4 min-h-[400px] bg-card text-xs overflow-y-auto">
                        {docContent.trim() ? (
                          <Markdown content={docContent} />
                        ) : (
                          <p className="text-muted-foreground italic">{t("documentation.noContent")}</p>
                        )}
                      </div>
                    )}

                    {mdTab === "split" && (
                      <div className="grid gap-4 lg:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("screenInspector:rules.markdownEditor")}</Label>
                          <Textarea
                            rows={20}
                            className="resize-none bg-muted/20 font-mono text-xs leading-relaxed"
                            placeholder={t("documentation.shortPlaceholder")}
                            value={docContent}
                            onChange={(e) => setDocContent(e.target.value)}
                          />
                        </div>
                        <div className="space-y-1.5 flex flex-col">
                          <Label className="text-xs text-muted-foreground">{t("screenInspector:rules.renderedPreview")}</Label>
                          <div className="flex-1 rounded-md border p-4 bg-card text-xs overflow-y-auto max-h-[440px]">
                            {docContent.trim() ? (
                              <Markdown content={docContent} />
                            ) : (
                              <p className="text-muted-foreground italic">{t("screenInspector:rules.nothingToRender")}</p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
