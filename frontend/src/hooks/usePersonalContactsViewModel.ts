/** ViewModels of the Pessoal page's "Contatos" and "Maia" tabs (§21): state and actions here, the
 * page renders them. Contacts are the Maia's WhatsApp contacts; their history carries the context of
 * each message, and the demands/tasks/notes she proposes only become real when Marcelo accepts them. */
import { useEffect, useMemo, useState } from "react";
import {
  useAcceptSuggestion,
  useAddContactNote,
  useAssistantSettings,
  useAssistantState,
  useContactCategories,
  useContactMessages,
  useContactSuggestions,
  useDeleteContact,
  useDismissSuggestion,
  usePersonalContact,
  usePersonalContacts,
  useReprocessMessage,
  useUpdateAssistantSettings,
  useUpsertContact,
  type ContactInput,
  type PersonalContact,
  type SuggestionKind,
} from "./usePersonalContacts";

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** The editable part of a contact's record. */
export interface ContactDraft {
  name: string;
  category: string;
  relation: string;
  birthday: string;
  observations: string;
  who_is: string;
  how_to_treat: string;
  blocked: boolean;
}

const BIRTHDAY = /^\d{2}\/\d{2}(\/\d{4})?$/;

export function draftOf(c: PersonalContact): ContactDraft {
  return {
    name: c.name,
    category: c.category,
    relation: c.relation,
    birthday: c.birthday,
    observations: c.observations,
    who_is: c.who_is,
    how_to_treat: c.how_to_treat,
    blocked: c.blocked,
  };
}

/** Only the fields that changed, so an edit never overwrites what the Maia wrote meanwhile. */
export function changedFields(original: PersonalContact, draft: ContactDraft): ContactInput {
  const changes: ContactInput = {};
  (Object.keys(draft) as (keyof ContactDraft)[]).forEach((key) => {
    const value = typeof draft[key] === "string" ? (draft[key] as string).trim() : draft[key];
    if (value !== original[key]) (changes as Record<string, unknown>)[key] = value;
  });
  return changes;
}

export type ContactsStatus = "loading" | "ready" | "editing" | "submitting" | "confirming" | "error";

