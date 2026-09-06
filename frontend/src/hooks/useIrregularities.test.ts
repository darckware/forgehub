import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type PropsWithChildren } from "react";
import { describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { useIrregularities, type Irregularity } from "./useIrregularities";

function queryWrapper(queryClient: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const IRREGULARITY: Irregularity = {
  id: "11111111-1111-4111-8111-111111111111",
  workstation_id: "22222222-2222-4222-8222-222222222222",
  rule_key: "disk_space_low",
  severity: "warning",
  detail: "Disk usage above 90%",
  status: "open",
  detected_at: "2026-09-06T12:00:00Z",
  resolved_at: null,
  resolved_by_user_id: null,
};

describe("useIrregularities", () => {
  it("keys its query on the filters object, so a filter change triggers a refetch", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue([IRREGULARITY]);
    const filters = { status_filter: "open" };

    const { result } = renderHook(() => useIrregularities(filters), { wrapper: queryWrapper(queryClient) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith("/api/v1/irregularities", { params: filters });
    // TanStack Query keys off deep-equality of the whole query key array, so
    // the filters object must be present in the cached key exactly as passed
    // -- this is what makes changing status_filter trigger a fresh fetch
    // instead of reusing a cached list for a different filter.
    expect(queryClient.getQueryData(["irregularities", filters])).toEqual([IRREGULARITY]);
    expect(queryClient.getQueryState(["irregularities", { status_filter: "open" }])).toBeDefined();
  });
});
