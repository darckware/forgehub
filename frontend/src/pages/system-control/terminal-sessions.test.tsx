import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";

const state = vi.hoisted(() => ({
  navigate: vi.fn(), kill: vi.fn(), refetch: vi.fn(),
  metadata: { data: { "session-codex": { label: "Codex · ForgeHub", notes: "" } } } as { data?: Record<string, { label: string | null; notes: string }>; isError?: boolean },
  sessions: { data: { sessions: [{ session_id: "session-codex", attached: false, created_at: 1794278284, last_activity_at: 1794278284 }] }, isLoading: false, isError: false, refetch: vi.fn() },
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => state.navigate }));
vi.mock("@/hooks/useSystemControl", () => {
  const idle = () => ({ data: undefined, isPending: false, isSuccess: false, isError: false, mutate: vi.fn() });
  return { ...Object.fromEntries(["useBackupListing", "useBackupTargets", "useCleanupScan", "useCommitChanges", "useDeleteBackup", "useDeleteCleanupCategory", "useEmptyTrash", "useRunBackup", "useRunCleanup", "useTrashStatus"].map(name => [name, idle])),
    useSystemControlStatus: () => ({ data: { git: { dirty_count: 0, last_commit: { hash: "abcdef123", date: "2026-11-10T00:00:00Z" }, status_lines: [], repo_key: "forgehub" }, backups: { count: 0 }, available_repos: [] }, refetch: vi.fn() }),
  };
});
vi.mock("@/hooks/useTerminalBrowse", () => ({
  useTerminalSessions: () => state.sessions,
  useTerminalMetadata: () => ({ refetch: state.refetch, ...state.metadata }),
  useKillTerminalSession: () => ({ mutate: state.kill }),
}));
vi.mock("@/hooks/useChat", () => Object.fromEntries(["useChatSessionsHostStatus", "useDeleteChatSessionHostStatus", "useResetAllStaleChatSessions", "useResetChatSessionHermesLink"].map(name => [name, () => ({ data: [] })])));
vi.mock("@/components/AssistantToggleButton", () => ({ AssistantToggleButton: () => null }));
vi.mock("./DockerCleanupCard", () => ({ DockerCleanupCard: () => null }));
vi.mock("./BackupFilesCard", () => ({ BackupFilesCard: () => null }));
vi.mock("./OffsiteBackupCard", () => ({ OffsiteBackupCard: () => null }));
import SystemControlPage from "./index";

beforeEach(async () => {
  await i18n.changeLanguage("pt-BR");
  vi.clearAllMocks();
  state.metadata = { data: { "session-codex": { label: "Codex · ForgeHub", notes: "" } } };
  state.sessions.isError = false;
});

it("identifies the live session by its shared tab name and preserves it when reopening", () => {
  render(<SystemControlPage />);
  expect(screen.getByText("Codex · ForgeHub")).toBeInTheDocument();
  expect(screen.getByText("session-codex")).toBeInTheDocument();
  expect(screen.getByText("Sem conexão")).toBeInTheDocument();
  expect(screen.queryByText("Órfã")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Abrir sessão Codex · ForgeHub no Workspace" }));
  expect(state.navigate).toHaveBeenCalledWith("/workspace", { state: { openSession: { id: "session-codex", label: "Codex · ForgeHub" } } });
});

it("keeps the session identifiable when no saved name exists", () => {
  state.metadata = { data: {} };
  render(<SystemControlPage />);
  expect(screen.getByText("Terminal sem nome")).toBeInTheDocument();
  expect(screen.getByText("session-codex")).toBeInTheDocument();
});

it("reports failed names without hiding the live session", () => {
  state.metadata = { isError: true };
  render(<SystemControlPage />);
  expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível carregar os nomes");
  expect(screen.getByText("session-codex")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Atualizar sessões" }));
  expect(state.refetch).toHaveBeenCalledOnce();
  expect(state.sessions.refetch).toHaveBeenCalledOnce();
});

it("does not report no active sessions when the host request fails", () => {
  state.sessions.isError = true;
  render(<SystemControlPage />);
  expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível consultar as sessões");
  expect(screen.queryByText("Nenhuma sessão de terminal ativa.")).not.toBeInTheDocument();
});

it("names the destructive confirmation and requires confirmation before ending work", () => {
  render(<SystemControlPage />);
  fireEvent.click(screen.getByRole("button", { name: "Encerrar sessão Codex · ForgeHub" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Codex · ForgeHub");
  expect(state.kill).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Encerrar sessão" }));
  expect(state.kill).toHaveBeenCalledWith("session-codex", expect.any(Object));
});
