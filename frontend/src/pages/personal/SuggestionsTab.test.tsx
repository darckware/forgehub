import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SuggestionsTab } from "./SuggestionsTab";

const bulkAcceptMutate = vi.fn().mockResolvedValue({ affected: 2 });
const bulkDismissMutate = vi.fn().mockResolvedValue({ affected: 2 });
const deleteMutate = vi.fn().mockResolvedValue(undefined);
const cleanupMutate = vi.fn().mockResolvedValue({ affected: 5 });

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}:${JSON.stringify(opts)}` : key,
    i18n: { language: "pt-BR" },
  }),
}));

vi.mock("@/hooks/usePersonalContacts", () => ({
  usePersonalSuggestions: () => ({
    data: {
      pages: [
        [
          {
            id: "sug-1",
            contact_id: "c-1",
            source_kind: "contact",
            message_id: "m-1",
            kind: "task",
            title: "Enviar boleto",
            details: "Até sexta",
            status: "pending",
            created_item_id: null,
            decided_at: null,
            created_at: "2026-11-20T10:00:00Z",
            contact_name: "Ana",
            contact_phone: "5521999999999",
          },
          {
            id: "sug-2",
            contact_id: "c-1",
            source_kind: "contact",
            message_id: "m-2",
            kind: "demand",
            title: "Reforma da sala",
            details: "",
            status: "pending",
            created_item_id: null,
            decided_at: null,
            created_at: "2026-11-19T10:00:00Z",
            contact_name: "Ana",
            contact_phone: "5521999999999",
          },
        ],
      ],
    },
    isLoading: false,
    isError: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    refetch: vi.fn(),
    fetchNextPage: vi.fn(),
  }),
  usePersonalSuggestionCounts: () => ({
    data: {
      pending: 426,
      accepted: 3,
      dismissed: 13,
      all: 442,
      older_than_15_days: 356,
    },
  }),
  useAcceptSuggestion: () => ({ mutate: vi.fn(), isPending: false }),
  useDismissSuggestion: () => ({ mutate: vi.fn(), isPending: false }),
  useBulkAcceptSuggestions: () => ({ mutateAsync: bulkAcceptMutate, isPending: false }),
  useBulkDismissSuggestions: () => ({ mutateAsync: bulkDismissMutate, isPending: false }),
  useDeleteSuggestions: () => ({ mutate: vi.fn(), mutateAsync: deleteMutate, isPending: false }),
  useCleanupSuggestions: () => ({ mutateAsync: cleanupMutate, isPending: false }),
}));

describe("SuggestionsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("displays status counts differentiating Pendente and Todas and shows breakdown on Todas", () => {
    render(<SuggestionsTab />);
    expect(screen.getByRole("button", { name: "suggestions.status.pending (426)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "suggestions.status.accepted (3)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "suggestions.status.dismissed (13)" })).toBeInTheDocument();
    const allBtn = screen.getByRole("button", { name: "suggestions.all (442)" });
    expect(allBtn).toBeInTheDocument();

    fireEvent.click(allBtn);
    expect(
      screen.getByText('suggestions.allSummary:{"pending":426,"accepted":3,"dismissed":13}'),
    ).toBeInTheDocument();
  });

  it("supports bulk accepting all pending suggestions and 15-day cleanup", async () => {
    render(<SuggestionsTab />);

    const acceptAllBtn = screen.getByRole("button", { name: 'suggestions.acceptAll:{"count":426}' });
    fireEvent.click(acceptAllBtn);

    const confirmButtons = screen.getAllByRole("button", { name: "contacts.suggestions.accept" });
    fireEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(bulkAcceptMutate).toHaveBeenCalledWith({ ids: undefined, all_pending: true });
    });

    const cleanupBtn = screen.getByRole("button", { name: 'suggestions.cleanup15DaysCount:{"count":356}' });
    fireEvent.click(cleanupBtn);
    fireEvent.click(screen.getByRole("button", { name: "suggestions.cleanupConfirm" }));

    await waitFor(() => {
      expect(cleanupMutate).toHaveBeenCalledWith({ keep_days: 15 });
    });
  });

  it("supports selecting individual suggestions to delete or dismiss", async () => {
    render(<SuggestionsTab />);

    const checkbox = screen.getByRole("checkbox", { name: 'suggestions.select:{"title":"Enviar boleto"}' });
    fireEvent.click(checkbox);

    const deleteSelectedBtn = screen.getByRole("button", { name: 'suggestions.deleteSelected:{"count":1}' });
    fireEvent.click(deleteSelectedBtn);
    fireEvent.click(screen.getByRole("button", { name: "delete.confirm" }));

    await waitFor(() => {
      expect(deleteMutate).toHaveBeenCalledWith(["sug-1"]);
    });
  });
});
