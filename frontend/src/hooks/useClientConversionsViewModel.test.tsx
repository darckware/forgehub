import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import { apiClient } from "@/lib/api";

import { contractSchema, conversionBody, type ConversionInput } from "./useClientOps";
import { conversionDefaults, useClientConversionsViewModel } from "./useClientConversionsViewModel";
import { contractDefaults, useClientAccountViewModel } from "./useClientAccountViewModel";

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

const PROPOSAL = {
  id: "p1",
  lead_id: "l1",
  proposed_by: "lara",
  status: "proposta" as const,
  payload: {
    company_name: "Clube Gatling",
    contact_name: "Roberto",
    email: "r@gatling.com.br",
    notes: "Aceitou por WhatsApp",
    contract: { contract_type: "suporte_horas" as const, plan_name: "Plano 8 Horas", monthly_hours_quota: 8, monthly_price: 900 },
  },
};

const INPUT: ConversionInput = {
  company_name: "Clube Gatling",
  contact_name: "Roberto",
  email: "r@gatling.com.br",
  phone: "",
  department: "",
  existing_client_account_id: "",
  contract: { contract_type: "suporte_horas", plan_name: "Plano 8 Horas", monthly_hours_quota: 8, monthly_price: 950, start_date: "" },
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("contractSchema", () => {
  it("requires quota and price only for hourly support", () => {
    expect(contractSchema.safeParse({ contract_type: "suporte_horas", plan_name: "x" }).success).toBe(false);
    expect(
      contractSchema.safeParse({ contract_type: "suporte_horas", plan_name: "x", monthly_hours_quota: 4, monthly_price: 600 }).success,
    ).toBe(true);
    expect(contractSchema.safeParse({ contract_type: "desenvolvimento", plan_name: "Site", total_value: 5000 }).success).toBe(true);
  });

  it("treats empty number inputs as unset and rejects an end before the start", () => {
    const parsed = contractSchema.safeParse({ contract_type: "desenvolvimento", plan_name: "x", total_value: Number.NaN });
    expect(parsed.success && parsed.data.total_value).toBe(undefined);
    expect(
      contractSchema.safeParse({ contract_type: "desenvolvimento", plan_name: "x", start_date: "2026-10-05", end_date: "2026-10-01" })
        .success,
    ).toBe(false);
  });
});

describe("conversionBody", () => {
  it("drops empty fields so Darckware never gets blank strings", () => {
    const body = conversionBody(INPUT);
    expect(body.existing_client_account_id).toBeUndefined();
    expect(body.data).not.toHaveProperty("phone");
    expect(body.data.contract).not.toHaveProperty("start_date");
    expect(body.data.contract.monthly_price).toBe(950);
  });
});

describe("useClientConversionsViewModel", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.get).mockImplementation(async (path: string) =>
      path.includes("/leads")
        ? { leads: [{ id: "l2", name: "Ana" }, { id: "l3", name: "Já cliente", client_account_id: "c9" }] }
        : { items: [PROPOSAL] },
    );
  });

  it("pre-fills the form from Lara's proposal", () => {
    const defaults = conversionDefaults({ mode: "approve", proposal: PROPOSAL });
    expect(defaults.company_name).toBe("Clube Gatling");
    expect(defaults.contract.monthly_hours_quota).toBe(8);
  });

  it("approves the proposal with the edited data", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ client_account_id: "c1", contract: {}, welcome_email_id: "e1" });
    const { result } = renderHook(() => useClientConversionsViewModel(), { wrapper });
    await waitFor(() => expect(result.current.proposals).toHaveLength(1));
    act(() => result.current.openProposal(result.current.proposals[0]));
    expect(result.current.status).toBe("editing");
    await act(() => result.current.submit(INPUT));
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/conversions/p1:approve", conversionBody(INPUT));
    expect(result.current.dialog).toBeUndefined();
    expect(result.current.lastResult?.welcome_email_id).toBe("e1");
  });

  it("keeps the dialog open on a conflict and hides already converted leads", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(darckwareRefusal("Já existe cliente com o e-mail"));
    const { result } = renderHook(() => useClientConversionsViewModel(), { wrapper });
    act(() => result.current.openLeadPicker());
    await waitFor(() => expect(result.current.leads.map((l) => l.id)).toEqual(["l2"]));
    act(() => result.current.pickLead(result.current.leads[0]));
    await act(() => result.current.submit(INPUT));
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/leads/l2:convert", expect.any(Object));
    expect(result.current.dialog?.mode).toBe("convert");
    expect(result.current.errorMessage).toContain("Já existe cliente");
  });
});

describe("useClientAccountViewModel", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.patch).mockReset();
    vi.mocked(apiClient.get).mockResolvedValue({
      id: "c1",
      company_name: "ACME",
      contacts: [],
      contracts: [{ id: "k1", contract_type: "suporte_horas", status: "ativo", plan_name: "Plano 8 Horas", monthly_hours_quota: 8 }],
      open_tickets: 0,
      open_demands: 0,
      converted_from_leads: [],
    });
  });

  it("asks before changing a contract's status and never sends the type on edit", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({});
    const { result } = renderHook(() => useClientAccountViewModel("c1"), { wrapper });
    await waitFor(() => expect(result.current.client?.contracts).toHaveLength(1));
    const contract = result.current.client!.contracts[0];

    act(() => result.current.requestStatusChange(contract, "encerrado"));
    expect(result.current.status).toBe("confirming");
    expect(apiClient.patch).not.toHaveBeenCalled();
    await act(() => result.current.confirmStatusChange());
    expect(apiClient.patch).toHaveBeenCalledWith("/api/v1/client-ops/contracts/k1", { status: "encerrado" });

    act(() => result.current.openEditContract(contract));
    await act(() => result.current.submitContract({ ...contractDefaults(contract), monthly_price: 1000 }));
    const changes = vi.mocked(apiClient.patch).mock.calls[1][1] as Record<string, unknown>;
    expect(changes).not.toHaveProperty("contract_type");
    expect(changes.monthly_price).toBe(1000);
  });
});
