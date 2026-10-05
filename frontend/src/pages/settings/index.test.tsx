import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { useAuthStore } from "@/store/authStore";
import SettingsPage from "./index";

const appConfig = {
  hermes_source_path: "/root/hermes",
  git_control_default_repo: "hermes",
  backup_root: "/backups",
  trash_root: "/root/trash",
  cleanup_scan_root: "/root",
  cleanup_prune_paths: [],
  cleanup_prune_names: [],
  timezone: "America/Sao_Paulo",
  chat_response_language: "fr",
  default_ui_language: "pt-BR",
  agent_runtime_paths: {},
  default_forgerouter_service_name: "",
};
const mutateAsync = vi.fn(async (payload) => payload);

vi.mock("@/hooks/useAppConfig", () => ({
  useAppConfig: () => ({ data: appConfig, isLoading: false, isError: false }),
  useUpdateAppConfig: () => ({ mutateAsync, isPending: false, isSuccess: false, isError: false }),
}));
vi.mock("@/hooks/useAgent", () => ({ useForgeRouterServices: () => ({ data: [] }) }));
vi.mock("@/hooks/useOrchestration", () => ({ useForgeRouterVirtualModels: () => ({ data: [], isLoading: false }) }));
vi.mock("@/hooks/useTerminalBrowse", () => ({
  useOpenclawGatewayToken: () => ({ data: { token: "" }, isLoading: false }),
  useUpdateOpenclawGatewayToken: () => ({ mutate: vi.fn(), isPending: false, isSuccess: false, isError: false }),
}));

beforeEach(async () => {
  mutateAsync.mockClear();
  await i18n.changeLanguage("en");
  useAuthStore.getState().setAuth("token", {
    id: "u1", username: "operator", email: null, full_name: "Operator",
    avatar_data_url: null, totp_enabled: false, is_active: true,
    is_admin: true, profile_id: null, ui_language: "en",
  }, {});
});

it("separates the current account language from the default for new users", async () => {
  render(<QueryClientProvider client={new QueryClient()}><SettingsPage /></QueryClientProvider>);

  expect(screen.getByLabelText("My interface language")).toHaveValue("en");
  expect(screen.getByLabelText("Default language for new users")).toHaveValue("pt-BR");
  expect(screen.getByLabelText("Chat response language")).toHaveValue("fr");
  expect(screen.getByText(/previous language remains active/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Default language for new users"), { target: { value: "es" } });
  await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ default_ui_language: "es" })));
  expect(useAuthStore.getState().user?.ui_language).toBe("en");
  expect(i18n.language).toBe("en");
});
