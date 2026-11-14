import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import type { ServiceRule } from "@/hooks/useServiceRules";
import { ServiceRulesTab } from "./ServiceRulesTab";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "pt-BR" } }),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ApiError: actual.ApiError, apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } };
});

function rule(agent: ServiceRule["agent"], channel: ServiceRule["channel"], state: ServiceRule["file_state"]): ServiceRule {
  const file = `ATENDIMENTO_${channel.toUpperCase()}.md`;
  return {
    agent, channel, file_name: file, file_path: `/root/.hermes/profiles/${agent}/${file}`,
    content: "Regras.", content_hash: "h", chars: 7, max_chars: 10,
    updated_at: null, updated_by: null, file_state: state,
  };
}

const RULES = [
  rule("maia", "whatsapp", "in_sync"),
  rule("lara", "whatsapp", "differs"),
  rule("lara", "site", "missing"),
  rule("lara", "email", "in_sync"),
];

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

let phone = false;

beforeEach(() => {
  phone = false;
  // Desktop width by default: list and editor side by side.
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: phone, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
  vi.mocked(apiClient.get).mockReset();
  vi.mocked(apiClient.get).mockImplementation(async (path: string) => (path.endsWith("/history") ? [] : RULES));
});

describe("ServiceRulesTab", () => {
  it("lists the four pairs with their file state", async () => {
    render(<ServiceRulesTab />, { wrapper: Wrapper });
    expect(await screen.findAllByRole("button", { name: /serviceRules.agents/ })).toHaveLength(4);
    // in_sync x2 in the list + the selected (maia, in_sync) in the editor header
    expect(screen.getAllByText("serviceRules.fileState.in_sync")).toHaveLength(3);
    expect(screen.getByText("serviceRules.fileState.differs")).toBeInTheDocument();
    expect(screen.getByText("serviceRules.fileState.missing")).toBeInTheDocument();
    expect(screen.getByTestId("service-rule-file-path")).toHaveTextContent("/root/.hermes/profiles/maia/ATENDIMENTO_WHATSAPP.md");
  });

  it("explains a differing file when that pair is opened", async () => {
    render(<ServiceRulesTab />, { wrapper: Wrapper });
    const buttons = await screen.findAllByRole("button", { name: /serviceRules.agents/ });
    fireEvent.click(buttons[1]);
    expect(screen.getByText("serviceRules.fileStateHelp.differs")).toBeInTheDocument();
  });

  it("disables Save over the limit", async () => {
    render(<ServiceRulesTab />, { wrapper: Wrapper });
    const editor = await screen.findByRole("textbox");
    const save = screen.getByRole("button", { name: "actions.save" });
    expect(save).toBeDisabled();
    fireEvent.change(editor, { target: { value: "Curto." } });
    expect(save).toBeEnabled();
    fireEvent.change(editor, { target: { value: "x".repeat(11) } });
    expect(save).toBeDisabled();
    expect(screen.getByText(/serviceRules.overLimit/)).toBeInTheDocument();
  });

  it("shows one side at a time on a phone", async () => {
    phone = true;
    render(<ServiceRulesTab />, { wrapper: Wrapper });
    const buttons = await screen.findAllByRole("button", { name: /serviceRules.agents/ });
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.click(buttons[2]);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.queryAllByRole("button", { name: /serviceRules.agents/ })).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: /serviceRules.back/ }));
    expect(screen.getAllByRole("button", { name: /serviceRules.agents/ })).toHaveLength(4);
  });
});
