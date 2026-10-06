import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import { apiClient } from "@/lib/api";

import type { ClientSummary } from "./useClientOps";
import { clientFormDefaults, portalState, useClientProfileViewModel } from "./useClientProfileViewModel";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

const CLIENT: ClientSummary = {
  id: "c1",
  company_name: "Padaria Estrela",
  contact_name: "Joana",
  email: "joana@estrela.com.br",
  is_active: true,
  must_change_password: true,
  last_login_at: null,
  contacts: [{ id: "k1", name: "Joana", email: "joana@estrela.com.br", phone: "2199", department: "Diretoria", is_authorized: true, is_primary: true }],
  contracts: [],
  open_tickets: 0,
  open_demands: 0,
  converted_from_leads: [],
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useClientProfileViewModel", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.patch).mockReset();
  });

  it("creates a client without sending empty fields", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...CLIENT, id: "new" });
    const { result } = renderHook(() => useClientProfileViewModel(), { wrapper });
    act(() => result.current.openCreate());
    await act(() =>
      result.current.submit({ company_name: "Padaria Estrela", contact_name: "Joana", email: "joana@estrela.com.br", phone: "", department: "" }),
    );
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/clients", {
      company_name: "Padaria Estrela",
      contact_name: "Joana",
      email: "joana@estrela.com.br",
    });
    expect(result.current.createdId).toBe("new");
    expect(result.current.dialog).toBeUndefined();
  });

  it("asks before issuing portal access and shows the password once", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ client_id: "c1", login: CLIENT.email, temporary_password: "abcd-efgh-jkmn", must_change_password: true });
    const { result } = renderHook(() => useClientProfileViewModel("c1"), { wrapper });
    act(() => result.current.requestPortalAccess());
    expect(result.current.status).toBe("confirming");
    expect(apiClient.post).not.toHaveBeenCalled();
    await act(() => result.current.confirmAction());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/clients/c1:portal-access", {});
    expect(result.current.issued?.temporary_password).toBe("abcd-efgh-jkmn");
    act(() => result.current.closeAccess());
    expect(result.current.issued).toBeUndefined();
  });

  it("deactivates only after confirmation", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ ...CLIENT, is_active: false });
    const { result } = renderHook(() => useClientProfileViewModel("c1"), { wrapper });
    act(() => result.current.requestActivation(false));
    await act(() => result.current.confirmAction());
    expect(apiClient.patch).toHaveBeenCalledWith("/api/v1/client-ops/clients/c1", { is_active: false });
  });
});

describe("portalState and defaults", () => {
  it("reads the portal from login history and fills the form from the primary contact", () => {
    expect(portalState(CLIENT)).toBe("notUsed");
    expect(portalState({ ...CLIENT, last_login_at: "2026-10-05T10:00:00Z" })).toBe("mustChange");
    expect(portalState({ ...CLIENT, last_login_at: "2026-10-05T10:00:00Z", must_change_password: false })).toBe("active");
    expect(clientFormDefaults(CLIENT).phone).toBe("2199");
  });
});
