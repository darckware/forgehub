import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowUpDown,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardCopy,
  Eraser,
  Loader2,
  Play,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useExecuteQuery } from "@/hooks/useDatabase";
import type { QueryResult } from "@/hooks/useDatabase";
import { useSchema } from "./SchemaContext";
import { apiClient, ApiError } from "@/lib/api";

interface ValidateResult {
  valid: boolean;
  error?: string | null;
}

const EXAMPLES = [
  { label: "Tables", sql: "SELECT table_name, table_type\nFROM information_schema.tables\nWHERE table_schema = 'company'\nORDER BY table_name" },
  { label: "Products", sql: "SELECT id, name, created_at\nFROM company.products\nORDER BY created_at DESC" },
  { label: "Projects", sql: "SELECT p.name, p.status, v.version\nFROM company.projects p\nJOIN company.product_versions v ON v.id = p.product_version_id\nORDER BY p.created_at DESC" },
  { label: "Recent tasks", sql: "SELECT title, status, created_at\nFROM company.project_tasks\nORDER BY created_at DESC\nLIMIT 20" },
];

type ValidationState = "idle" | "checking" | "valid" | "invalid";

function ValidationIcon({ state, error }: { state: ValidationState; error: string | null }) {
  if (state === "checking")
    return <span title="Validating syntax…"><Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground shrink-0" /></span>;
  if (state === "valid")
    return <span title="Valid syntax"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" /></span>;
  if (state === "invalid")
    return <span title={error ?? "Syntax error"}><XCircle className="h-3.5 w-3.5 text-destructive shrink-0" /></span>;
  return null;
}

