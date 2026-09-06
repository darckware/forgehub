import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import { apiClient } from "@/lib/api";
import { ThemeProvider } from "@/lib/theme";
import { useAuthStore } from "@/store/authStore";
import { UserSettingsMenu } from "./UserSettingsMenu";


const systemVersion = {
  app_version: "1.4.2",
  git_sha: "abc1234",
  git_commit_url: "https://github.com/marcelodarckferreira/forgehub/commit/abc1234",
  build_date: "2026-09-06T15:00:00Z",
  postgres_version: "PostgreSQL 16.4",
  latest_migration_bundled: "ff98a10e7daa_add_chat_sessions_working_directory_path.py",
  github_repo_url: "https://github.com/marcelodarckferreira/forgehub",
};


function renderMenu() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <UserSettingsMenu collapsed={false} />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}


describe("UserSettingsMenu system version", () => {
  beforeEach(() => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    useAuthStore.getState().setAuth(
      "test-token",
      {
        id: "user-1",
        username: "marcelo",
        email: null,
        full_name: "Marcelo",
        avatar_data_url: null,
        is_active: true,
        is_admin: true,
        profile_id: null,
        ui_language: "pt-BR",
      },
      {},
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens About and identifies the deployed ForgeHub build", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(systemVersion);
    renderMenu();

    fireEvent.click(screen.getByRole("button", { name: "Configurações" }));
    fireEvent.click(screen.getByRole("button", { name: "Sobre" }));

    await screen.findByText("1.4.2");
    const dialog = screen.getByRole("dialog", { name: "Sobre" });
    expect(dialog).toHaveTextContent("1.4.2");
    expect(dialog).toHaveTextContent("abc1234");
    expect(dialog).toHaveTextContent("PostgreSQL 16.4");
    expect(screen.getByRole("link", { name: "abc1234" })).toHaveAttribute(
      "href",
      systemVersion.git_commit_url,
    );
  });

  it("keeps an honest loading state while deployment identity is pending", () => {
    vi.spyOn(apiClient, "get").mockReturnValue(new Promise(() => undefined));
    renderMenu();

    fireEvent.click(screen.getByRole("button", { name: "Configurações" }));
    fireEvent.click(screen.getByRole("button", { name: "Sobre" }));

    expect(screen.getByRole("status")).toHaveTextContent(
      "Carregando informações da versão",
    );
  });

  it("reports when deployment identity cannot be loaded", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("offline"));
    renderMenu();

    fireEvent.click(screen.getByRole("button", { name: "Configurações" }));
    fireEvent.click(screen.getByRole("button", { name: "Sobre" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar as informações da versão.",
    );
  });

  it("focuses the About action and closes the dialog with Escape", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(systemVersion);
    renderMenu();

    fireEvent.click(screen.getByRole("button", { name: "Configurações" }));
    fireEvent.click(screen.getByRole("button", { name: "Sobre" }));

    const dialog = await screen.findByRole("dialog", { name: "Sobre" });
    expect(screen.getByRole("button", { name: "Fechar" })).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Sobre" })).not.toBeInTheDocument();
  });
});
