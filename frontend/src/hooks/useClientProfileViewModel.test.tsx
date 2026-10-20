import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import { apiClient } from "@/lib/api";

import { changedFields, clientAccountSchema, clientAddressLine, cnpjIsValid, type ClientSummary } from "./useClientOps";
import { clientFormDefaults, portalState, registrationDefaults, useClientProfileViewModel } from "./useClientProfileViewModel";

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

describe("client registry (2026-10-06)", () => {
  it("validates CNPJ check digits, CEP and UF", () => {
    expect(cnpjIsValid("45.498.857/0001-11")).toBe(true);
    expect(cnpjIsValid("45.498.857/0004-11")).toBe(false); // OCR misread
    expect(cnpjIsValid("11111111111111")).toBe(false);
    const base = { company_name: "HW", contact_name: "Alessandra", email: "a@b.com" };
    expect(clientAccountSchema.safeParse({ ...base, cnpj: "45498857000411" }).success).toBe(false);
    expect(clientAccountSchema.safeParse({ ...base, address_zip: "2628-500" }).success).toBe(false);
    expect(clientAccountSchema.safeParse({ ...base, address_state: "R" }).success).toBe(false);
    const ok = clientAccountSchema.safeParse({ ...base, cnpj: "", address_state: "rj", address_zip: "26.285-000" });
    expect(ok.success && ok.data.address_state).toBe("RJ");
  });

  it("fills the form with the registry and shows a one-line address", () => {
    const client = { ...CLIENT, cnpj: "45.498.857/0001-11", address_street: "ROD PRESIDENTE DUTRA", address_number: "280", address_district: "CENTRO", address_city: "NOVA IGUACU", address_state: "RJ", address_zip: "26285-000" };
    const form = clientFormDefaults(client);
    expect(form.cnpj).toBe("45.498.857/0001-11");
    expect(form.trade_name).toBe("");
    expect(clientAddressLine(client)).toBe("ROD PRESIDENTE DUTRA, 280 · CENTRO · NOVA IGUACU/RJ · CEP 26285-000");
    expect(clientAddressLine(CLIENT)).toBeNull();
  });

  it("reads Darckware's change notes", () => {
    expect(changedFields("Campos alterados: phone, cnpj")).toEqual(["phone", "cnpj"]);
    expect(changedFields("Cliente cadastrado.")).toBeNull();
  });
});

describe("client registration asked by an agent (2026-10-06)", () => {
  const REG = {
    id: "r1",
    status: "proposta" as const,
    proposed_by: "agente:lara",
    payload: { company_name: "Clube Beta", contact_name: "Bia", email: "bia@beta.com.br", cnpj: "45.498.857/0001-11", note: "Pelo WhatsApp" },
    decided_by: null,
    decided_at: null,
    decision_note: null,
    client_account_id: null,
    created_at: null,
  };

  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
  });

  it("fills the form with what the agent proposed", () => {
    const form = registrationDefaults(REG);
    expect(form.company_name).toBe("Clube Beta");
    expect(form.cnpj).toBe("45.498.857/0001-11");
    expect(form.trade_name).toBe("");
    expect("note" in form).toBe(false);
  });

  it("approves through the registration route and reports the new client", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...CLIENT, id: "new-client" });
    const { result } = renderHook(() => useClientProfileViewModel(), { wrapper });
    act(() => result.current.openApprove(REG));
    expect(result.current.dialog).toEqual({ mode: "approve", registration: REG });
    await act(() => result.current.submit({ ...registrationDefaults(REG), company_name: "Clube Beta Ltda" }));
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/client-ops/registrations/r1:approve",
      expect.objectContaining({ company_name: "Clube Beta Ltda", cnpj: "45.498.857/0001-11" }),
    );
    expect(result.current.createdId).toBe("new-client");
    expect(result.current.dialog).toBeUndefined();
  });

  it("rejects only with a reason", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...REG, status: "rejeitada" });
    const { result } = renderHook(() => useClientProfileViewModel(), { wrapper });
    act(() => result.current.requestReject(REG));
    await act(() => result.current.confirmReject());
    expect(apiClient.post).not.toHaveBeenCalled();
    act(() => result.current.setRejectReason("Não é cliente"));
    await act(() => result.current.confirmReject());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/registrations/r1:reject", { reason: "Não é cliente" });
    expect(result.current.rejecting).toBeUndefined();
  });
});

