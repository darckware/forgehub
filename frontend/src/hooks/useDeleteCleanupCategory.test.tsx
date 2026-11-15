import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { useDeleteCleanupCategory } from "./useSystemControl";

vi.mock("@/lib/api", () => ({ apiClient: { post: vi.fn() } }));

describe("useDeleteCleanupCategory", () => {
  afterEach(() => vi.clearAllMocks());

  it.each(["success", "partial failure"] as const)(
    "refreshes the cleanup card and trash status after %s",
    async (outcome) => {
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      });
      const invalidateQueries = vi.spyOn(client, "invalidateQueries").mockResolvedValue();
      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      );
      if (outcome === "success") {
        vi.mocked(apiClient.post).mockResolvedValueOnce({ category: "Logs" } as never);
      } else {
        vi.mocked(apiClient.post).mockRejectedValueOnce(new Error("one file could not be moved"));
      }

      const { result, unmount } = renderHook(() => useDeleteCleanupCategory(), { wrapper });
      try {
        await act(async () => {
          try {
            await result.current.mutateAsync("Logs");
          } catch {
            // A partial move is reported as an error, but the displayed inventory still needs refresh.
          }
        });

        expect(invalidateQueries).toHaveBeenCalledWith({
          queryKey: ["system-control", "cleanup-scan"],
        });
        expect(invalidateQueries).toHaveBeenCalledWith({
          queryKey: ["system-control", "trash-status"],
        });
      } finally {
        unmount();
        client.clear();
      }
    },
  );
});
