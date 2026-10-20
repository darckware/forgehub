import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import ClientAccountPage from "./[id]";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

const CLIENT = {
  id: "c1",
  company_name: "HW CLUBE DE TIROS ESPORTIVO LTDA",
  contact_name: "Alessandra Monteiro",
  email: "clubedetirogatling@gmail.com",
  is_active: true,
  must_change_password: true,
  last_login_at: null,
  contacts: [
    { id: "k1", name: "Alessandra Monteiro", email: "clubedetirogatling@gmail.com", phone: "+55 21 99824-2448", department: "Diretoria", is_authorized: true, is_primary: true },
  ],
  contracts: [],
  open_tickets: 0,
  open_demands: 0,
  converted_from_leads: [],
  cnpj: "45.498.857/0001-11",
  trade_name: null,
  company_phone: null,
  address_street: "ROD PRESIDENTE DUTRA",
  address_number: "280",
  address_complement: null,
  address_district: "CENTRO",
  address_city: "NOVA IGUACU",
  address_state: "RJ",
  address_zip: "26285-000",
  history: [
    { id: "h1", event_type: "alteracao", note: "Campos alterados: phone, cnpj", actor: "agente:lara", created_at: "2026-10-06T15:03:00Z" },
    { id: "h2", event_type: "nota", note: "Nome fantasia vazio no documento.", actor: "forgehub:marcelo", created_at: "2026-10-06T15:04:00Z" },
  ],
};

function renderPage() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/clients/c1")) return CLIENT as never;
    if (url.endsWith("/factory")) return { products: [], projects: [], unlinked_products: [] } as never;
    return { items: [], total: 0 } as never;
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/client-accounts/c1"]}>
        <Routes>
          <Route path="/client-accounts/:id" element={<ClientAccountPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("client page: company registry and history (2026-10-06)", () => {
  it("shows CNPJ, address, missing fields and the translated history", async () => {
    await i18n.changeLanguage("pt-BR");
    renderPage();
    const company = (await screen.findByText("Dados da empresa")).closest("div.space-y-3") as HTMLElement;
    expect(within(company).getByText("45.498.857/0001-11")).toBeInTheDocument();
    expect(within(company).getByText("ROD PRESIDENTE DUTRA, 280 · CENTRO · NOVA IGUACU/RJ · CEP 26285-000")).toBeInTheDocument();
    expect(within(company).getAllByText("Não informado")).toHaveLength(2); // trade name, company phone
    expect(within(company).queryByText("Completar cadastro")).not.toBeInTheDocument();

    expect(screen.getByText("Alterou: Telefone do contato, CNPJ")).toBeInTheDocument();
    expect(screen.getByText("Nome fantasia vazio no documento.")).toBeInTheDocument();
    expect(screen.getByText("agente:lara")).toBeInTheDocument();
  });

  it("opens the edit form with the registry filled in", async () => {
    await i18n.changeLanguage("pt-BR");
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Editar dados/ }));
    expect(await screen.findByLabelText("CNPJ")).toHaveValue("45.498.857/0001-11");
    expect(screen.getByLabelText("CEP")).toHaveValue("26285-000");
    expect(screen.getByLabelText("Nome fantasia")).toHaveValue("");
  });
});
