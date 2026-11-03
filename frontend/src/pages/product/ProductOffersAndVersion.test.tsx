import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import "@/i18n";
import { apiClient } from "@/lib/api";
import { productInputSchema } from "@/hooks/useProduct";
import { CommercialOffersCard } from "./CommercialOffersCard";
import SystemFormPage from "../systems/SystemFormPage";

vi.mock("@/lib/api", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const MOCK_OFFERS = [
  {
    id: "offer-pro",
    name: "Oferta Pro",
    slug: "pro",
    category: "saas",
    description: "Plano profissional",
    is_active: true,
    base_monthly_price: 250,
    available_modules: ["base"],
    forgehub_product_id: "prod-1",
    forgehub_product_name: "Ecossistema Foundation",
  },
  {
    id: "offer-starter",
    name: "Oferta Starter",
    slug: "starter",
    category: "saas",
    description: "Plano inicial",
    is_active: true,
    base_monthly_price: 100,
    available_modules: ["base"],
    forgehub_product_id: null,
    forgehub_product_name: null,
  },
];

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

describe("CommercialOffersCard and Product Detail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows linked offers and links an unlinked offer", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === "/api/v1/client-ops/software-products") {
        return MOCK_OFFERS as never;
      }
      return [] as never;
    });

    vi.mocked(apiClient.put).mockImplementation(async (_url: string, body: any) => {
      return { ...MOCK_OFFERS[1], ...body } as never;
    });

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <CommercialOffersCard productId="prod-1" />
      </QueryClientProvider>
    );

    // Linked offer should be visible
    expect(await screen.findByText("Oferta Pro")).toBeInTheDocument();
    expect(screen.getByText("Plano profissional")).toBeInTheDocument();

    // Click "Ligar oferta"
    const linkButton = screen.getByRole("button", { name: /Ligar oferta/i });
    fireEvent.click(linkButton);

    // Unlinked offer should be in the selector
    const select = await screen.findByRole("combobox");
    expect(select).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "offer-starter" } });

    // Confirm link
    const confirmButton = screen.getByRole("button", { name: /Vincular/i });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(apiClient.put).toHaveBeenCalledWith(
        "/api/v1/client-ops/software-products/offer-starter/forgehub-link",
        { forgehub_product_id: "prod-1" }
      );
    });
  });

  it("unlinks an offer with confirm dialog", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === "/api/v1/client-ops/software-products") {
        return MOCK_OFFERS as never;
      }
      return [] as never;
    });

    vi.mocked(apiClient.put).mockImplementation(async (_url: string, body: any) => {
      return { ...MOCK_OFFERS[0], ...body } as never;
    });

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <CommercialOffersCard productId="prod-1" />
      </QueryClientProvider>
    );

    expect(await screen.findByText("Oferta Pro")).toBeInTheDocument();

    // Click "Desligar"
    const unlinkButton = screen.getByRole("button", { name: /Desligar/i });
    fireEvent.click(unlinkButton);

    // Confirm dialog should appear
    const dialogConfirmButton = await screen.findByRole("button", {
      name: "Desligar oferta",
    });
    fireEvent.click(dialogConfirmButton);

    await waitFor(() => {
      expect(apiClient.put).toHaveBeenCalledWith(
        "/api/v1/client-ops/software-products/offer-pro/forgehub-link",
        { forgehub_product_id: null }
      );
    });
  });
});

describe("System creation form sends initial_version", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("submits initial_version {version, status} on create product", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.includes("/clients")) return { items: [] } as never;
      if (url === "/api/v1/products") return [] as never;
      if (url === "/api/v1/projects") return [] as never;
      return [] as never;
    });

    vi.mocked(apiClient.post).mockImplementation(async (url: string, body: any) => {
      if (url === "/api/v1/products") {
        return {
          id: "prod-new-1",
          name: body.name,
          versions: [{ id: "ver-new-1", version: body.initial_version?.version }],
        } as never;
      }
      if (url === "/api/v1/projects") {
        return { id: "proj-new-1" } as never;
      }
      return {} as never;
    });

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={["/systems/novo"]}>
          <Routes>
            <Route path="/systems/novo" element={<SystemFormPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Fill form
    const nameInput = await screen.findByLabelText(/Nome do Sistema/i);
    fireEvent.change(nameInput, { target: { value: "Ecossistema Foundation" } });

    const versionInput = screen.getByLabelText(/Versão Inicial/i);
    fireEvent.change(versionInput, { target: { value: "2026.11" } });

    const statusSelect = screen.getByLabelText(/Estado da Versão/i);
    fireEvent.change(statusSelect, { target: { value: "planned" } });

    // Submit
    const submitButton = screen.getByRole("button", { name: /Cadastrar Sistema/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/api/v1/products",
        expect.objectContaining({
          name: "Ecossistema Foundation",
          initial_version: {
            version: "2026.11",
            status: "planned",
          },
        })
      );
    });
  });

  it("validates productInputSchema includes initial_version", () => {
    const parsed = productInputSchema.parse({
      name: "Ecossistema Foundation",
      initial_version: {
        version: "2026.11",
        status: "planned",
      },
    });
    expect(parsed.initial_version).toEqual({
      version: "2026.11",
      status: "planned",
    });
  });
});
