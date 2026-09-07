import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import {
  useCreatePeerGrant,
  usePeerGrants,
  useRevokePeerGrant,
  type PeerGrant,
} from "./usePeerGrants";

function queryWrapper(queryClient: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const GRANT: PeerGrant = {
  id: "11111111-1111-4111-8111-111111111111",
  workstation_a_id: "22222222-2222-4222-8222-222222222222",
  workstation_b_id: "33333333-3333-4333-8333-333333333333",
  granted_by_user_id: "44444444-4444-4444-8444-444444444444",
  granted_at: "2026-09-07T12:00:00Z",
  revoked_at: null,
};

afterEach(() => vi.restoreAllMocks());

describe("usePeerGrants", () => {
  it("does not request grants until a client is selected", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue([]);

    const { result } = renderHook(() => usePeerGrants(""), {
      wrapper: queryWrapper(queryClient),
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(get).not.toHaveBeenCalled();
  });

  it("requests grants scoped to the selected client", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const get = vi.spyOn(apiClient, "get").mockResolvedValue([GRANT]);

    const { result } = renderHook(() => usePeerGrants("client-1"), {
      wrapper: queryWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith("/api/v1/peer-grants", {
      params: { client_id: "client-1" },
    });
    expect(result.current.data).toEqual([GRANT]);
  });

  it("creates a pair and invalidates every peer-grant list", async () => {
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    queryClient.setQueryData(["peer-grants", "client-1"], []);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(GRANT);
    const { result } = renderHook(() => useCreatePeerGrant(), {
      wrapper: queryWrapper(queryClient),
    });

    await result.current.mutateAsync({
      workstationAId: GRANT.workstation_a_id,
      workstationBId: GRANT.workstation_b_id,
    });

    expect(post).toHaveBeenCalledWith("/api/v1/peer-grants", {
      workstation_a_id: GRANT.workstation_a_id,
      workstation_b_id: GRANT.workstation_b_id,
    });
    expect(queryClient.getQueryState(["peer-grants", "client-1"])?.isInvalidated).toBe(true);
  });

  it("revokes a pair and invalidates every peer-grant list", async () => {
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    queryClient.setQueryData(["peer-grants", "client-1"], [GRANT]);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      ...GRANT,
      revoked_at: "2026-09-07T12:05:00Z",
    });
    const { result } = renderHook(() => useRevokePeerGrant(), {
      wrapper: queryWrapper(queryClient),
    });

    await result.current.mutateAsync(GRANT.id);

    expect(post).toHaveBeenCalledWith(`/api/v1/peer-grants/${GRANT.id}:revoke`);
    expect(queryClient.getQueryState(["peer-grants", "client-1"])?.isInvalidated).toBe(true);
  });
});
