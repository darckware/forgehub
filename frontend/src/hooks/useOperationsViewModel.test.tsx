import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api";
import { useOperationsViewModel } from "./useOperationsViewModel";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiClient.get).mockImplementation(async (path) => {
    if (path.endsWith("/overview")) return { agents: [], policy_version: 1 };
    return [];
  });
});

it("loads the overview without fetching hidden tabs", async () => {
  const { result } = renderHook(() => useOperationsViewModel("agents"), { wrapper });
  await waitFor(() => expect(result.current.overview.data?.policy_version).toBe(1));
  expect(apiClient.get).toHaveBeenCalledWith("/api/v1/operations/overview");
  expect(apiClient.get).not.toHaveBeenCalledWith("/api/v1/operations/questions");
});

it("sends a question answer to its canonical endpoint", async () => {
  vi.mocked(apiClient.post).mockResolvedValue({ id: "q1", status: "answered" });
  const { result } = renderHook(() => useOperationsViewModel("questions"), { wrapper });
  await act(async () => {
    await result.current.answerQuestion.mutateAsync({ id: "q1", answer: "Aprovado." });
  });
  expect(apiClient.post).toHaveBeenCalledWith("/api/v1/operations/questions/q1:answer", { answer: "Aprovado." });
});
