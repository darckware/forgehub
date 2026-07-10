import { createContext, useContext, useState } from "react";
import { DEFAULT_SCHEMA } from "@/hooks/useDatabase";

export const DEFAULT_INSTANCE = "company_postgres";
export const DEFAULT_DB = "forgehub";

interface SchemaContextValue {
  instance: string;
  db: string;
  schema: string;
  setInstance: (s: string) => void;
  setDb: (s: string) => void;
  setSchema: (s: string) => void;
}

const SchemaContext = createContext<SchemaContextValue>({
  instance: DEFAULT_INSTANCE,
  db: DEFAULT_DB,
  schema: DEFAULT_SCHEMA,
  setInstance: () => undefined,
  setDb: () => undefined,
  setSchema: () => undefined,
});

export function SchemaProvider({ children }: { children: React.ReactNode }) {
  const [instance, setInstanceState] = useState(DEFAULT_INSTANCE);
  const [db, setDbState] = useState(DEFAULT_DB);
  const [schema, setSchema] = useState(DEFAULT_SCHEMA);

  const setInstance = (i: string) => {
    setInstanceState(i);
    // Reset db and schema when instance changes
    setDbState("");
    setSchema("");
  };

  const setDb = (d: string) => {
    setDbState(d);
    setSchema("");
  };

  return (
    <SchemaContext.Provider value={{ instance, db, schema, setInstance, setDb, setSchema }}>
      {children}
    </SchemaContext.Provider>
  );
}

export function useSchema() {
  return useContext(SchemaContext);
}