export function usePersonalContactsViewModel() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [onlyWithSuggestions, setOnlyWithSuggestions] = useState(false);
  const [selectedPhone, setSelectedPhone] = useState<string>();
  const [draft, setDraft] = useState<ContactDraft | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [kindChoice, setKindChoice] = useState<Record<string, SuggestionKind>>({});

  const list = usePersonalContacts(search.trim(), category);
  const categories = useContactCategories();
  const contact = usePersonalContact(selectedPhone);
  const messages = useContactMessages(selectedPhone);
  const suggestions = useContactSuggestions(selectedPhone);
  const upsert = useUpsertContact();
  const addNote = useAddContactNote();
  const accept = useAcceptSuggestion();
  const dismiss = useDismissSuggestion();
  const reprocess = useReprocessMessage();
  const remove = useDeleteContact();

  // Leaving the contact (or it reloading after a save) drops an unsaved edit only on purpose.
  useEffect(() => {
    setDraft(null);
    setNote("");
    setError(null);
  }, [selectedPhone]);

  const contacts = useMemo(() => {
    const all = list.data ?? [];
    return onlyWithSuggestions ? all.filter((c) => c.pending_suggestions > 0) : all;
  }, [list.data, onlyWithSuggestions]);
  const birthdayError = draft && draft.birthday.trim() && !BIRTHDAY.test(draft.birthday.trim()) ? "birthday" : null;
  const submitting = upsert.isPending || addNote.isPending || remove.isPending;

  let status: ContactsStatus = "ready";
  if (list.isLoading) status = "loading";
  else if (submitting) status = "submitting";
  else if (confirmDelete) status = "confirming";
  else if (draft) status = "editing";
  else if (error) status = "error";

  return {
    status,
    search,
    setSearch,
    category,
    setCategory,
    onlyWithSuggestions,
    setOnlyWithSuggestions,
    categories: categories.data ?? [],
    contacts,
    listError: list.isError ? errorText(list.error) : null,
    selectedPhone,
    select(phone: string | undefined) {
      setSelectedPhone(phone);
    },
    contact: contact.data,
    contactLoading: contact.isLoading && Boolean(selectedPhone),
    messages: messages.data?.pages.flat() ?? [],
    messagesLoading: messages.isLoading,
    hasMoreMessages: Boolean(messages.hasNextPage),
    loadingMoreMessages: messages.isFetchingNextPage,
    loadMoreMessages: () => void messages.fetchNextPage(),
    suggestions: suggestions.data ?? [],
    error,
    dismissError: () => setError(null),

    draft,
    birthdayError,
    startEdit() {
      if (contact.data) setDraft(draftOf(contact.data));
    },
    setDraft,
    cancelEdit: () => setDraft(null),
    async saveEdit() {
      if (!contact.data || !draft || birthdayError) return;
      const changes = changedFields(contact.data, draft);
      try {
        if (Object.keys(changes).length) await upsert.mutateAsync({ phone: contact.data.phone, body: changes });
        setDraft(null);
        setError(null);
      } catch (e) {
        setError(errorText(e));
      }
    },

    note,
    setNote,
    async addNote() {
      if (!contact.data || !note.trim()) return;
      try {
        await addNote.mutateAsync({ phone: contact.data.phone, text: note.trim() });
        setNote("");
      } catch (e) {
        setError(errorText(e));
      }
    },

    kindFor: (id: string, fallback: SuggestionKind) => kindChoice[id] ?? fallback,
    setKindFor: (id: string, kind: SuggestionKind) => setKindChoice((k) => ({ ...k, [id]: kind })),
    busySuggestion: accept.isPending ? accept.variables?.id : dismiss.isPending ? dismiss.variables : undefined,
    async acceptSuggestion(id: string, kind: SuggestionKind) {
      try {
        await accept.mutateAsync({ id, kind });
      } catch (e) {
        setError(errorText(e));
      }
    },
    async dismissSuggestion(id: string) {
      try {
        await dismiss.mutateAsync(id);
      } catch (e) {
        setError(errorText(e));
      }
    },
    reprocessing: reprocess.isPending ? reprocess.variables : undefined,
    reprocess: (id: string) => void reprocess.mutateAsync(id).catch((e) => setError(errorText(e))),

    confirmDelete,
    askDelete: () => setConfirmDelete(true),
    cancelDelete: () => setConfirmDelete(false),
    deleting: remove.isPending,
    async deleteContact() {
      if (!contact.data) return;
      try {
        await remove.mutateAsync(contact.data.phone);
        setConfirmDelete(false);
        setSelectedPhone(undefined);
      } catch (e) {
        setConfirmDelete(false);
        setError(errorText(e));
      }
    },
  };
}

export type PersonalContactsViewModel = ReturnType<typeof usePersonalContactsViewModel>;

/* ---------------------------------------------------------------- the Maia's rules */

export interface MaiaDraft {
  instructions: string;
  wait_minutes: string;
  capture_enabled: boolean;
}

export function useMaiaSettingsViewModel() {
  const settings = useAssistantSettings();
  const state = useAssistantState();
  const update = useUpdateAssistantSettings();
  const [draft, setDraft] = useState<MaiaDraft | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The form starts from what is stored and follows it until Marcelo starts typing.
  const current: MaiaDraft | null = draft ?? (settings.data
    ? { instructions: settings.data.instructions, wait_minutes: String(settings.data.wait_minutes), capture_enabled: settings.data.capture_enabled }
    : null);
  const minutes = Number(current?.wait_minutes);
  const minutesError = current && (!Number.isInteger(minutes) || minutes < 0 || minutes > 240) ? "minutes" : null;
  const dirty = Boolean(
    draft && settings.data &&
      (draft.instructions !== settings.data.instructions ||
        Number(draft.wait_minutes) !== settings.data.wait_minutes ||
        draft.capture_enabled !== settings.data.capture_enabled),
  );

  return {
    loading: settings.isLoading,
    form: current,
    updatedAt: settings.data?.updated_at,
    state: state.data,
    dirty,
    saved,
    error,
    minutesError,
    submitting: update.isPending,
    change(patch: Partial<MaiaDraft>) {
      if (!current) return;
      setSaved(false);
      setDraft({ ...current, ...patch });
    },
    discard: () => setDraft(null),
    async save() {
      if (!draft || minutesError) return;
      try {
        await update.mutateAsync({
          instructions: draft.instructions,
          wait_minutes: Number(draft.wait_minutes),
          capture_enabled: draft.capture_enabled,
        });
        setDraft(null);
        setSaved(true);
        setError(null);
      } catch (e) {
        setError(errorText(e));
      }
    },
  };
}

export type MaiaSettingsViewModel = ReturnType<typeof useMaiaSettingsViewModel>;
