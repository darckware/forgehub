import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import type { PersonalContact } from "./usePersonalContacts";
import { changedFields, draftOf, useMaiaSettingsViewModel, usePersonalContactsViewModel } from "./usePersonalContactsViewModel";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const CONTACT: PersonalContact = {
  id: "c1", phone: "5521999991234", phone_display: "+55 21 99999-1234", name: "Ana", category: "familia",
  relation: "irmã", birthday: "03/05", observations: "", who_is: "Irmã.", how_to_treat: "", other_data: {},
  blocked: false, last_contact_at: null, created_by: "maia", created_at: "", updated_at: "",
  pending_suggestions: 1, message_count: 2,
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("changedFields", () => {
  it("sends only what changed, trimmed", () => {
    const draft = { ...draftOf(CONTACT), name: " Ana Maria ", blocked: true };
    expect(changedFields(CONTACT, draft)).toEqual({ name: "Ana Maria", blocked: true });
    expect(changedFields(CONTACT, draftOf(CONTACT))).toEqual({});
  });
});

describe("usePersonalContactsViewModel", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path.includes("/messages")) return [];
      if (path.includes("/suggestions")) return [];
      if (path.endsWith("/contact-categories")) return ["familia", "amigos"];
      if (path.startsWith("/api/v1/personal/contacts/")) return CONTACT;
      return [CONTACT, { ...CONTACT, id: "c2", phone: "5521888881234", pending_suggestions: 0 }];
    });
  });

  it("filters to contacts with suggestions and saves only changed fields", async () => {
    vi.mocked(apiClient.put).mockResolvedValue(CONTACT);
    const { result } = renderHook(() => usePersonalContactsViewModel(), { wrapper });
    await waitFor(() => expect(result.current.contacts).toHaveLength(2));
    act(() => result.current.setOnlyWithSuggestions(true));
    expect(result.current.contacts.map((c) => c.id)).toEqual(["c1"]);

    act(() => result.current.select(CONTACT.phone));
    await waitFor(() => expect(result.current.contact?.id).toBe("c1"));
    act(() => result.current.startEdit());
    act(() => result.current.setDraft({ ...result.current.draft!, birthday: "maio" }));
    expect(result.current.birthdayError).toBe("birthday");
    act(() => result.current.setDraft({ ...result.current.draft!, birthday: "03/05", relation: "irmã mais velha" }));
    await act(() => result.current.saveEdit());
    expect(apiClient.put).toHaveBeenCalledWith("/api/v1/personal/contacts/5521999991234", { relation: "irmã mais velha" });
    expect(result.current.draft).toBeNull();
  });
});

describe("useMaiaSettingsViewModel", () => {
  it("is not dirty until edited and validates the wait", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (path: string) =>
      path.endsWith("/assistant-settings")
        ? { instructions: "Seja breve.", wait_minutes: 5, capture_enabled: true, updated_at: "2026-10-14T10:00:00Z" }
        : { paused: [], open_tasks: [], context_pending: 0, context_failed: 0, suggestions_pending: 0, contacts: 0, blocked: 0 },
    );
    vi.mocked(apiClient.put).mockResolvedValue({ instructions: "Seja breve.", wait_minutes: 10, capture_enabled: true, updated_at: "" });
    const { result } = renderHook(() => useMaiaSettingsViewModel(), { wrapper });
    await waitFor(() => expect(result.current.form?.instructions).toBe("Seja breve."));
    expect(result.current.dirty).toBe(false);
    act(() => result.current.change({ wait_minutes: "999" }));
    expect(result.current.minutesError).toBe("minutes");
    act(() => result.current.change({ wait_minutes: "10" }));
    expect(result.current.dirty).toBe(true);
    await act(() => result.current.save());
    expect(apiClient.put).toHaveBeenCalledWith("/api/v1/personal/assistant-settings", {
      instructions: "Seja breve.", wait_minutes: 10, capture_enabled: true });
    expect(result.current.saved).toBe(true);
  });
});
