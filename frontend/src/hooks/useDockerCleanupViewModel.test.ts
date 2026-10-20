import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { DockerUsage } from "./useSystemControl";

const mutateAsync = vi.fn();
const usage: DockerUsage = {
  disk: { total: 200, used: 164, available: 36 },
  types: [
    { type: "Images", total_count: 78, active: 16, size: 24_000, reclaimable: 10_000 },
    { type: "Build Cache", total_count: 333, active: 8, size: 92_000, reclaimable: 88_000 },
  ],
  unused_images: [
    { id: "sha256:a", name: "<none>", size: 1_500, created_at: "", created_since: "9 days ago" },
    { id: "sha256:b", name: "forgehub-frontend:rollback-a", size: 500, created_at: "", created_since: "1 day ago" },
  ],
};

vi.mock("./useSystemControl", () => ({
  useDockerUsage: () => ({ data: usage, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() }),
  useDockerPrune: () => ({ mutateAsync, isPending: false }),
}));

const { useDockerCleanupViewModel } = await import("./useDockerCleanupViewModel");

describe("useDockerCleanupViewModel", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
  });

  it("takes what a full clean frees from Docker's own reclaimable figures", () => {
    const { result } = renderHook(() => useDockerCleanupViewModel());
    expect(result.current.status).toBe("ready");
    expect(result.current.unusedImages).toHaveLength(2);
    expect(result.current.totalReclaimable).toBe(98_000);
    expect(result.current.diskPercent).toBe(82);
  });

  it("asks for confirmation before pruning, then sends only the chosen step", async () => {
    mutateAsync.mockResolvedValue({ results: { build_cache: "Total:\t88GB" }, policy: "no-docker-volume-prune" });
    const { result } = renderHook(() => useDockerCleanupViewModel());

    act(() => result.current.requestPrune("build_cache"));
    expect(result.current.status).toBe("confirming");
    expect(mutateAsync).not.toHaveBeenCalled();

    await act(() => result.current.confirmPrune());
    expect(mutateAsync).toHaveBeenCalledWith({ build_cache: true, unused_images: false });
    expect(result.current.status).toBe("success");
  });

  it("'all' prunes both, and a failure lands in the error state", async () => {
    mutateAsync.mockRejectedValue(new Error("bridge down"));
    const { result } = renderHook(() => useDockerCleanupViewModel());

    act(() => result.current.requestPrune("all"));
    await act(() => result.current.confirmPrune());
    expect(mutateAsync).toHaveBeenCalledWith({ build_cache: true, unused_images: true });
    expect(result.current.status).toBe("error");
    expect(result.current.errorMessage).toBe("bridge down");
  });

  it("cancel leaves nothing pruned", () => {
    const { result } = renderHook(() => useDockerCleanupViewModel());
    act(() => result.current.requestPrune("unused_images"));
    act(() => result.current.cancelPrune());
    expect(result.current.status).toBe("ready");
    expect(mutateAsync).not.toHaveBeenCalled();
  });
});
