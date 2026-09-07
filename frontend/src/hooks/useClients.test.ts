import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/lib/api";
import { useClient } from "./useClients";

function wrapper(client: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return createElement(QueryClientProvider, { client }, children);
  };
}

afterEach(() => vi.restoreAllMocks());

describe("useClient", () => {
  it("does not request a client until the route has an id", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({});
    const { result } = renderHook(() => useClient(""), { wrapper: wrapper(queryClient) });

    expect(result.current.fetchStatus).toBe("idle");
    expect(get).not.toHaveBeenCalled();
  });

  it("loads one client by id", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ id: "client-1", name: "Acme" });
    const { result } = renderHook(() => useClient("client-1"), { wrapper: wrapper(queryClient) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith("/api/v1/clients/client-1");
  });
});
