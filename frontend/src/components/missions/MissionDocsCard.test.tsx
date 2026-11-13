import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import "@/i18n";
import { ApiError, apiClient } from "@/lib/api";
import { MissionDocsCard } from "./MissionDocsCard";

vi.mock("@/components/explorer/FileExplorerPane", () => ({
  FileExplorerPane: ({ initialPath }: { initialPath: string }) => <p>explorer at {initialPath}</p>,
}));

function show(dir: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MissionDocsCard workingDirectory={dir} /></QueryClientProvider>);
}
afterEach(() => vi.restoreAllMocks());

it("lists the documents in docs/ and opens the Explorer there", async () => {
  vi.spyOn(apiClient, "get").mockResolvedValue({ path: "/root/project/x/docs", parent: "/root/project/x",
    entries: [{ name: "CONTEXTO.md", path: "/root/project/x/docs/CONTEXTO.md", type: "file" },
      { name: ".hidden", path: "/root/project/x/docs/.hidden", type: "file" }] } as never);
  const post = vi.spyOn(apiClient, "post");
  show("/root/project/x/");
  expect(await screen.findByText("CONTEXTO.md")).toBeInTheDocument();
  expect(screen.queryByText(".hidden")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Abrir no Explorador" }));
  expect(await screen.findByText("explorer at /root/project/x/docs")).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});

it("creates docs/ before opening the Explorer when it doesn't exist", async () => {
  vi.spyOn(apiClient, "get").mockRejectedValue(new ApiError("nf", 404, {}));
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({} as never);
  show("/root/project/x");
  expect(await screen.findByText(/ainda não existe/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Abrir no Explorador" }));
  await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/file-explorer/directory", { path: "/root/project/x/docs" }, expect.anything()));
  expect(await screen.findByText("explorer at /root/project/x/docs")).toBeInTheDocument();
});

it("asks for a working directory when the mission has none", () => {
  show(null);
  expect(screen.getByText(/não tem pasta de trabalho/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Abrir no Explorador" })).not.toBeInTheDocument();
});
