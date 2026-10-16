import { useMemo, useState } from "react";
import {
  useArchiveHostScript,
  useCreateScriptCategory,
  useHostScript,
  useHostScripts,
  useSaveHostScript,
  useScriptCategories,
  type HostScript,
  type ScriptParameter,
  type ScriptPlatform,
  type ScriptRisk,
} from "@/hooks/useHostScripts";

/** Script library: browse by classification/platform, create and edit
 * (a content change is a new version), archive, add a classification. */
export interface ScriptDraft {
  name: string;
  category_id: string;
  description: string;
  platform: ScriptPlatform;
  risk: ScriptRisk;
  timeout_seconds: number;
  parameters: ScriptParameter[];
  content: string;
  note: string;
}

export interface ScriptLibraryViewModel {
  status: "loading" | "error" | "ready";
  categories: { id: string; label: string }[];
  categoryFilter: string;
  setCategoryFilter: (id: string) => void;
  platformFilter: string;
  setPlatformFilter: (value: string) => void;
  showArchived: boolean;
  setShowArchived: (value: boolean) => void;
  query: string;
  setQuery: (value: string) => void;
  grouped: { categoryId: string; label: string; scripts: HostScript[] }[];
  // editor
  editingId: string | null; // "new" for a new script
  draft: ScriptDraft | null;
  setDraft: (patch: Partial<ScriptDraft>) => void;
  addParameter: () => void;
  updateParameter: (index: number, patch: Partial<ScriptParameter>) => void;
  removeParameter: (index: number) => void;
  startNew: () => void;
  startEdit: (script: HostScript) => void;
  cancelEdit: () => void;
  save: () => void;
  saving: boolean;
  saveError: string | null;
  versionsOf: string | null;
  showVersions: (id: string | null) => void;
  versions: { version: number; content: string; changed_by: string; note: string | null; created_at: string }[];
  toggleArchive: (script: HostScript) => void;
  newCategory: string;
  setNewCategory: (value: string) => void;
  addCategory: () => void;
  categoryError: string | null;
}

const EMPTY: ScriptDraft = {
  name: "", category_id: "", description: "", platform: "windows", risk: "read",
  timeout_seconds: 300, parameters: [], content: "", note: "",
};

export function useScriptLibraryViewModel(): ScriptLibraryViewModel {
  const [showArchived, setShowArchived] = useState(false);
  const scripts = useHostScripts(showArchived);
  const categoryQuery = useScriptCategories();
  const saveScript = useSaveHostScript();
  const archive = useArchiveHostScript();
  const createCategory = useCreateScriptCategory();
  const [categoryFilter, setCategoryFilter] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraftState] = useState<ScriptDraft | null>(null);
  const [versionsOf, setVersionsOf] = useState<string | null>(null);
  const detail = useHostScript(versionsOf);
  const [newCategory, setNewCategory] = useState("");

  const categories = (categoryQuery.data ?? []).map((c) => ({ id: c.id, label: c.label }));
  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = (scripts.data ?? []).filter((s) =>
      (!categoryFilter || s.category_id === categoryFilter)
      && (!platformFilter || s.platform === platformFilter)
      && (!q || [s.name, s.description].some((v) => v?.toLowerCase().includes(q))),
    );
    return categories
      .map((c) => ({ categoryId: c.id, label: c.label, scripts: list.filter((s) => s.category_id === c.id) }))
      .filter((g) => g.scripts.length > 0);
  }, [scripts.data, categories, categoryFilter, platformFilter, query]);

  return {
    status: scripts.isLoading || categoryQuery.isLoading ? "loading" : scripts.isError ? "error" : "ready",
    categories,
    categoryFilter,
    setCategoryFilter,
    platformFilter,
    setPlatformFilter,
    showArchived,
    setShowArchived,
    query,
    setQuery,
    grouped,
    editingId,
    draft,
    setDraft: (patch) => setDraftState((cur) => (cur ? { ...cur, ...patch } : cur)),
    addParameter: () =>
      setDraftState((cur) => cur && { ...cur, parameters: [...cur.parameters, { name: "", label: "", required: false, default: null, secret: false }] }),
    updateParameter: (index, patch) =>
      setDraftState((cur) => cur && { ...cur, parameters: cur.parameters.map((p, i) => (i === index ? { ...p, ...patch } : p)) }),
    removeParameter: (index) =>
      setDraftState((cur) => cur && { ...cur, parameters: cur.parameters.filter((_, i) => i !== index) }),
    startNew: () => {
      saveScript.reset();
      setEditingId("new");
      setDraftState({ ...EMPTY, category_id: categoryFilter || categories[0]?.id || "" });
    },
    startEdit: (script) => {
      saveScript.reset();
      setEditingId(script.id);
      setDraftState({
        name: script.name, category_id: script.category_id, description: script.description ?? "",
        platform: script.platform, risk: script.risk, timeout_seconds: script.timeout_seconds,
        parameters: script.parameters, content: script.content, note: "",
      });
    },
    cancelEdit: () => {
      setEditingId(null);
      setDraftState(null);
    },
    save: () => {
      if (!draft) return;
      const data = {
        ...draft,
        description: draft.description.trim() || null,
        note: draft.note.trim() || null,
        parameters: draft.parameters
          .filter((p) => p.name.trim())
          .map((p) => ({ ...p, name: p.name.trim().toUpperCase(), label: p.label?.trim() || null, default: p.default?.trim() || null })),
      };
      saveScript.mutate(
        { id: editingId === "new" ? null : editingId, data },
        { onSuccess: () => { setEditingId(null); setDraftState(null); } },
      );
    },
    saving: saveScript.isPending,
    saveError: saveScript.error?.message ?? null,
    versionsOf,
    showVersions: setVersionsOf,
    versions: detail.data?.versions ?? [],
    toggleArchive: (script) => archive.mutate({ id: script.id, archived: !script.archived }),
    newCategory,
    setNewCategory,
    addCategory: () =>
      createCategory.mutate({ label: newCategory.trim() }, { onSuccess: (c) => { setNewCategory(""); setDraftState((cur) => cur && { ...cur, category_id: c.id }); } }),
    categoryError: createCategory.error?.message ?? null,
  };
}
