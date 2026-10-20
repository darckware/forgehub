import { useState } from "react";
import {
  useCreateScriptCategory,
  useDeleteScriptCategory,
  useScriptCategories,
  useUpdateScriptCategory,
  type ScriptCategory,
} from "@/hooks/useHostScripts";

/** "Classificações" (Script library): add, rename, describe and delete the
 * classifications scripts are filed under. Delete only an unused one that
 * ForgeHub doesn't ship (the backend enforces the same).
 * idle -> editing -> submitting; deleting -> confirming. */
export interface ScriptCategoriesViewModel {
  status: "loading" | "idle" | "submitting" | "error";
  categories: ScriptCategory[];
  newLabel: string;
  setNewLabel: (value: string) => void;
  newDescription: string;
  setNewDescription: (value: string) => void;
  create: () => void;
  editingId: string | null;
  draftLabel: string;
  setDraftLabel: (value: string) => void;
  draftDescription: string;
  setDraftDescription: (value: string) => void;
  startEdit: (category: ScriptCategory) => void;
  cancelEdit: () => void;
  saveEdit: () => void;
  canDelete: (category: ScriptCategory) => boolean;
  deleting: ScriptCategory | null;
  askDelete: (category: ScriptCategory) => void;
  cancelDelete: () => void;
  confirmDelete: () => void;
  deletePending: boolean;
  error: string | null;
}

export function useScriptCategoriesViewModel(): ScriptCategoriesViewModel {
  const list = useScriptCategories();
  const create = useCreateScriptCategory();
  const update = useUpdateScriptCategory();
  const remove = useDeleteScriptCategory();
  const [newLabel, setNewLabel] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftLabel, setDraftLabel] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [deleting, setDeleting] = useState<ScriptCategory | null>(null);

  const error = create.error?.message ?? update.error?.message ?? remove.error?.message ?? null;
  const status = list.isLoading ? "loading" : create.isPending || update.isPending ? "submitting" : error ? "error" : "idle";
  return {
    status,
    categories: list.data ?? [],
    newLabel,
    setNewLabel,
    newDescription,
    setNewDescription,
    create: () => {
      if (newLabel.trim().length < 2) return;
      create.mutate({ label: newLabel.trim(), description: newDescription.trim() || null }, {
        onSuccess: () => { setNewLabel(""); setNewDescription(""); },
      });
    },
    editingId,
    draftLabel,
    setDraftLabel,
    draftDescription,
    setDraftDescription,
    startEdit: (c) => { update.reset(); setEditingId(c.id); setDraftLabel(c.label); setDraftDescription(c.description ?? ""); },
    cancelEdit: () => setEditingId(null),
    saveEdit: () => {
      if (!editingId || draftLabel.trim().length < 2) return;
      update.mutate({ id: editingId, label: draftLabel.trim(), description: draftDescription.trim() || null }, {
        onSuccess: () => setEditingId(null),
      });
    },
    canDelete: (c) => !c.is_system && !c.script_count,
    deleting,
    askDelete: (c) => { remove.reset(); setDeleting(c); },
    cancelDelete: () => setDeleting(null),
    confirmDelete: () => {
      if (deleting) remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
    },
    deletePending: remove.isPending,
    error,
  };
}
