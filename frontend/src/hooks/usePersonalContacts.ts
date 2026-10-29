/** Personal contacts: the people on Marcelo's personal WhatsApp, their history with the context of
 * each message, the demands/tasks/notes the Maia proposes from it and her WhatsApp service rules
 * (api/routes/personal_contacts.py, 2026-10-14). */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

const BASE = "/api/v1/personal";

export interface PersonalContact {
  id: string;
  phone: string;
  phone_display: string;
  name: string;
  category: string;
  relation: string;
  birthday: string;
  observations: string;
  who_is: string;
  how_to_treat: string;
  other_data: Record<string, unknown>;
  blocked: boolean;
  last_contact_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  pending_suggestions: number;
  message_count: number;
}

export type ContactInput = Partial<
  Pick<PersonalContact, "name" | "category" | "relation" | "birthday" | "observations" | "who_is" | "how_to_treat" | "blocked">
> & { other_data?: Record<string, unknown> };

export type MessageDirection = "in" | "out" | "note";
export type ContextStatus = "pending" | "done" | "skipped" | "failed";

export interface ContactMessage {
  id: string;
  contact_id: string;
  at: string;
  direction: MessageDirection;
  author: string;
  text: string;
  source: string;
  context: string | null;
  context_status: ContextStatus;
}

export type SuggestionKind = "demand" | "task" | "note";

export interface CaptureSuggestion {
  id: string;
  contact_id: string | null;
  group_id?: string | null;
  source_kind?: 'contact' | 'group';
  group_name?: string;
  group_whatsapp_id?: string;
  source_author?: string | null;
  source_author_id?: string | null;
  source_message_ref?: string | null;
  source_at?: string | null;
  message_id: string | null;
  kind: SuggestionKind;
  title: string;
  details: string;
  status: "pending" | "accepted" | "dismissed";
  created_item_id: string | null;
  decided_at: string | null;
  created_at: string;
  contact_name: string;
  contact_phone: string;
}

export interface AssistantSettings {
  instructions: string;
  wait_minutes: number;
  capture_enabled: boolean;
  updated_at: string;
}

export interface AssistantState {
  paused: { phone: string; name: string; until: string }[];
  open_tasks: { phone: string; name: string; goal: string; created: string; expires_at: string | null }[];
  context_pending: number;
  context_failed: number;
  suggestions_pending: number;
  contacts: number;
  blocked: number;
}

const PAGE = 50;

const keys = {
  all: ["personal"] as const,
  contacts: (q: string, category: string) => ["personal", "contacts", q, category] as const,
  contact: (phone: string) => ["personal", "contact", phone] as const,
  messages: (phone: string) => ["personal", "contact-messages", phone] as const,
  suggestions: (phone: string) => ["personal", "suggestions", phone] as const,
  allSuggestions: (status: string) => ["personal", "suggestions-all", status] as const,
  categories: ["personal", "contact-categories"] as const,
  settings: ["personal", "assistant-settings"] as const,
  state: ["personal", "assistant-state"] as const,
};

function qs(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v) as [string, string][];
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

function useInvalidatePersonal() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: keys.all });
}

export function usePersonalContacts(q: string, category: string) {
  return useQuery<PersonalContact[]>({
    queryKey: keys.contacts(q, category),
    queryFn: () => apiClient.get(`${BASE}/contacts${qs({ q, category })}`),
  });
}

export function usePersonalContact(phone: string | undefined) {
  return useQuery<PersonalContact>({
    queryKey: keys.contact(phone ?? ""),
    queryFn: () => apiClient.get(`${BASE}/contacts/${phone}`),
    enabled: Boolean(phone),
  });
}

/** Newest first, a page at a time (`before` = the oldest message already shown). */
export function useContactMessages(phone: string | undefined) {
  return useInfiniteQuery<ContactMessage[]>({
    queryKey: keys.messages(phone ?? ""),
    enabled: Boolean(phone),
    initialPageParam: undefined,
    queryFn: ({ pageParam }) =>
      apiClient.get(`${BASE}/contacts/${phone}/messages${qs({ limit: String(PAGE), before: pageParam as string | undefined })}`),
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1].at : undefined),
    // Context is written a few seconds after a message arrives: keep it fresh while the tab is open.
    refetchInterval: 30_000,
  });
}

