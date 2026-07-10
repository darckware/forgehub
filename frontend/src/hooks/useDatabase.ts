import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export const DEFAULT_SCHEMA = "company";
export const DEFAULT_INSTANCE = "company_postgres";
export const DEFAULT_DB = "forgehub";

// ---------------------------------------------------------------------------
// Instances
// ---------------------------------------------------------------------------

export interface InstanceInfo {
  key: string;
  label: string;
  databases: string[];
  default_db: string;
}

export function useDatabaseInstances() {
  return useQuery<InstanceInfo[]>({
    queryKey: ["database", "instances"],
    queryFn: () => apiClient.get("/api/v1/database/instances"),
    staleTime: Infinity,
  });
}

export function useDatabaseSchemas(instance = DEFAULT_INSTANCE, db = DEFAULT_DB) {
  return useQuery<string[]>({
    queryKey: ["database", "schemas", instance, db],
    queryFn: () => apiClient.get(`/api/v1/database/schemas?instance=${encodeURIComponent(instance)}&db=${encodeURIComponent(db)}`),
    staleTime: 300_000,
    enabled: !!instance && !!db,
  });
}

export interface TableSummary {
  name: string;
  row_count: number;
  column_count: number;
}

export interface ColumnInfo {
  name: string;
  data_type: string;
  is_nullable: boolean;
  column_default: string | null;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  references: string | null;
}

export interface IndexInfo {
  name: string;
  columns: string[];
  is_unique: boolean;
  is_primary: boolean;
}

export interface TableDetail {
  name: string;
  row_count: number;
  columns: ColumnInfo[];
  indexes: IndexInfo[];
  foreign_keys: { column: string; ref_table: string; ref_column: string }[];
}

export interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
  pk: boolean;
  fk_to: string | null;
}

export interface SchemaTable {
  name: string;
  columns: SchemaColumn[];
  foreign_keys: { column: string; ref_table: string; ref_column: string }[];
}

export interface SchemaOut {
  tables: SchemaTable[];
}

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  elapsed_ms: number;
  truncated: boolean;
}

function buildParams(instance: string, db: string, schema: string, extra?: string) {
  const p = `instance=${encodeURIComponent(instance)}&db=${encodeURIComponent(db)}&schema=${encodeURIComponent(schema)}`;
  return extra ? `${p}&${extra}` : p;
}

export function useDatabaseTables(schema = DEFAULT_SCHEMA, instance = DEFAULT_INSTANCE, db = DEFAULT_DB) {
  return useQuery<TableSummary[]>({
    queryKey: ["database", "tables", instance, db, schema],
    queryFn: () => apiClient.get(`/api/v1/database/tables?${buildParams(instance, db, schema)}`),
    staleTime: 60_000,
    enabled: !!instance && !!db && !!schema,
  });
}

export function useDatabaseTable(table: string | null, schema = DEFAULT_SCHEMA, instance = DEFAULT_INSTANCE, db = DEFAULT_DB) {
  return useQuery<TableDetail>({
    queryKey: ["database", "table", instance, db, schema, table],
    queryFn: () => apiClient.get(`/api/v1/database/tables/${table}?${buildParams(instance, db, schema)}`),
    enabled: !!table && !!instance && !!db && !!schema,
    staleTime: 60_000,
  });
}

export function useDatabaseSchema(schema = DEFAULT_SCHEMA, instance = DEFAULT_INSTANCE, db = DEFAULT_DB) {
  return useQuery<SchemaOut>({
    queryKey: ["database", "schema", instance, db, schema],
    queryFn: () => apiClient.get(`/api/v1/database/schema?${buildParams(instance, db, schema)}`),
    staleTime: 120_000,
  });
}

export function useExecuteQuery() {
  return useMutation<QueryResult, Error, { sql: string; limit?: number; offset?: number; instance?: string; db?: string; schema?: string }>({
    mutationFn: (payload) => apiClient.post("/api/v1/database/query", {
      sql: payload.sql,
      limit: payload.limit ?? 1000,
      offset: payload.offset ?? 0,
      instance: payload.instance ?? DEFAULT_INSTANCE,
      db: payload.db ?? DEFAULT_DB,
      schema: payload.schema ?? DEFAULT_SCHEMA,
    }),
  });
}

// ---------------------------------------------------------------------------
// Functions
// ---------------------------------------------------------------------------

export interface FunctionSummary {
  name: string;
  return_type: string;
  language: string;
  kind: "function" | "procedure";
  arg_types: string;
}

export interface FunctionDetail extends FunctionSummary {
  source: string;
}

export function useDatabaseFunctions(schema = DEFAULT_SCHEMA, instance = DEFAULT_INSTANCE, db = DEFAULT_DB) {
  return useQuery<FunctionSummary[]>({
    queryKey: ["database", "functions", instance, db, schema],
    queryFn: () => apiClient.get(`/api/v1/database/functions?${buildParams(instance, db, schema)}`),
    staleTime: 60_000,
    enabled: !!instance && !!db && !!schema,
  });
}

export function useDatabaseFunction(name: string | null, schema = DEFAULT_SCHEMA, instance = DEFAULT_INSTANCE, db = DEFAULT_DB) {
  return useQuery<FunctionDetail>({
    queryKey: ["database", "function", instance, db, schema, name],
    queryFn: () => apiClient.get(`/api/v1/database/functions/${name}?${buildParams(instance, db, schema)}`),
    enabled: !!name && !!instance && !!db && !!schema,
    staleTime: 60_000,
  });
}

export function useCreateFunction() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean; message: string }, Error, { source: string }>({
    mutationFn: (payload) => apiClient.post("/api/v1/database/functions", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["database", "functions"] }),
  });
}

export function useDropFunction() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean }, Error, string>({
    mutationFn: (name) => apiClient.delete(`/api/v1/database/functions/${name}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["database", "functions"] }),
  });
}

// ---------------------------------------------------------------------------
// Indexes
// ---------------------------------------------------------------------------

export interface IndexGlobal {
  name: string;
  table_name: string;
  columns: string;
  is_unique: boolean;
  is_primary: boolean;
  index_def: string;
}

export interface IndexCreate {
  table_name: string;
  column_names: string[];
  index_name?: string;
  unique?: boolean;
}

export function useDatabaseIndexes(schema = DEFAULT_SCHEMA, instance = DEFAULT_INSTANCE, db = DEFAULT_DB) {
  return useQuery<IndexGlobal[]>({
    queryKey: ["database", "indexes", instance, db, schema],
    queryFn: () => apiClient.get(`/api/v1/database/indexes?${buildParams(instance, db, schema)}`),
    staleTime: 60_000,
    enabled: !!instance && !!db && !!schema,
  });
}

export function useCreateIndex() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean; name: string }, Error, IndexCreate>({
    mutationFn: (payload) => apiClient.post("/api/v1/database/indexes", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["database", "indexes"] }),
  });
}

export function useDropIndex() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean }, Error, string>({
    mutationFn: (name) => apiClient.delete(`/api/v1/database/indexes/${name}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["database", "indexes"] }),
  });
}

// ---------------------------------------------------------------------------
// Tables — structured create
// ---------------------------------------------------------------------------

export interface ColumnDef {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  default: string;
}

export function useCreateTable() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean; sql: string }, Error, { name: string; columns: ColumnDef[] }>({
    mutationFn: (payload) => apiClient.post("/api/v1/database/tables", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["database", "tables"] }),
  });
}
