import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { RotationDialog } from "./RotationDialog";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

describe("RotationDialog", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === "/api/v1/servers") {
        return [
          { id: "a", name: "gat-adm-pc01", os_family: "windows", ssh_key_path: "/k", darckware_client_name: "Gatling", group_ids: [] },
          { id: "b", name: "offline-pc", os_family: "windows", ssh_key_path: "/k2", group_ids: [] },
        ] as never;
      }
      return { entries: [{ server_id: "a", readiness: "ready" }, { server_id: "b", readiness: "offline" }] } as never;
    });
  });

  it("rotates the SSH key of the selected ready machines and opens the execution", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ execution_id: "e9" } as never);
    const onExecution = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><RotationDialog kind="ssh_key" onClose={vi.fn()} onExecution={onExecution} /></QueryClientProvider>);
    fireEvent.click(await screen.findByRole("checkbox", { name: /gat-adm-pc01/ }));
    expect(screen.queryByRole("checkbox", { name: /offline-pc/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revisar" }));
    fireEvent.click(screen.getByRole("button", { name: "Rotacionar (1)" }));
    await vi.waitFor(() => expect(onExecution).toHaveBeenCalledWith("e9"));
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/servers/rotations", { server_ids: ["a"], kind: "ssh_key" });
  });
});
