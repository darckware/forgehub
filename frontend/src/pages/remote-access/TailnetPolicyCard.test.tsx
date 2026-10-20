import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { TailnetPolicyCard } from "./TailnetPolicyCard";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

const POLICY = {
  id: "p1", note: "inicial", saved_by: "marcelodarck", created_at: "2026-10-16T12:00:00Z", content: "{ }", parse_error: null,
  analysis: {
    client_tags: ["tag:gatling-users", "tag:semed-users"], tags_with_ssh: ["tag:semed-users"], missing_ssh: ["tag:gatling-users"],
    snippet: '{\n    "src": ["tag:darckware-infra"],\n}', style: "grants", warnings: [], server_tag: "tag:darckware-infra",
  },
};

function renderCard(state: unknown) {
  vi.mocked(apiClient.get).mockResolvedValue(state as never);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><TailnetPolicyCard /></QueryClientProvider>);
}

describe("TailnetPolicyCard", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("shows which client tags the server can't reach and the rule to add", async () => {
    renderCard({ current: POLICY, versions: [POLICY] });
    expect(await screen.findByText(/não pode abrir SSH em 1 tag de cliente/)).toBeInTheDocument();
    expect(screen.getByText("tag:gatling-users")).toBeInTheDocument();
    expect(screen.getByText(/"src": \["tag:darckware-infra"\]/)).toBeInTheDocument();
    expect(screen.getByText(/Onde colar: dentro de "grants"/)).toBeInTheDocument();
  });

  it("records a pasted policy", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(POLICY as never);
    renderCard({ current: null, versions: [] });
    fireEvent.click(await screen.findByRole("button", { name: "Registrar política" }));
    fireEvent.change(screen.getByLabelText("Política (HuJSON)"), { target: { value: '{"tagOwners": {}}' } });
    fireEvent.change(screen.getByLabelText("Nota da versão"), { target: { value: "cópia de hoje" } });
    fireEvent.click(screen.getByRole("button", { name: "Registrar" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/vpn/policy", {
      content: '{"tagOwners": {}}', note: "cópia de hoje",
    }));
  });
});
