import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { AgentMcpAccessCard } from "./AgentMcpAccessCard";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), put: vi.fn() } }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "pt-BR" } }),
}));

const SERVERS = ["forgehub_factory", "forgehub_missions", "forgehub_ops", "forgehub_registry", "forgehub_remote", "forgehub_personal"];

function row(overrides: Record<string, unknown>) {
  return {
    agent_id: "a1", name: "Scriba", profile_slug: "scriba", department: "Documentation", runtime_type: "hermes",
    core_server: "forgehub", servers: ["forgehub_factory"], restart_mode: "approval", query_mode: "approval",
    personal_allowed: false, saved: true,
    suggested: { servers: ["forgehub_factory", "forgehub_missions", "forgehub_ops"], restart_mode: "approval", query_mode: "approval" },
    updated_by: "marcelodarck", updated_at: "2026-11-15T20:00:00Z",
    ...overrides,
  };
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AgentMcpAccessCard />
    </QueryClientProvider>,
  );
}

describe("AgentMcpAccessCard", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(apiClient.get).mockResolvedValue({
      core_server: "forgehub", servers: SERVERS,
      agents: [row({}), row({ agent_id: "m1", name: "Maia", profile_slug: "maia", personal_allowed: true, saved: false })],
    } as never);
    useAuthStore.setState({ user: { is_admin: true } as never });
  });

  it("shows one row per agent and one column per server, Messages always on", async () => {
    renderCard();
    expect(await screen.findByText("Scriba")).toBeInTheDocument();
    for (const short of ["factory", "missions", "ops", "registry", "remote", "personal"]) {
      expect(screen.getByRole("columnheader", { name: short })).toBeInTheDocument();
    }
    const core = screen.getByRole("checkbox", { name: "forgehub — Scriba" });
    expect(core).toBeChecked();
    expect(core).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "forgehub_personal — Scriba" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "forgehub_personal — Maia" })).not.toBeDisabled();
  });

  it("saves what was changed for that agent only", async () => {
    vi.mocked(apiClient.put).mockResolvedValue(row({}) as never);
    renderCard();
    fireEvent.click(await screen.findByRole("checkbox", { name: "forgehub_ops — Scriba" }));
    fireEvent.change(screen.getByRole("combobox", { name: "mcpAccess.restart_mode — Scriba" }), { target: { value: "direct" } });
    const saveButtons = screen.getAllByRole("button", { name: "mcpAccess.save" });
    fireEvent.click(saveButtons[0]);
    await waitFor(() =>
      expect(apiClient.put).toHaveBeenCalledWith("/api/v1/mcp-access/a1", {
        servers: ["forgehub_factory", "forgehub_ops"], restart_mode: "direct", query_mode: "approval",
        expected_updated_at: "2026-11-15T20:00:00Z",
      }),
    );
  });

  it("applies the function's suggestion", async () => {
    vi.mocked(apiClient.put).mockResolvedValue(row({}) as never);
    renderCard();
    fireEvent.click((await screen.findAllByRole("button", { name: "mcpAccess.suggest" }))[0]);
    expect(screen.getByRole("checkbox", { name: "forgehub_missions — Scriba" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "forgehub_ops — Scriba" })).toBeChecked();
  });

  it("is hidden from non-admins", () => {
    useAuthStore.setState({ user: { is_admin: false } as never });
    renderCard();
    expect(screen.queryByText("mcpAccess.title")).not.toBeInTheDocument();
  });
});
