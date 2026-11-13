import { fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useMissionPhaseMutation } from "@/hooks/useMissions";
import { MissionDecisionsCard } from "./MissionDecisionsCard";

const plan = {
  kind: "plan_approval", mission_project_id: "m1", mission_name: "Portal", title: "Plano: plan v1",
  summary: "plan v1 · 3 tarefa(s)", requested_at: "2026-11-13T10:00:00Z", requested_by: "Athos",
  approval_request_id: "req-1", project_plan_id: "plan-1", task_count: 3, phase_id: null,
  phase_position: null, phase_name: null, homologation_evidence: [], link: "/missions/m1",
};
const phase = {
  kind: "phase_approval", mission_project_id: "m2", mission_name: "CRM", title: "Fase 1 · Estrutura",
  summary: "Testei a navegação", requested_at: "2026-11-13T11:00:00Z", requested_by: null,
  approval_request_id: null, project_plan_id: null, task_count: null, phase_id: "ph-1", phase_position: 1,
  phase_name: "Estrutura", homologation_evidence: ["git:abc123"], link: "/missions/m2",
};

function setAdmin(isAdmin: boolean) {
  useAuthStore.setState({ user: { id: "u1", username: "marcelo", email: null, full_name: null,
    avatar_data_url: null, totp_enabled: false, is_active: true, is_admin: isAdmin,
    profile_id: null, ui_language: "pt-BR" } });
}

let client: QueryClient;

function open() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><MissionDecisionsCard /></MemoryRouter></QueryClientProvider>);
}

const get = vi.fn();
const post = vi.fn();

beforeEach(async () => {
  await i18n.changeLanguage("pt-BR");
  setAdmin(true);
  get.mockReset(); post.mockReset();
  vi.spyOn(apiClient, "get").mockImplementation(get);
  vi.spyOn(apiClient, "post").mockImplementation(post);
  post.mockResolvedValue({});
});

describe("MissionDecisionsCard", () => {
  it("is hidden when nothing is pending and for non-admins", async () => {
    get.mockResolvedValue([]);
    const { container } = open();
    await waitFor(() => expect(get).toHaveBeenCalledWith("/api/v1/missions/pending-decisions"));
    expect(container).toBeEmptyDOMElement();

    setAdmin(false);
    get.mockClear();
    const other = open();
    expect(other.container).toBeEmptyDOMElement();
    expect(get).not.toHaveBeenCalled();
  });

  it("lists plan and phase decisions with their count and mission links", async () => {
    get.mockResolvedValue([plan, phase]);
    open();
    expect(await screen.findByRole("heading", { name: "Decisões de missão (2)" })).toBeInTheDocument();
    expect(screen.getByText("Plano: plan v1")).toBeInTheDocument();
    expect(screen.getByText("Testei a navegação")).toBeInTheDocument();
    expect(screen.getByText("git:abc123")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Abrir missão" }).map((a) => a.getAttribute("href")))
      .toEqual(["/missions/m1", "/missions/m2"]);
  });

  it("approves a plan through the governed decision route", async () => {
    get.mockResolvedValue([plan]);
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Aprovar" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Aprovar" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/governed/approval-requests/req-1:decide",
      expect.objectContaining({ decision: "approved", idempotency_key: expect.any(String) })));
  });

  it("returns a phase only with a reason", async () => {
    get.mockResolvedValue([phase]);
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Devolver" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Devolver" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "Faltou o menu" } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/m2/phases/ph-1:return",
      { reason: "Faltou o menu", expected_phase_status: "awaiting_approval" }));
  });

  it("rejects a plan with its reason as the comment", async () => {
    get.mockResolvedValue([plan]);
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Recusar" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "Escopo grande demais" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Recusar" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/governed/approval-requests/req-1:decide",
      expect.objectContaining({ decision: "rejected", comments: "Escopo grande demais" })));
  });

  it("refreshes the mission's board, timeline and record after a decision", async () => {
    get.mockResolvedValue([phase]);
    open();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    fireEvent.click(await screen.findByRole("button", { name: "Aprovar" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Aprovar" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/m2/phases/ph-1:approve",
      { reason: null, expected_phase_status: "awaiting_approval" }));
    await waitFor(() => {
      const keys = invalidate.mock.calls.map(([filters]) => JSON.stringify(filters?.queryKey));
      for (const key of [["mission-pending-decisions"], ["mission-board", "m2"], ["mission-timeline", "m2"], ["mission-record", "m2"]]) {
        expect(keys).toContain(JSON.stringify(key));
      }
    });
  });

  it("shows a load failure inline with a retry instead of hiding", async () => {
    get.mockRejectedValueOnce(new Error("boom"));
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar as decisões de missão.");
    get.mockResolvedValue([plan]);
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("Plano: plan v1")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("useMissionPhaseMutation", () => {
  it("also refreshes the pending decisions", async () => {
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useMissionPhaseMutation("m9"), {
      wrapper: ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>,
    });
    await result.current.mutateAsync({ method: "POST", path: "/phases/p1:approve", body: {} });
    expect(post).toHaveBeenCalledWith("/api/v1/missions/m9/phases/p1:approve", {});
    expect(invalidate.mock.calls.map(([filters]) => JSON.stringify(filters?.queryKey)))
      .toContain(JSON.stringify(["mission-pending-decisions"]));
  });
});
