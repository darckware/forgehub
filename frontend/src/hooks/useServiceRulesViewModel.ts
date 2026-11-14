/**
 * ViewModel for Pessoal -> "Regras de atendimento" (§21 pattern, see useImprovePromptViewModel.ts).
 *
 * One editor for the four agent + channel documents. The draft follows what is stored until
 * Marcelo types; a save sends `expected_hash` = the stored item's `content_hash`, so a save on top
 * of someone else's newer version comes back 409 SERVICE_RULE_CHANGED and becomes `conflict`
 * (the draft is kept on screen, saving is blocked, and `reload` brings the stored version back).
 * Switching to another pair with unsaved changes asks first (`pendingKey` -> ConfirmDialog).
 */
import { useMemo, useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import {
  serviceRuleKey,
  serviceRulesKey,
  useSaveServiceRule,
  useServiceRuleHistory,
  useServiceRules,
  type ServiceRule,
  type ServiceRuleHistoryEntry,
} from "./useServiceRules";

export type ServiceRulesStatus = "loading" | "idle" | "saving" | "error" | "conflict";

export interface ServiceRulesViewModel {
  status: ServiceRulesStatus;
  /** Load error of the list itself (not a save error). */
  loadError: string | null;
  rules: ServiceRule[];
  selectedKey: string | null;
  selected: ServiceRule | null;
  /** What the editor shows: the draft, or the stored content when nothing was typed. */
  text: string;
  dirty: boolean;
  chars: number;
  maxChars: number;
  overLimit: boolean;
  empty: boolean;
  canSave: boolean;
  /** Save error message (status "error"). */
  error: string | null;
  /** True right after a successful save, until the next edit. */
  saved: boolean;
  history: ServiceRuleHistoryEntry[];
  historyLoading: boolean;
  historyError: string | null;
  /** A pair the user tried to open while there were unsaved changes. */
  pendingKey: string | null;
  select: (key: string) => void;
  confirmSwitch: () => void;
  cancelSwitch: () => void;
  change: (text: string) => void;
  discard: () => void;
  save: () => Promise<void>;
  reload: () => Promise<void>;
  /** After a conflict: load the newer version but keep this draft, to save it over that version. */
  keepMine: () => Promise<void>;
}

const DEFAULT_MAX_CHARS = 9000;

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = (e.body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") {
      return detail.message;
    }
    if (Array.isArray(detail) && detail[0] && typeof detail[0].msg === "string") return detail[0].msg;
  }
  return e instanceof Error ? e.message : String(e);
}

function isConflict(e: unknown): boolean {
  if (!(e instanceof ApiError) || e.status !== 409) return false;
  const detail = (e.body as { detail?: { code?: string } } | null)?.detail;
  return detail?.code === "SERVICE_RULE_CHANGED";
}

export function useServiceRulesViewModel(): ServiceRulesViewModel {
  const qc = useQueryClient();
  const list = useServiceRules();
  const save = useSaveServiceRule();
  const rules = useMemo(() => list.data ?? [], [list.data]);

  const [chosenKey, setChosenKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "error" | "conflict">("idle");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const selected = rules.find((r) => serviceRuleKey(r) === chosenKey) ?? rules[0] ?? null;
  const selectedKey = selected ? serviceRuleKey(selected) : null;
  const history = useServiceRuleHistory(selected?.agent, selected?.channel);

  const text = draft ?? selected?.content ?? "";
  const dirty = draft !== null && selected !== null && draft !== selected.content;
  const maxChars = selected?.max_chars ?? DEFAULT_MAX_CHARS;
  const chars = text.length;
  const overLimit = chars > maxChars;
  const empty = text.trim().length === 0;
  const saving = save.isPending;
  // Leaving the page with unsaved rules asks first (switching pairs has its own guard).
  useEffect(() => {
    if (draft === null) return undefined;
    const onBeforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [draft]);

  const canSave = Boolean(selected) && dirty && !overLimit && !empty && !saving && status !== "conflict";

  function resetEditor() {
    setDraft(null);
    setStatus("idle");
    setError(null);
    setSaved(false);
  }

  function open(key: string) {
    setChosenKey(key);
    setPendingKey(null);
    resetEditor();
  }

  return {
    status: list.isLoading ? "loading" : saving ? "saving" : status,
    loadError: list.isError ? errorText(list.error) : null,
    rules,
    selectedKey,
    selected,
    text,
    dirty,
    chars,
    maxChars,
    overLimit,
    empty,
    canSave,
    error,
    saved,
    history: history.data ?? [],
    historyLoading: history.isLoading,
    historyError: history.isError ? errorText(history.error) : null,
    pendingKey,
    select(key) {
      if (key === selectedKey) return;
      if (dirty) setPendingKey(key);
      else open(key);
    },
    confirmSwitch() {
      if (pendingKey) open(pendingKey);
    },
    cancelSwitch: () => setPendingKey(null),
    change(next) {
      setSaved(false);
      if (status === "error") {
        setStatus("idle");
        setError(null);
      }
      setDraft(next);
    },
    discard: resetEditor,
    async save() {
      if (!selected || !canSave) return;
      try {
        await save.mutateAsync({
          agent: selected.agent,
          channel: selected.channel,
          content: text,
          expected_hash: selected.content_hash,
        });
        setDraft(null);
        setStatus("idle");
        setError(null);
        setSaved(true);
      } catch (e) {
        setSaved(false);
        if (isConflict(e)) {
          setStatus("conflict");
          setError(null);
        } else {
          setStatus("error");
          setError(errorText(e));
        }
      }
    },
    async reload() {
      await qc.invalidateQueries({ queryKey: serviceRulesKey });
      resetEditor();
    },
    async keepMine() {
      await qc.invalidateQueries({ queryKey: serviceRulesKey });
      setStatus("idle");
      setError(null);
    },
  };
}