export function useContactSuggestions(phone: string | undefined) {
  return useQuery<CaptureSuggestion[]>({
    queryKey: keys.suggestions(phone ?? ""),
    queryFn: () => apiClient.get(`${BASE}/suggestions${qs({ status: "pending", contact_phone: phone })}`),
    enabled: Boolean(phone),
    refetchInterval: 30_000,
  });
}

/** Global capture inbox; suggestions remain proposals until the explicit decision. */
export function usePersonalSuggestions(status = "pending", groupId?: string) {
  return useInfiniteQuery<CaptureSuggestion[]>({
    queryKey: [...keys.allSuggestions(status), groupId ?? ""],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => apiClient.get(`${BASE}/suggestions${qs({ status, group_id: groupId, limit: String(PAGE), offset: String(pageParam) })}`),
    getNextPageParam: (last, _pages, offset) => (last.length === PAGE ? Number(offset) + PAGE : undefined),
    refetchInterval: 30_000,
  });
}

export function useContactCategories() {
  return useQuery<string[]>({ queryKey: keys.categories, queryFn: () => apiClient.get(`${BASE}/contact-categories`) });
}

export function useCreateContactCategory() {
  const invalidate = useInvalidatePersonal();
  return useMutation<string[], Error, string>({
    mutationFn: (name) => apiClient.post(`${BASE}/contact-categories`, { name }),
    onSettled: invalidate,
  });
}

export function useUpsertContact() {
  const invalidate = useInvalidatePersonal();
  return useMutation<PersonalContact, Error, { phone: string; body: ContactInput }>({
    mutationFn: ({ phone, body }) => apiClient.put(`${BASE}/contacts/${phone}`, body),
    onSettled: invalidate,
  });
}

export function useDeleteContact() {
  const invalidate = useInvalidatePersonal();
  return useMutation<void, Error, string>({
    mutationFn: (phone) => apiClient.delete(`${BASE}/contacts/${phone}`),
    onSettled: invalidate,
  });
}

export function useAddContactNote() {
  const invalidate = useInvalidatePersonal();
  return useMutation<ContactMessage, Error, { phone: string; text: string }>({
    mutationFn: ({ phone, text }) =>
      apiClient.post(`${BASE}/contacts/${phone}/messages`, { text, direction: "note", author: "Marcelo", source: "manual" }),
    onSettled: invalidate,
  });
}

export function useReprocessMessage() {
  const invalidate = useInvalidatePersonal();
  return useMutation<ContactMessage, Error, string>({
    mutationFn: (id) => apiClient.post(`${BASE}/messages/${id}:reprocess`),
    onSettled: invalidate,
  });
}

export function useAcceptSuggestion() {
  const invalidate = useInvalidatePersonal();
  return useMutation<CaptureSuggestion, Error, { id: string; kind?: SuggestionKind; title?: string; details?: string; type_id?: string | null }>({
    mutationFn: ({ id, ...body }) => apiClient.post(`${BASE}/suggestions/${id}:accept`, body),
    onSettled: invalidate,
  });
}

export function useDismissSuggestion() {
  const invalidate = useInvalidatePersonal();
  return useMutation<CaptureSuggestion, Error, string>({
    mutationFn: (id) => apiClient.post(`${BASE}/suggestions/${id}:dismiss`),
    onSettled: invalidate,
  });
}

export function useAssistantSettings() {
  return useQuery<AssistantSettings>({ queryKey: keys.settings, queryFn: () => apiClient.get(`${BASE}/assistant-settings`) });
}

export function useUpdateAssistantSettings() {
  const invalidate = useInvalidatePersonal();
  return useMutation<AssistantSettings, Error, Partial<Pick<AssistantSettings, "instructions" | "wait_minutes" | "capture_enabled">>>({
    mutationFn: (body) => apiClient.put(`${BASE}/assistant-settings`, body),
    onSettled: invalidate,
  });
}

export function useAssistantState() {
  return useQuery<AssistantState>({
    queryKey: keys.state,
    queryFn: () => apiClient.get(`${BASE}/assistant-state`),
    refetchInterval: 60_000,
  });
}
