import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import { ToolVersionsCard } from "./ToolVersionsCard";
import * as useToolVersionsModule from "@/hooks/useToolVersions";

vi.mock("@/hooks/useToolVersions", async (importOriginal) => {
  const actual = await importOriginal<typeof useToolVersionsModule>();
  return {
    ...actual,
    useToolVersions: vi.fn(),
    useToolSyncSetting: vi.fn(),
    useCheckToolVersions: vi.fn(),
    useSetToolSyncSetting: vi.fn(),
    useRunToolUpdate: vi.fn(),
    useRunToolInstall: vi.fn(),
  };
});

describe("ToolVersionsCard - Install button", () => {
  const mockRunInstall = vi.fn();
  const mockRunUpdate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(useToolVersionsModule.useToolSyncSetting).mockReturnValue({
      data: { enabled: true },
      isLoading: false,
    } as any);

    vi.mocked(useToolVersionsModule.useCheckToolVersions).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    } as any);

    vi.mocked(useToolVersionsModule.useSetToolSyncSetting).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as any);

    vi.mocked(useToolVersionsModule.useRunToolUpdate).mockReturnValue(mockRunUpdate as any);
    vi.mocked(useToolVersionsModule.useRunToolInstall).mockReturnValue(mockRunInstall as any);
  });

  function renderCard(versions: any[]) {
    vi.mocked(useToolVersionsModule.useToolVersions).mockReturnValue({
      data: versions,
      isLoading: false,
    } as any);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    return render(
      <QueryClientProvider client={queryClient}>
        <ToolVersionsCard />
      </QueryClientProvider>
    );
  }

  it("renders 'Instalar' button and 'Não instalado' badge for uninstalled tools", () => {
    const mockVersions = [
      {
        id: "1",
        tool: "hermes",
        installed_version: "0.21.3",
        latest_version: "0.21.3",
        update_available: false,
        last_error: null,
        created_at: "2026-09-16T00:00:00Z",
        updated_at: "2026-09-16T00:00:00Z",
      },
      {
        id: "2",
        tool: "pi",
        installed_version: null,
        latest_version: "0.85.1",
        update_available: false,
        last_error: null,
        created_at: "2026-09-16T00:00:00Z",
        updated_at: "2026-09-16T00:00:00Z",
      },
    ];

    renderCard(mockVersions);

    // PI is uninstalled: should have badge/text "Não instalado" or "Not installed"
    expect(screen.getAllByText(/não instalado|not installed/i).length).toBeGreaterThanOrEqual(1);

    // PI should have an Install button
    const installButton = screen.getByTestId("tool-install-pi");
    expect(installButton).toBeInTheDocument();

    // Hermes is installed: should not have an Install button
    expect(screen.queryByTestId("tool-install-hermes")).not.toBeInTheDocument();

    // Clicking install triggers the install hook
    fireEvent.click(installButton);
    expect(mockRunInstall).toHaveBeenCalledWith("pi");
  });
});
