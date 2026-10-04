import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { actionBody } from "./useClientOps";
import { useClientDemandsViewModel } from "./useClientDemandsViewModel";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const ITEM = {
  kind: "ticket" as const,
  id: "t1",
  title: "Impressora parada",
  tipo: "servico" as const,
  status: "aberto",
  stage: "novo" as const,
  requester_email: "ana@acme.com.br",
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("actionBody", () => {
  it("sends the text under the field each action expects", () => {
    expect(actionBody("resolve", "Trocado o toner")).toEqual({ resolution: "Trocado o toner", email: undefined });
    expect(actionBody("reopen", "Voltou")).toEqual({ reason: "Voltou" });
    expect(actionBody("wait-customer", "")).toEqual({ note: undefined, email: undefined });
  });
});

describe("useClientDemandsViewModel", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path.endsWith("/factory")) return { products: [{ id: "pr1", name: "Sistema ACME", status: "active" }], projects: [], unlinked_products: [] };
      if (path.startsWith("/api/v1/client-ops/work-items/"))
        return { ...ITEM, client_account_id: "c1", company_name: "ACME", timeline: [], time_entries: [], emails: [], project: null };
      return { items: [ITEM], total: 1, by_stage: { novo: 1 } };
    });
  });

  it("starts on open items", async () => {
    const { result } = renderHook(() => useClientDemandsViewModel(), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/client-ops/work-items?stage=open");
  });

  it("requires a resolution and a complete e-mail before resolving", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...ITEM, queued_email: { id: "e9" } });
    const { result } = renderHook(() => useClientDemandsViewModel(), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    act(() => result.current.select(result.current.items[0]));
    await waitFor(() => expect(result.current.detail?.id).toBe("t1"));

    act(() => result.current.openAction("resolve"));
    expect(result.current.draft?.withEmail).toBe(true);
    expect(result.current.draft?.to_email).toBe("ana@acme.com.br");
    expect(result.current.canSubmitAction).toBe(false);

    act(() => result.current.updateDraft({ text: "Trocado o toner" }));
    expect(result.current.canSubmitAction).toBe(false); // e-mail body still empty
    act(() => result.current.updateDraft({ body_text: "Resolvido." }));
    expect(result.current.canSubmitAction).toBe(true);

    await act(() => result.current.submitAction());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/work-items/ticket/t1:resolve", {
      resolution: "Trocado o toner",
      email: { subject: "Re: Impressora parada", body_text: "Resolvido.", to_email: "ana@acme.com.br" },
    });
    expect(result.current.draft).toBeUndefined();
    expect(result.current.lastQueuedEmail).toBe("e9");
  });

  it("keeps the dialog open with the error when the action fails", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new Error("Destinatário não vinculado"));
    const { result } = renderHook(() => useClientDemandsViewModel(), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    act(() => result.current.select(result.current.items[0]));
    await waitFor(() => expect(result.current.detail?.id).toBe("t1"));
    act(() => result.current.openAction("start"));
    await act(() => result.current.submitAction());
    expect(result.current.draft?.action).toBe("start");
    expect(result.current.errorMessage).toBe("Destinatário não vinculado");
  });

  it("opens a project under the client's only product by default", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ project: { id: "pj1" }, product: { id: "pr1" } });
    const { result } = renderHook(() => useClientDemandsViewModel(), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(1));
    act(() => result.current.select(result.current.items[0]));
    await waitFor(() => expect(result.current.projectProducts).toHaveLength(1));

    act(() => result.current.openCreateProject());
    expect(result.current.projectDraft).toMatchObject({ productChoice: "existing", productId: "pr1", projectName: ITEM.title });
    expect(result.current.canSubmitProject).toBe(true);
    await act(() => result.current.submitCreateProject());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/work-items/ticket/t1:create-project", {
      product_id: "pr1",
      project_name: ITEM.title,
    });
    expect(result.current.projectDraft).toBeUndefined();
  });
});
