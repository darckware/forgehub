import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import "@/i18n";
import { useAuthStore } from "@/store/authStore";
import { apiClient } from "@/lib/api";
import MissionFormPage from "./FormPage";

beforeEach(() => {
  useAuthStore.setState({ user: { is_admin: true } as never });
  vi.spyOn(apiClient, "get").mockImplementation(async (path) => {
    if (path === "/api/v1/products") return [{ id: "p", name: "FileNest" }] as never;
    if (path === "/api/v1/products/versions") return [{ id: "v", product_id: "p", version: "0.4.0", status: "planned" }] as never;
    if (path === "/api/v1/agents") return [{ id: "a", name: "Athos", is_active: true, status: "active" }, { id: "b", name: "Atlas", is_active: true, status: "active" }] as never;
    return [] as never;
  });
});
afterEach(() => { vi.restoreAllMocks(); useAuthStore.setState({ user: null }); });
function open(path = "/missions/new") {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={cache}>
    <MemoryRouter initialEntries={[path]}><Routes>
      <Route path="/missions/new" element={<MissionFormPage />} />
      <Route path="/missions/:projectId/edit" element={<MissionFormPage />} />
      <Route path="/missions/:id" element={<p>Missão criada</p>} />
      <Route path="/missions" element={<p>Lista de missões</p>} />
    </Routes></MemoryRouter>
  </QueryClientProvider>);
  return cache;
}
it("creates a draft mission from a full page and selected real records", async () => {
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({ project_id: "created" });
  open();
  await screen.findByRole("option", { name: /FileNest.*0.4.0/ });
  fireEvent.change(screen.getByLabelText("Nome da missão"), { target: { value: "Validar FileNest" } });
  fireEvent.change(screen.getByLabelText("Produto e versão"), { target: { value: "v" } });
  fireEvent.change(screen.getByLabelText("Orquestrador"), { target: { value: "a" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar missão" }));
  await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions", expect.objectContaining({ name: "Validar FileNest", product_version_id: "v", orchestrator_agent_id: "a", project_type: "mission", autonomy_level: "N0" })));
  expect(await screen.findByText("Missão criada")).toBeInTheDocument();
});
it("configures an agent's role and responsibilities through the governed membership command", async () => {
  const originalGet = vi.mocked(apiClient.get).getMockImplementation()!;
  vi.spyOn(apiClient, "get").mockImplementation(async (path) => {
    if (path === "/api/v1/missions/m") return { project_id: "m", name: "Piloto", product_version_id: "v", orchestrator_agent_id: "a", state: "draft", priority: 100, row_version: 1 } as never;
    if (path === "/api/v1/orchestration/projects/m/memberships") return [] as never;
    return originalGet(path) as never;
  });
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({ memberships: [] });
  open("/missions/m/edit");
  await screen.findByRole("heading", { name: "Agentes por função" });
  fireEvent.change(screen.getByLabelText("Agente da equipe"), { target: { value: "b" } });
  fireEvent.change(screen.getByLabelText("Função na missão"), { target: { value: "planner" } });
  fireEvent.change(screen.getByLabelText("Responsabilidades e limites"), { target: { value: "Planejar o backend sem implementar código." } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar função" }));
  expect(post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar função" }));
  await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/m/members:apply", expect.objectContaining({
    idempotency_key: expect.any(String), operations: [{ op: "add", agent_id: "b", role: "planner", responsibilities: "Planejar o backend sem implementar código.", can_review: false }],
  })));
});
it("keeps creation unavailable to a non-administrator", async () => {
  useAuthStore.setState({ user: { is_admin: false } as never });
  open();
  expect(screen.queryByRole("button", { name: "Criar missão" })).not.toBeInTheDocument();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

function mockMission(state = "draft") {
  const originalGet = vi.mocked(apiClient.get).getMockImplementation()!;
  vi.mocked(apiClient.get).mockImplementation(async (path) => path === "/api/v1/missions/m"
    ? { project_id: "m", name: "Piloto", product_version_id: "v", orchestrator_agent_id: "a", state, priority: 100, row_version: 7, description: "Objetivo", working_directory_path: "/srv/pilot" } as never
    : originalGet(path) as never);
}

it("edits mission metadata using the loaded row version", async () => {
  mockMission();
  const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ project_id: "m" });
  open("/missions/m/edit");
  await screen.findByDisplayValue("Piloto");
  fireEvent.change(screen.getByLabelText("Nome da missão"), { target: { value: "Piloto revisado" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
  await waitFor(() => expect(patch).toHaveBeenCalledWith("/api/v1/missions/m", expect.objectContaining({ name: "Piloto revisado", expected_row_version: 7, description: "Objetivo", working_directory_path: "/srv/pilot" })));
  expect(await screen.findByText("Missão criada")).toBeInTheDocument();
});

it("cancels only after a reason and confirmation, preserving mission history", async () => {
  mockMission();
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({ project_id: "m" });
  open("/missions/m/edit");
  const cancel = await screen.findByRole("button", { name: "Cancelar missão" });
  expect(cancel).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Motivo da alteração ou cancelamento"), { target: { value: "Piloto substituído" } });
  fireEvent.click(cancel);
  expect(post).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toHaveTextContent("O histórico, os documentos e as provas serão preservados");
  const buttons = screen.getAllByRole("button", { name: "Cancelar missão" });
  fireEvent.click(buttons[buttons.length - 1]);
  await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/m:transition", { to: "cancelled", reason: "Piloto substituído", expected_row_version: 7 }));
  expect(await screen.findByText("Lista de missões")).toBeInTheDocument();
});

it("keeps terminal missions and their team read-only", async () => {
  mockMission("completed");
  open("/missions/m/edit");
  await screen.findByDisplayValue("Piloto");
  expect(screen.queryByRole("button", { name: "Salvar alterações" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Salvar função" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Nome da missão")).toBeDisabled();
});

it("keeps the edited snapshot row version when a background refresh brings concurrent changes", async () => {
  mockMission();
  const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ project_id: "m" });
  const cache = open("/missions/m/edit");
  await screen.findByDisplayValue("Piloto");
  fireEvent.change(screen.getByLabelText("Nome da missão"), { target: { value: "Minha edição" } });
  await act(async () => {
    cache.setQueryData(["mission-record", "m"], (old: object) => ({ ...old, name: "Outra edição", row_version: 8 }));
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
  await waitFor(() => expect(patch).toHaveBeenCalledWith("/api/v1/missions/m", expect.objectContaining({ name: "Minha edição", expected_row_version: 7 })));
});

it("can release an existing member whose registered agent has become inactive", async () => {
  mockMission();
  const originalGet = vi.mocked(apiClient.get).getMockImplementation()!;
  vi.mocked(apiClient.get).mockImplementation(async (path) => {
    if (path === "/api/v1/agents") return [{ id: "c", name: "Aramis inativo", is_active: false, status: "inactive" }] as never;
    if (path.endsWith("/memberships")) return [{ id: "mc", agent_id: "c", role: "developer", status: "active", can_review: false }] as never;
    return originalGet(path) as never;
  });
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({ memberships: [] });
  open("/missions/m/edit");
  await screen.findByRole("option", { name: "Aramis inativo" });
  fireEvent.change(screen.getByLabelText("Agente da equipe"), { target: { value: "c" } });
  fireEvent.click(screen.getByRole("button", { name: "Liberar agente" }));
  const releases = screen.getAllByRole("button", { name: "Liberar agente" });
  fireEvent.click(releases[releases.length - 1]);
  await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/m/members:apply", expect.objectContaining({ operations: [{ op: "release", agent_id: "c" }] })));
});

it("identifies a failed version selector and recovers through retry", async () => {
  const originalGet = vi.mocked(apiClient.get).getMockImplementation()!;
  let unavailable = true;
  vi.mocked(apiClient.get).mockImplementation(async path => {
    if (path === "/api/v1/products/versions" && unavailable) throw new Error("422");
    return originalGet(path) as never;
  });
  open();
  expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar as versões dos produtos.");
  expect(screen.getByRole("link", { name: "Missões" })).toHaveAttribute("href", "/missions");
  unavailable = false;
  fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
  expect(await screen.findByLabelText("Nome da missão")).toBeInTheDocument();
});
