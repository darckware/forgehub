import { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCopy,
  Code2,
  Eye,
  KeyRound,
  Link2,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Table2,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";
import {
  useDatabaseTable,
  useDatabaseTables,
  useDatabaseFunctions,
  useDatabaseFunction,
  useDatabaseIndexes,
  useExecuteQuery,
  useCreateFunction,
  useDropFunction,
  useCreateIndex,
  useDropIndex,
  useCreateTable,
  type FunctionSummary,
  type IndexGlobal,
  type ColumnDef,
  type QueryResult,
} from "@/hooks/useDatabase";
import { useSchema } from "./SchemaContext";
import { ResultsTable } from "./QueryPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function typeColor(t: string) {
  if (t.includes("uuid")) return "text-violet-500";
  if (t.includes("int") || t.includes("numeric") || t.includes("float")) return "text-blue-500";
  if (t.includes("char") || t.includes("text")) return "text-emerald-500";
  if (t.includes("bool")) return "text-amber-500";
  if (t.includes("timestamp") || t.includes("date")) return "text-sky-500";
  if (t.includes("json")) return "text-orange-500";
  return "text-muted-foreground";
}

function LangBadge({ lang }: { lang: string }) {
  const color = lang === "plpgsql" ? "border-violet-500/40 text-violet-600"
    : lang === "sql" ? "border-blue-500/40 text-blue-600"
    : "border-muted-foreground/30 text-muted-foreground";
  return <Badge variant="outline" className={cn("text-[10px] font-mono", color)}>{lang}</Badge>;
}

// ---------------------------------------------------------------------------
// Mini SQL editor modal (for create/edit function)
// ---------------------------------------------------------------------------

