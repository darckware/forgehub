import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { useSyncUiLanguage } from "@/hooks/useAuth";
import { apiClient } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { MyLanguageControl } from "./MyLanguageControl";

function LanguageScreen() {
  useSyncUiLanguage();
  return <MyLanguageControl />;
}

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <LanguageScreen />
    </QueryClientProvider>,
  );
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
  useAuthStore.getState().setAuth("token", {
    id: "u1", username: "operator", email: null, full_name: "Operator",
    avatar_data_url: null, totp_enabled: false, is_active: true,
    is_admin: true, profile_id: null, ui_language: "en",
  }, {});
  vi.restoreAllMocks();
});

it("changes the current account language after a successful save", async () => {
  const user = useAuthStore.getState().user!;
  vi.spyOn(apiClient, "patch").mockResolvedValue({ ...user, ui_language: "pt-BR" });
  mount();

  fireEvent.change(screen.getByLabelText("My interface language"), { target: { value: "pt-BR" } });

  await waitFor(() => expect(useAuthStore.getState().user?.ui_language).toBe("pt-BR"));
  await waitFor(() => expect(i18n.language).toBe("pt-BR"));
  expect(apiClient.patch).toHaveBeenCalledWith("/api/v1/users/me", { ui_language: "pt-BR" });
});

it("keeps the previous language when saving fails", async () => {
  vi.spyOn(apiClient, "patch").mockRejectedValue(new Error("offline"));
  mount();

  fireEvent.change(screen.getByLabelText("My interface language"), { target: { value: "es" } });

  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save your language");
  expect(screen.getByLabelText("My interface language")).toHaveValue("en");
  expect(i18n.language).toBe("en");
});
