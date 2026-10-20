import { useState } from "react";
import { useSaveTailnetPolicy, useTailnetPolicy, type TailnetPolicyState } from "@/hooks/useVpn";

/** Tailnet policy card: view the recorded policy (or an older version), its
 * analysis, and record a newly pasted copy. viewing <-> editing -> saving. */
export interface TailnetPolicyViewModel {
  status: "loading" | "error" | "empty" | "viewing" | "editing" | "saving";
  state: TailnetPolicyState | undefined;
  selectedVersionId: string | null;
  selectVersion: (id: string | null) => void;
  showContent: boolean;
  toggleContent: () => void;
  draft: string;
  setDraft: (value: string) => void;
  note: string;
  setNote: (value: string) => void;
  startEditing: () => void;
  cancelEditing: () => void;
  save: () => void;
  saveError: string | null;
  copiedSnippet: boolean;
  copySnippet: () => void;
}

export function useTailnetPolicyViewModel(): TailnetPolicyViewModel {
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const query = useTailnetPolicy(selectedVersionId);
  const save = useSaveTailnetPolicy();
  const [editing, setEditing] = useState(false);
  const [showContent, setShowContent] = useState(false);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [copiedSnippet, setCopiedSnippet] = useState(false);

  const status = query.isLoading
    ? "loading"
    : query.isError
      ? "error"
      : save.isPending
        ? "saving"
        : editing
          ? "editing"
          : query.data?.current
            ? "viewing"
            : "empty";

  return {
    status,
    state: query.data,
    selectedVersionId,
    selectVersion: (id) => {
      setSelectedVersionId(id);
      setShowContent(true);
    },
    showContent,
    toggleContent: () => setShowContent((v) => !v),
    draft,
    setDraft,
    note,
    setNote,
    startEditing: () => {
      save.reset();
      setDraft(query.data?.current?.content ?? "");
      setNote("");
      setEditing(true);
    },
    cancelEditing: () => setEditing(false),
    save: () =>
      save.mutate(
        { content: draft, note: note.trim() || null },
        {
          onSuccess: () => {
            setEditing(false);
            setSelectedVersionId(null);
          },
        },
      ),
    saveError: save.error?.message ?? null,
    copiedSnippet,
    copySnippet: () => {
      const snippet = query.data?.current?.analysis?.snippet;
      if (!snippet) return;
      void navigator.clipboard.writeText(snippet);
      setCopiedSnippet(true);
      setTimeout(() => setCopiedSnippet(false), 1500);
    },
  };
}
