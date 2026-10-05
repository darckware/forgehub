import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import { apiClient } from "@/lib/api";

import { useClientEmailApprovalViewModel } from "./useClientEmailApprovalViewModel";

/** What apiClient throws when Darckware refuses: the coded detail from client_ops. */
function darckwareRefusal(reason: string) {
  return Object.assign(new Error("Request failed with status 422"), {
    status: 422,
    body: { detail: { code: "darckware_rejected", message: reason, params: { reason } } },
  });
}

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

const EMAIL = {
  id: "e1",
  status: "aguardando_aprovacao",
  kind: "pendencia",
  to_email: "ana@acme.com.br",
  subject: "Precisamos do acesso",
  body_text: "Olá",
  version: 2,
  body_hash: "h".repeat(64),
  source_system: "forgehub",
  created_by: "forgehub:marcelo",
  approval_valid: false,
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useClientEmailApprovalViewModel", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.patch).mockReset();
    vi.mocked(apiClient.get).mockImplementation(async (path: string) =>
      path.startsWith("/api/v1/client-ops/emails/") ? EMAIL : { items: [EMAIL], total: 1 },
    );
  });

  it("lists the pending queue by default", async () => {
    const { result } = renderHook(() => useClientEmailApprovalViewModel(), { wrapper });
    await waitFor(() => expect(result.current.emails).toHaveLength(1));
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/client-ops/emails?status=aguardando_aprovacao%2Cfalhou%2Cenvio_incerto",
    );
  });

  it("approves the exact version and hash being shown, after confirmation", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...EMAIL, status: "aprovado" });
    const { result } = renderHook(() => useClientEmailApprovalViewModel(), { wrapper });
    act(() => result.current.select("e1"));
    await waitFor(() => expect(result.current.selected?.id).toBe("e1"));
    expect(result.current.canApprove).toBe(true);

    act(() => result.current.requestApprove());
    expect(result.current.dialog).toBe("approve");
    expect(apiClient.post).not.toHaveBeenCalled();

    await act(() => result.current.confirmApprove());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/emails/e1:approve", {
      version: 2,
      body_hash: EMAIL.body_hash,
    });
    expect(result.current.dialog).toBeUndefined();
  });

  it("keeps the edit form open when saving fails", async () => {
    vi.mocked(apiClient.patch).mockRejectedValue(darckwareRefusal("Destinatário não vinculado"));
    const { result } = renderHook(() => useClientEmailApprovalViewModel(), { wrapper });
    act(() => result.current.select("e1"));
    await waitFor(() => expect(result.current.selected?.id).toBe("e1"));
    act(() => result.current.startEdit());
    act(() => result.current.setDraft({ to_email: "outro@x.com" }));
    await act(() => result.current.saveEdit());
    expect(result.current.editing).toBe(true);
    expect(result.current.errorMessage).toContain("Destinatário não vinculado");
    expect(result.current.draft.to_email).toBe("outro@x.com");
  });

  it("will not reject without a reason", async () => {
    const { result } = renderHook(() => useClientEmailApprovalViewModel(), { wrapper });
    act(() => result.current.select("e1"));
    await waitFor(() => expect(result.current.selected?.id).toBe("e1"));
    act(() => result.current.requestReject());
    await act(() => result.current.confirmReject());
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