export function ResultsTable({ result }: { result: QueryResult }) {
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [colWidths, setColWidths] = useState<Record<string, number>>({});
  const resizingRef = useRef<{ col: string; startX: number; startW: number } | null>(null);

  // Client-side sort over the fetched rows
  const sortedRows = useMemo(() => {
    if (!sortCol) return result.rows;
    const idx = result.columns.indexOf(sortCol);
    if (idx === -1) return result.rows;
    return [...result.rows].sort((a, b) => {
      const av = a[idx], bv = b[idx];
      if (av === null && bv === null) return 0;
      if (av === null) return sortDir === "asc" ? -1 : 1;
      if (bv === null) return sortDir === "asc" ? 1 : -1;
      const an = Number(av), bn = Number(bv);
      if (!isNaN(an) && !isNaN(bn)) return sortDir === "asc" ? an - bn : bn - an;
      return sortDir === "asc"
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
  }, [result.rows, result.columns, sortCol, sortDir]);

  const handleSort = (col: string) => {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  };

  // Drag-to-resize: track start position and width via a ref to avoid stale closures
  const startResize = (col: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation(); // don't trigger sort click
    const th = (e.currentTarget as HTMLElement).closest("th") as HTMLElement;
    resizingRef.current = { col, startX: e.clientX, startW: th.offsetWidth };

    const onMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return;
      const w = Math.max(60, resizingRef.current.startW + ev.clientX - resizingRef.current.startX);
      setColWidths(prev => ({ ...prev, [resizingRef.current!.col]: w }));
    };
    const onUp = () => {
      resizingRef.current = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  return (
    <>
      {/* Data table */}
      <table className="text-xs border-collapse" style={{ minWidth: "100%", width: "max-content" }}>
        <thead className="sticky top-0 z-10">
          <tr>
            {/* Row number column — not sortable/resizable */}
            <th className="px-3 py-2 font-medium text-muted-foreground border-b border-border text-right select-none w-10"
                style={{ backgroundColor: "hsl(var(--muted))" }}>
              #
            </th>
            {result.columns.map((col) => (
              <th
                key={col}
                className="relative px-3 py-2 text-left font-medium text-foreground border-b border-border font-mono cursor-pointer select-none group"
                style={{ backgroundColor: "hsl(var(--muted))", ...(colWidths[col] ? { width: colWidths[col], minWidth: colWidths[col] } : {}) }}
                onClick={() => handleSort(col)}
              >
                <span className="flex items-center gap-1 pr-3 whitespace-nowrap">
                  {col}
                  {sortCol === col
                    ? sortDir === "asc"
                      ? <ChevronUp className="h-3 w-3 text-primary shrink-0" />
                      : <ChevronDown className="h-3 w-3 text-primary shrink-0" />
                    : <ArrowUpDown className="h-3 w-3 shrink-0 opacity-0 group-hover:opacity-40 transition-opacity" />
                  }
                </span>
                {/* Resize handle — right edge of the header cell */}
                <div
                  className="absolute right-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-primary/50 active:bg-primary/80 transition-colors"
                  onMouseDown={(e) => startResize(col, e)}
                />
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {sortedRows.map((row, i) => (
            <tr key={i} className="hover:bg-muted/30 transition-colors">
              <td className="px-3 py-1.5 text-muted-foreground/50 text-right font-mono">{i + 1}</td>
              {row.map((cell, j) => {
                const w = colWidths[result.columns[j]];
                return (
                  <td
                    key={j}
                    className="px-3 py-1.5 font-mono whitespace-nowrap"
                    style={w ? { maxWidth: w, overflow: "hidden", textOverflow: "ellipsis" } : undefined}
                  >
                    {cell === null ? (
                      <span className="italic text-muted-foreground/50">null</span>
                    ) : (
                      <span title={String(cell)}>{String(cell)}</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {result.rows.length === 0 && (
        <div className="py-12 text-center text-xs text-muted-foreground">No results returned.</div>
      )}
    </>
  );
}

export default function QueryPage() {
  const { instance, db, schema } = useSchema();
  const [sql, setSql] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [validationState, setValidationState] = useState<ValidationState>("idle");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [sqlCopied, setSqlCopied] = useState(false);
  const [csvCopied, setCsvCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const executeMut = useExecuteQuery();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const copySql = () => {
    if (!sql) return;
    navigator.clipboard.writeText(sql);
    setSqlCopied(true);
    setTimeout(() => setSqlCopied(false), 2000);
  };

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!sql.trim()) {
      setValidationState("idle");
      setValidationError(null);
      return;
    }
    setValidationState("checking");
    timerRef.current = setTimeout(async () => {
      try {
        const r = await apiClient.post<ValidateResult>("/api/v1/database/validate", { sql, instance, db, schema });
        if (r.valid) { setValidationState("valid"); setValidationError(null); }
        else { setValidationState("invalid"); setValidationError(r.error ?? "Syntax error"); }
      } catch {
        setValidationState("idle");
        setValidationError(null);
      }
    }, 600);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [sql, instance, db, schema]);

  const run = async () => {
    if (!sql.trim()) return;
    setQueryError(null);
    setResult(null);
    try {
      const r = await executeMut.mutateAsync({ sql, instance, db, schema });
      setResult(r);
    } catch (err) {
      let msg: string;
      if (err instanceof ApiError && err.body && typeof err.body === "object") {
        msg = (err.body as { detail?: string }).detail ?? err.message;
      } else {
        msg = err instanceof Error ? err.message : String(err);
      }
      setQueryError(msg);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(); }
  };

  return (
    <div className="flex flex-col p-4 gap-3">
      <div className="flex flex-col gap-2 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">SQL Editor</span>
          <ValidationIcon state={validationState} error={validationError} />
          <span className="flex-1" />
          <span className="text-[10px] text-muted-foreground">Ctrl+Enter to run · SELECT/WITH/EXPLAIN only</span>
          <div className="flex gap-1">
            {EXAMPLES.map((ex) => (
              <Button key={ex.label} size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => setSql(ex.sql)}>
                {ex.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="relative">
          <Textarea
            ref={textareaRef}
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={7}
            placeholder="SELECT * FROM company.products LIMIT 10"
            className="font-mono text-xs resize-none bg-muted/30 border-border focus:ring-1 focus:ring-ring pr-16"
            spellCheck={false}
          />
          {sql && (
            <div className="absolute top-2 right-2 flex gap-0.5">
              <button
                type="button"
                title={sqlCopied ? "Copied!" : "Copy query"}
                onClick={copySql}
                className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
              >
                {sqlCopied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <ClipboardCopy className="h-3.5 w-3.5" />}
              </button>
              <button
                type="button"
                title="Clear editor"
                onClick={() => { setSql(""); setResult(null); setQueryError(null); }}
                className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
              >
                <Eraser className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>

        {validationState === "invalid" && validationError && (
          <p className="flex items-start gap-1.5 text-xs text-destructive font-mono">
            <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            {validationError}
          </p>
        )}

        <div className="flex items-center gap-2">
          <Button size="sm" onClick={run} disabled={executeMut.isPending || !sql.trim()} className="gap-1.5">
            {executeMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Run
          </Button>
          {result && (
            <Badge variant="outline" className="text-emerald-600 border-emerald-500/30 gap-1">
              <CheckCircle2 className="h-3 w-3" /> {result.row_count} row(s) · {result.elapsed_ms}ms
            </Badge>
          )}
          {queryError && (
            <div className="flex items-center gap-1.5 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate max-w-lg">{queryError}</span>
            </div>
          )}
        </div>
      </div>

      {!result && !queryError && (
        <div className="flex items-center justify-center rounded-lg border border-border bg-muted/10 py-12">
          <p className="text-xs text-muted-foreground">Run a query to see the results</p>
        </div>
      )}
      {queryError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <p className="text-xs font-semibold text-destructive mb-1 flex items-center gap-1.5">
            <AlertCircle className="h-3.5 w-3.5" /> Query error
          </p>
          <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono">{queryError}</pre>
        </div>
      )}
      {result && (
        <>
          <div className="flex items-center gap-2 px-1 -mb-1">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
            <span className="text-xs text-muted-foreground flex-1">
              {result.row_count.toLocaleString()} row(s) · {result.elapsed_ms.toFixed(1)} ms
              {result.truncated && <span className="ml-2 text-amber-600 font-medium">(truncated to 1000 rows)</span>}
            </span>
            <Button
              size="sm" variant="ghost" className="h-6 px-2 gap-1 text-xs"
              onClick={() => {
                const header = result.columns.join(",");
                const body = result.rows.map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
                navigator.clipboard.writeText(`${header}\n${body}`);
                setCsvCopied(true);
                setTimeout(() => setCsvCopied(false), 2000);
              }}
            >
              <ClipboardCopy className="h-3 w-3" /> {csvCopied ? "Copied!" : "CSV"}
            </Button>
          </div>
          <div className="rounded-lg border border-border" style={{ maxHeight: "calc(100vh - 370px)", overflow: "auto" }}>
            <ResultsTable result={result} />
          </div>
        </>
      )}
    </div>
  );
}
