import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { ProductSaleCard } from "./ProductSaleCard";

vi.mock("@/lib/api", () => ({ apiClient: { post: vi.fn() } }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

function renderCard(offeredForSaleAt: string | null) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ProductSaleCard productId="p1" offeredForSaleAt={offeredForSaleAt} />
    </QueryClientProvider>,
  );
}

describe("ProductSaleCard", () => {
  beforeEach(() => {
    vi.mocked(apiClient.post).mockReset();
  });

  it("offers the product straight from the button", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({});
    renderCard(null);
    fireEvent.click(screen.getByRole("button", { name: "sale.offer" }));
    await waitFor(() =>
      expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/products/p1:offer-for-sale", {}),
    );
  });

  it("asks before taking the product off sale", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({});
    renderCard("2026-11-04T00:00:00Z");
    fireEvent.click(screen.getByRole("button", { name: "sale.withdraw" }));
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(screen.getByText("sale.withdrawDialog.title")).toBeInTheDocument();
  });

  it("shows the failure", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new Error("502"));
    renderCard(null);
    fireEvent.click(screen.getByRole("button", { name: "sale.offer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("sale.error");
  });
});
