import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { AgentAccessCard } from "./AgentAccessCard";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), put: vi.fn() } }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "pt-BR" } }),
}));

const agent = { id: "a1", name: "Scriba", slug: "scriba", enabled: false, has_credential: true, last_session_at: null };
const denied = {
  id: "e1", agent: "scriba", event: "request_denied", occurred_at: "2026-11-04T00:00:00Z",
  details: { path: "/api/v1/personal/tasks", ip_address: "127.0.0.1" },
};

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AgentAccessCard />
    </QueryClientProvider>,
  );
}

describe("AgentAccessCard", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(apiClient.get).mockImplementation((url: string) =>
      Promise.resolve(url.includes("audit") ? [denied] : [agent]) as never,
    );
    useAuthStore.setState({ user: { is_admin: true } as never });
  });

  it("allows an agent and shows the audit", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({} as never);
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: "agentAccess.allow" }));
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith("/api/v1/agent-access/a1", { enabled: true }));
    expect(screen.getByText("/api/v1/personal/tasks")).toBeInTheDocument();
  });

  it("is hidden from non-admins", () => {
    useAuthStore.setState({ user: { is_admin: false } as never });
    renderCard();
    expect(screen.queryByText("agentAccess.title")).not.toBeInTheDocument();
  });
});
