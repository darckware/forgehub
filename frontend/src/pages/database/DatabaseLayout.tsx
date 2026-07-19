import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { ChevronDown, Database } from "lucide-react";
import { useDatabaseInstances, useDatabaseSchemas, useDatabaseTables } from "@/hooks/useDatabase";
import { SchemaProvider, useSchema } from "./SchemaContext";
import { useTranslation } from "react-i18next";

function Select({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="shrink-0">
      <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-0.5">{label}</label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled || options.length === 0}
          className="h-7 pl-2 pr-6 text-xs rounded border border-input bg-background font-mono appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
        >
          {options.length === 0 && <option value="">—</option>}
          {options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
        <ChevronDown className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
      </div>
    </div>
  );
}

function LayoutInner() {
  const { t } = useTranslation();
  const { instance, db, schema, setInstance, setDb, setSchema } = useSchema();
  const { data: instances = [] } = useDatabaseInstances();
  const { data: schemas = [] } = useDatabaseSchemas(instance, db);
  const { data: tables = [] } = useDatabaseTables(schema, instance, db);

  // When instance list loads, ensure selection is valid
  useEffect(() => {
    if (instances.length && !instances.find((i) => i.key === instance)) {
      const first = instances[0];
      setInstance(first.key);
      setDb(first.default_db);
    }
  }, [instances]);  // eslint-disable-line

  // When db resets (after instance change), pick the default
  useEffect(() => {
    if (!db && instances.length) {
      const inst = instances.find((i) => i.key === instance);
      if (inst) setDb(inst.default_db);
    }
  }, [db, instance, instances]);  // eslint-disable-line

  // When schema list loads and current schema is empty/invalid, pick first
  useEffect(() => {
    if (schemas.length && !schema) {
      setSchema(schemas[0]);
    }
  }, [schemas, schema]);  // eslint-disable-line

  const instanceDbs = instances.find((i) => i.key === instance)?.databases ?? [];

  return (
    <div className="flex flex-col flex-1 min-h-0 h-full overflow-hidden">
      <div className="flex items-center gap-4 px-6 py-2.5 border-b border-border shrink-0">
        <Database className="h-5 w-5 text-blue-500 shrink-0" />
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-bold leading-none">{t('database:title')}</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {tables.length} {t('database:tablesCount', { count: tables.length })} · <span className="font-mono">{instance}/{db}/{schema}</span>
          </p>
        </div>

        <div className="flex items-end gap-3 shrink-0">
          <Select
            label="Instance"
            value={instance}
            options={instances.map((i) => i.key)}
            onChange={(v) => {
              const inst = instances.find((i) => i.key === v);
              setInstance(v);
              if (inst) setDb(inst.default_db);
            }}
          />
          <Select
            label="Database"
            value={db}
            options={instanceDbs}
            onChange={setDb}
          />
          <Select
            label="Schema"
            value={schema}
            options={schemas}
            onChange={setSchema}
            disabled={!db}
          />
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}

export default function DatabaseLayout() {
  return (
    <SchemaProvider>
      <LayoutInner />
    </SchemaProvider>
  );
}