function SqlEditorModal({
  title, initialValue, onSave, onClose, saving, error,
}: {
  title: string; initialValue: string;
  onSave: (sql: string) => void; onClose: () => void;
  saving: boolean; error: string | null;
}) {
  const [sql, setSql] = useState(initialValue);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-3xl rounded-xl border border-border bg-card shadow-2xl flex flex-col max-h-[90vh]">
        <div className="flex items-center gap-3 px-5 py-3 border-b border-border shrink-0">
          <Code2 className="h-4 w-4 text-blue-500" />
          <h2 className="font-semibold text-sm flex-1">{title}</h2>
          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        <div className="flex-1 min-h-0 overflow-hidden p-4 flex flex-col gap-3">
          <div className="rounded border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 flex items-center gap-2">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            This action runs SQL directly against the database. Review before saving.
          </div>
          <Textarea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            rows={18}
            className="font-mono text-xs resize-none bg-muted/30 flex-1"
            spellCheck={false}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); onSave(sql); } }}
          />
          {error && (
            <div className="rounded border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive font-mono whitespace-pre-wrap">
              {error}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between px-5 py-3 border-t border-border shrink-0">
          <span className="text-[10px] text-muted-foreground">Ctrl+Enter to run</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={onClose}>Cancel</Button>
            <Button size="sm" onClick={() => onSave(sql)} disabled={saving || !sql.trim()}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
              Run
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create Table modal
// ---------------------------------------------------------------------------

const PG_TYPES = ["uuid", "text", "varchar(255)", "integer", "bigint", "boolean",
  "numeric", "float8", "timestamp with time zone", "date", "jsonb", "bytea"];

function CreateTableModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [columns, setColumns] = useState<ColumnDef[]>([
    { name: "id", type: "uuid", nullable: false, primary_key: true, default: "gen_random_uuid()" },
    { name: "created_at", type: "timestamp with time zone", nullable: false, primary_key: false, default: "now()" },
  ]);
  const [error, setError] = useState<string | null>(null);
  const createMut = useCreateTable();

  const addCol = () => setColumns((c) => [...c, { name: "", type: "text", nullable: true, primary_key: false, default: "" }]);
  const removeCol = (i: number) => setColumns((c) => c.filter((_, j) => j !== i));
  const updateCol = (i: number, field: keyof ColumnDef, value: string | boolean) =>
    setColumns((c) => c.map((col, j) => j === i ? { ...col, [field]: value } : col));

  const save = async () => {
    setError(null);
    try {
      await createMut.mutateAsync({ name, columns });
      onCreated();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-2xl rounded-xl border border-border bg-card shadow-2xl flex flex-col max-h-[90vh]">
        <div className="flex items-center gap-3 px-5 py-3 border-b border-border shrink-0">
          <Table2 className="h-4 w-4 text-emerald-500" />
          <h2 className="font-semibold text-sm flex-1">Create Table</h2>
          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onClose}><X className="h-4 w-4" /></Button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
          <div>
            <Label className="text-xs">Table Name <span className="text-destructive">*</span></Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="my_table" className="h-8 mt-1 font-mono text-xs" />
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label className="text-xs">Columns</Label>
              <Button size="sm" variant="ghost" className="h-6 text-xs px-2 gap-1" onClick={addCol}><Plus className="h-3 w-3" /> Column</Button>
            </div>
            <div className="space-y-2">
              {columns.map((col, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_auto_auto_1fr_auto] gap-2 items-center">
                  <Input value={col.name} onChange={(e) => updateCol(i, "name", e.target.value)} placeholder="name" className="h-7 font-mono text-xs" />
                  <select value={col.type} onChange={(e) => updateCol(i, "type", e.target.value)} className="h-7 text-xs rounded border border-input bg-background px-2 font-mono">
                    {PG_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <label className="flex items-center gap-1 text-xs whitespace-nowrap cursor-pointer">
                    <input type="checkbox" checked={col.nullable} onChange={(e) => updateCol(i, "nullable", e.target.checked)} className="h-3 w-3" /> Null
                  </label>
                  <label className="flex items-center gap-1 text-xs whitespace-nowrap cursor-pointer">
                    <input type="checkbox" checked={col.primary_key} onChange={(e) => updateCol(i, "primary_key", e.target.checked)} className="h-3 w-3" /> PK
                  </label>
                  <Input value={col.default} onChange={(e) => updateCol(i, "default", e.target.value)} placeholder="default" className="h-7 font-mono text-[10px]" />
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground" onClick={() => removeCol(i)}><X className="h-3 w-3" /></Button>
                </div>
              ))}
            </div>
          </div>
          {error && <div className="rounded border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive font-mono whitespace-pre-wrap">{error}</div>}
        </div>
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-border shrink-0">
          <Button size="sm" variant="outline" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={save} disabled={!name.trim() || createMut.isPending}>
            {createMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null} Create Table
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create Index form
// ---------------------------------------------------------------------------

function CreateIndexPanel({ tables, onClose, onCreated }: { tables: string[]; onClose: () => void; onCreated: () => void }) {
  const [table, setTable] = useState(tables[0] ?? "");
  const [cols, setCols] = useState("");
  const [idxName, setIdxName] = useState("");
  const [unique, setUnique] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createMut = useCreateIndex();

  const save = async () => {
    setError(null);
    const colList = cols.split(",").map((c) => c.trim()).filter(Boolean);
    if (!colList.length) { setError("Provide at least one column"); return; }
    try {
      await createMut.mutateAsync({ table_name: table, column_names: colList, index_name: idxName || undefined, unique });
      onCreated();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-3 p-4 rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold">New Index</span>
        <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={onClose}><X className="h-3 w-3" /></Button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Table</Label>
          <select value={table} onChange={(e) => setTable(e.target.value)} className="mt-1 h-7 w-full text-xs rounded border border-input bg-background px-2 font-mono">
            {tables.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <Label className="text-xs">Columns <span className="text-muted-foreground">(comma-separated)</span></Label>
          <Input value={cols} onChange={(e) => setCols(e.target.value)} placeholder="col1, col2" className="h-7 mt-1 text-xs font-mono" />
        </div>
        <div>
          <Label className="text-xs">Index name <span className="text-muted-foreground">(optional)</span></Label>
          <Input value={idxName} onChange={(e) => setIdxName(e.target.value)} placeholder="idx_table_col" className="h-7 mt-1 text-xs font-mono" />
        </div>
        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 text-xs cursor-pointer">
            <input type="checkbox" checked={unique} onChange={(e) => setUnique(e.target.checked)} className="h-3.5 w-3.5" /> UNIQUE
          </label>
        </div>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="outline" onClick={onClose}>Cancel</Button>
        <Button size="sm" onClick={save} disabled={createMut.isPending || !table || !cols}>
          {createMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null} Create Index
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tables section
// ---------------------------------------------------------------------------

const PAGE_SIZE = 100;

function TablesSection() {
  const { schema, instance, db } = useSchema();
  const { data: tables = [], isLoading, refetch, isFetching } = useDatabaseTables(schema, instance, db);
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [dataResult, setDataResult] = useState<QueryResult | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [csvCopied, setCsvCopied] = useState(false);
  const dataMut = useExecuteQuery();
  const { data: detail, isLoading: loadingDetail } = useDatabaseTable(selected, schema, instance, db);

  const handleViewData = async (tableName: string, pageNum = 0) => {
    setSelected(tableName);
    setDataResult(null);
    setDataError(null);
    setPage(pageNum);
    try {
      const r = await dataMut.mutateAsync({
        sql: `SELECT * FROM "${schema}"."${tableName}"`,
        limit: PAGE_SIZE,
        offset: pageNum * PAGE_SIZE,
        instance,
        db,
        schema,
      });
      setDataResult(r);
    } catch (e) {
      setDataError(e instanceof Error ? e.message : String(e));
    }
  };

  const filtered = tables.filter((t) => t.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="flex h-full min-h-0">
      {/* List */}
      <div className="w-56 shrink-0 border-r border-border flex flex-col h-full">
        <div className="p-2 border-b border-border space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{tables.length} tables</span>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" className="h-5 w-5 p-0" onClick={() => refetch()} disabled={isFetching}><RefreshCw className={cn("h-3 w-3", isFetching && "animate-spin")} /></Button>
              <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-emerald-600" onClick={() => setShowCreate(true)} title="Create table"><Plus className="h-3 w-3" /></Button>
            </div>
          </div>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search..." className="h-6 pl-6 text-[10px]" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-0.5">
          {isLoading ? <div className="flex justify-center py-6"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            : filtered.map((t) => (
              <div key={t.name} className={cn("group flex items-center hover:bg-accent transition-colors", selected === t.name && "bg-accent")}>
                <button
                  type="button"
                  onClick={() => { setSelected(t.name); setDataResult(null); setDataError(null); setPage(0); }}
                  className="flex-1 flex items-center gap-1.5 px-2.5 py-1.5 text-left min-w-0 overflow-hidden"
                >
                  <Table2 className="h-3 w-3 shrink-0 text-muted-foreground" />
                  <span className="flex-1 text-[11px] font-mono truncate">{t.name}</span>
                  <span className="text-[9px] text-muted-foreground shrink-0">{t.row_count}</span>
                </button>
                {t.row_count > 0 && (
                  <button
                    type="button"
                    title="View data"
                    onClick={() => handleViewData(t.name)}
                    className="shrink-0 p-1.5 pr-2 text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <Eye className="h-3 w-3" />
                  </button>
                )}
              </div>
            ))}
        </div>
      </div>

      {/* Detail */}
      <div className="flex-1 min-w-0 overflow-y-auto p-4">
        {!selected ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
            <Table2 className="h-10 w-10 opacity-20" />
            <p className="text-sm">Select a table</p>
          </div>
        ) : loadingDetail ? (
          <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
        ) : detail ? (
          <div className="space-y-5 max-w-3xl">
            <div>
              <h2 className="text-base font-mono font-bold">{detail.name}</h2>
              <p className="text-xs text-muted-foreground">company.{detail.name} · {detail.row_count.toLocaleString()} rows · {detail.columns.length} cols</p>
            </div>

            {dataMut.isPending && selected === detail.name && (
              <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading data…
              </div>
            )}
            {dataError && selected === detail.name && (
              <div className="rounded border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive font-mono whitespace-pre-wrap">
                {dataError}
              </div>
            )}
            {dataResult && selected === detail.name && (() => {
              const totalPages = Math.ceil(detail.row_count / PAGE_SIZE);
              const copyCSV = () => {
                const header = dataResult.columns.join(",");
                const body = dataResult.rows.map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
                navigator.clipboard.writeText(`${header}\n${body}`);
                setCsvCopied(true);
                setTimeout(() => setCsvCopied(false), 2000);
              };
              return (
                <div className="space-y-1.5">
                  {/* Stats bar — outside scroll container so it stays visible on horizontal scroll */}
                  <div className="flex items-center gap-2 px-1">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                    <span className="text-xs text-muted-foreground flex-1">
                      {dataResult.row_count} row(s) · {dataResult.elapsed_ms.toFixed(1)} ms
                    </span>
                    <Button size="sm" variant="ghost" className="h-6 px-2 gap-1 text-xs" onClick={copyCSV}>
                      <ClipboardCopy className="h-3 w-3" /> {csvCopied ? "Copied!" : "CSV"}
                    </Button>
                    {totalPages > 1 && (
                      <>
                        <span className="text-xs text-muted-foreground border-l border-border pl-2">
                          Page {page + 1} of {totalPages} · {detail.row_count.toLocaleString()} records
                        </span>
                        <Button size="sm" variant="outline" className="h-6 w-6 p-0"
                          disabled={page === 0 || dataMut.isPending}
                          onClick={() => handleViewData(detail.name, page - 1)}>
                          <ChevronLeft className="h-3.5 w-3.5" />
                        </Button>
                        <Button size="sm" variant="outline" className="h-6 w-6 p-0"
                          disabled={page >= totalPages - 1 || dataMut.isPending}
                          onClick={() => handleViewData(detail.name, page + 1)}>
                          <ChevronRight className="h-3.5 w-3.5" />
                        </Button>
                      </>
                    )}
                  </div>
                  <div className="rounded-lg border border-border" style={{ maxHeight: "400px", overflow: "auto" }}>
                    <ResultsTable result={dataResult} />
                  </div>
                </div>
              );
            })()}

            {/* Columns */}
            <div>
              <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Columns</h3>
              <div className="rounded border border-border overflow-hidden">
                <table className="w-full text-xs">
                  <thead><tr className="bg-muted/40 border-b border-border">
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Name</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Type</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Null</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Default</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Flags</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Ref</th>
                  </tr></thead>
                  <tbody className="divide-y divide-border">
                    {detail.columns.map((col) => (
                      <tr key={col.name} className="hover:bg-muted/10">
                        <td className="px-3 py-1.5 font-mono font-medium">{col.name}</td>
                        <td className={cn("px-3 py-1.5 font-mono", typeColor(col.data_type))}>{col.data_type}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{col.is_nullable ? "YES" : <span className="text-foreground font-medium">NO</span>}</td>
                        <td className="px-3 py-1.5 font-mono text-[10px] text-muted-foreground max-w-[120px] truncate" title={col.column_default ?? ""}>{col.column_default ?? "—"}</td>
                        <td className="px-3 py-1.5">
                          <div className="flex gap-1">
                            {col.is_primary_key && <span className="inline-flex items-center gap-0.5 rounded bg-amber-500/15 px-1 py-0.5 text-[10px] text-amber-600"><KeyRound className="h-2 w-2" />PK</span>}
                            {col.is_foreign_key && <span className="inline-flex items-center gap-0.5 rounded bg-blue-500/15 px-1 py-0.5 text-[10px] text-blue-600"><Link2 className="h-2 w-2" />FK</span>}
                          </div>
                        </td>
                        <td className="px-3 py-1.5 font-mono text-[10px] text-muted-foreground">{col.references ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {detail.foreign_keys.length > 0 && (
              <div>
                <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Foreign Keys</h3>
                <div className="rounded border border-border overflow-hidden">
                  <table className="w-full text-xs"><thead><tr className="bg-muted/40 border-b border-border">
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Column</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Reference</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Ref. col.</th>
                  </tr></thead>
                    <tbody className="divide-y divide-border">
                      {detail.foreign_keys.map((fk) => (
                        <tr key={fk.column} className="hover:bg-muted/10">
                          <td className="px-3 py-1.5 font-mono">{fk.column}</td>
                          <td className="px-3 py-1.5 font-mono text-blue-500">{fk.ref_table}</td>
                          <td className="px-3 py-1.5 font-mono text-muted-foreground">{fk.ref_column}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {detail.indexes.length > 0 && (
              <div>
                <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Indexes</h3>
                <div className="rounded border border-border overflow-hidden">
                  <table className="w-full text-xs"><thead><tr className="bg-muted/40 border-b border-border">
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Name</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Columns</th>
                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Type</th>
                  </tr></thead>
                    <tbody className="divide-y divide-border">
                      {detail.indexes.map((idx) => (
                        <tr key={idx.name} className="hover:bg-muted/10">
                          <td className="px-3 py-1.5 font-mono text-[10px]">{idx.name}</td>
                          <td className="px-3 py-1.5 font-mono">{idx.columns.join(", ")}</td>
                          <td className="px-3 py-1.5">
                            {idx.is_primary ? <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-600">PRIMARY</Badge>
                              : idx.is_unique ? <Badge variant="outline" className="text-[10px]">UNIQUE</Badge>
                              : <Badge variant="outline" className="text-[10px] text-muted-foreground">INDEX</Badge>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>

      {showCreate && <CreateTableModal onClose={() => setShowCreate(false)} onCreated={() => refetch()} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Functions section
// ---------------------------------------------------------------------------

const FN_TEMPLATE = `CREATE OR REPLACE FUNCTION company.my_function()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  -- your logic here
END;
$$;`;

function FunctionsSection() {
  const { schema, instance, db } = useSchema();
  const { data: functions = [], isLoading, refetch, isFetching } = useDatabaseFunctions(schema, instance, db);
  const [selected, setSelected] = useState<FunctionSummary | null>(null);
  const [search, setSearch] = useState("");
  const [editorMode, setEditorMode] = useState<"create" | "edit" | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);

  const { data: detail, isLoading: loadingDetail } = useDatabaseFunction(selected?.name ?? null, schema, instance, db);
  const createMut = useCreateFunction();
  const dropMut = useDropFunction();

  const filtered = functions.filter((f) => f.name.toLowerCase().includes(search.toLowerCase()));

  const openCreate = () => { setEditorMode("create"); setEditorError(null); };
  const openEdit = () => { if (detail) { setEditorMode("edit"); setEditorError(null); } };

  const saveFunction = async (sql: string) => {
    setEditorError(null);
    try {
      await createMut.mutateAsync({ source: sql });
      setEditorMode(null);
      refetch();
    } catch (e) {
      setEditorError(e instanceof Error ? e.message : String(e));
    }
  };

  const confirmDrop = async () => {
    if (!dropTarget) return;
    try {
      await dropMut.mutateAsync(dropTarget);
      if (selected?.name === dropTarget) setSelected(null);
      setDropTarget(null);
      refetch();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
      setDropTarget(null);
    }
  };

  return (
    <div className="flex h-full min-h-0">
      <div className="w-56 shrink-0 border-r border-border flex flex-col h-full">
        <div className="p-2 border-b border-border space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">{functions.length} functions</span>
            <div className="flex gap-1">
              <Button size="sm" variant="ghost" className="h-5 w-5 p-0" onClick={() => refetch()} disabled={isFetching}><RefreshCw className={cn("h-3 w-3", isFetching && "animate-spin")} /></Button>
              <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-emerald-600" onClick={openCreate} title="Create function"><Plus className="h-3 w-3" /></Button>
            </div>
          </div>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search..." className="h-6 pl-6 text-[10px]" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-0.5">
          {isLoading ? <div className="flex justify-center py-6"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            : filtered.length === 0 ? <p className="text-center text-xs text-muted-foreground py-6">No functions found</p>
            : filtered.map((f) => (
              <button key={f.name} type="button" onClick={() => setSelected(f)}
                className={cn("w-full flex items-center gap-1.5 px-2.5 py-1.5 text-left hover:bg-accent transition-colors group", selected?.name === f.name && "bg-accent")}>
                <Zap className="h-3 w-3 shrink-0 text-violet-500" />
                <span className="flex-1 text-[11px] font-mono truncate">{f.name}</span>
                <LangBadge lang={f.language} />
              </button>
            ))}
        </div>
      </div>

      <div className="flex-1 min-w-0 overflow-y-auto p-4">
        {!selected ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
            <Zap className="h-10 w-10 opacity-20" />
            <p className="text-sm">Select a function</p>
            <Button size="sm" variant="outline" onClick={openCreate} className="gap-1.5 mt-2"><Plus className="h-3.5 w-3.5" /> New Function</Button>
          </div>
        ) : loadingDetail ? (
          <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
        ) : detail ? (
          <div className="space-y-4 max-w-3xl">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-base font-mono font-bold">{detail.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <LangBadge lang={detail.language} />
                  <Badge variant="outline" className="text-[10px]">{detail.kind}</Badge>
                  {detail.return_type && <span className="text-xs text-muted-foreground">→ {detail.return_type}</span>}
                </div>
                {detail.arg_types && <p className="text-xs text-muted-foreground font-mono mt-0.5">({detail.arg_types})</p>}
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={openEdit}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
                <Button size="sm" variant="ghost" className="gap-1.5 text-xs text-destructive" onClick={() => setDropTarget(detail.name)}><Trash2 className="h-3.5 w-3.5" /> Drop</Button>
              </div>
            </div>
            <div>
              <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">Source</h3>
              <pre className="rounded-lg border border-border bg-muted/30 p-4 text-xs font-mono whitespace-pre-wrap overflow-auto max-h-[500px]">{detail.source}</pre>
            </div>
          </div>
        ) : null}
      </div>

      {editorMode && (
        <SqlEditorModal
          title={editorMode === "create" ? "Create / Replace Function" : `Edit: ${detail?.name}`}
          initialValue={editorMode === "edit" && detail ? detail.source : FN_TEMPLATE}
          onSave={saveFunction}
          onClose={() => setEditorMode(null)}
          saving={createMut.isPending}
          error={editorError}
        />
      )}
      <ConfirmDialog
        open={!!dropTarget}
        title="Drop Function"
        description={`Remove function "${dropTarget}" from the database? This action cannot be undone.`}
        confirmLabel="Drop"
        onConfirm={confirmDrop}
        onCancel={() => setDropTarget(null)}
        loading={dropMut.isPending}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Indexes section
// ---------------------------------------------------------------------------

function IndexesSection() {
  const { schema, instance, db } = useSchema();
  const { data: allTables = [] } = useDatabaseTables(schema, instance, db);
  const { data: indexes = [], isLoading, refetch, isFetching } = useDatabaseIndexes(schema, instance, db);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const dropMut = useDropIndex();

  const tableNames = allTables.map((t) => t.name);
  const filtered = indexes.filter((i) =>
    i.name.toLowerCase().includes(search.toLowerCase()) || i.table_name.toLowerCase().includes(search.toLowerCase())
  );

  const grouped: Record<string, IndexGlobal[]> = {};
  for (const idx of filtered) {
    grouped[idx.table_name] = [...(grouped[idx.table_name] ?? []), idx];
  }

  const confirmDrop = async () => {
    if (!dropTarget) return;
    try {
      await dropMut.mutateAsync(dropTarget);
      setDropTarget(null);
      refetch();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
      setDropTarget(null);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border shrink-0">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search index or table..." className="h-7 pl-7 text-xs" />
        </div>
        <span className="text-xs text-muted-foreground flex-1">{indexes.length} index(es) · {Object.keys(grouped).length} tables</span>
        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => refetch()} disabled={isFetching}><RefreshCw className={cn("h-3 w-3", isFetching && "animate-spin")} /></Button>
        <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={() => setShowCreate((v) => !v)}><Plus className="h-3.5 w-3.5" /> New Index</Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {showCreate && (
          <CreateIndexPanel tables={tableNames} onClose={() => setShowCreate(false)} onCreated={() => refetch()} />
        )}
        {isLoading ? (
          <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
        ) : Object.entries(grouped).map(([table, idxs]) => (
          <div key={table}>
            <div className="flex items-center gap-2 mb-1.5">
              <Table2 className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-mono font-semibold">{table}</span>
              <span className="text-[10px] text-muted-foreground">{idxs.length} index(es)</span>
            </div>
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full text-xs">
                <thead><tr className="bg-muted/40 border-b border-border">
                  <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Name</th>
                  <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Columns</th>
                  <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Type</th>
                  <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Definition</th>
                  <th className="px-3 py-1.5 w-10"></th>
                </tr></thead>
                <tbody className="divide-y divide-border">
                  {idxs.map((idx) => (
                    <tr key={idx.name} className="hover:bg-muted/10 group">
                      <td className="px-3 py-1.5 font-mono text-[10px]">{idx.name}</td>
                      <td className="px-3 py-1.5 font-mono">{idx.columns}</td>
                      <td className="px-3 py-1.5">
                        {idx.is_primary ? <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-600">PRIMARY</Badge>
                          : idx.is_unique ? <Badge variant="outline" className="text-[10px]">UNIQUE</Badge>
                          : <Badge variant="outline" className="text-[10px] text-muted-foreground">INDEX</Badge>}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-[10px] text-muted-foreground max-w-[300px] truncate" title={idx.index_def}>{idx.index_def}</td>
                      <td className="px-3 py-1.5">
                        {!idx.is_primary && (
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-destructive opacity-0 group-hover:opacity-100" onClick={() => setDropTarget(idx.name)}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>

      <ConfirmDialog
        open={!!dropTarget}
        title="Drop Index"
        description={`Remove index "${dropTarget}"? This action cannot be undone.`}
        confirmLabel="Drop"
        onConfirm={confirmDrop}
        onCancel={() => setDropTarget(null)}
        loading={dropMut.isPending}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type Section = "tables" | "functions" | "indexes";

export default function SchemaPage() {
  const [section, setSection] = useState<Section>("tables");

  const tabs: { id: Section; label: string; icon: React.ReactNode }[] = [
    { id: "tables", label: "Tables", icon: <Table2 className="h-3.5 w-3.5" /> },
    { id: "functions", label: "Functions", icon: <Zap className="h-3.5 w-3.5" /> },
    { id: "indexes", label: "Indexes", icon: <ChevronRight className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* Section tabs */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-border shrink-0 bg-muted/10">
        {tabs.map((tab) => (
          <button key={tab.id} type="button" onClick={() => setSection(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
              section === tab.id ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50"
            )}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        {section === "tables" && <TablesSection />}
        {section === "functions" && <FunctionsSection />}
        {section === "indexes" && <IndexesSection />}
      </div>
    </div>
  );
}
