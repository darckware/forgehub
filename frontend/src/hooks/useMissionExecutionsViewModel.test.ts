import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiClient } from "@/lib/api";
import { actionRequest } from "@/hooks/useMissions";
import { useMissionExecutionsViewModel } from "@/hooks/useMissionExecutionsViewModel";
import { missionBoard } from "@/test/fixtures/missionBoard";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => vi.restoreAllMocks());

describe("useMissionExecutionsViewModel (M0.7)", () => {
  it("goes loading -> ready and keeps the backend's blocked reasons", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(missionBoard());
    const { result } = renderHook(() => useMissionExecutionsViewModel("m07-mission"), { wrapper });
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    const [ready, running] = result.current.tasks;
    expect(result.current.blockedReason(ready, "dispatch")).toBeNull();
    expect(result.current.blockedReason(running, "dispatch")).toBe("TASK_RUN_IN_FLIGHT");
    expect(result.current.blockedReason(running, "request_review")).toBe("REVIEWER_IS_EXECUTOR");
    expect(result.current.missionBlockedReason("pause")).toBeNull();
  });

  it("is empty for a mission with no tasks and no planning", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(missionBoard({ tasks: [], conflicts: [] }));
    const { result } = renderHook(() => useMissionExecutionsViewModel("m07-mission"), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("empty"));
  });

  it("shows live updates as paused when only polling is available", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(missionBoard());
    const { result } = renderHook(() => useMissionExecutionsViewModel("m07-mission"), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.live).toBe("paused");
  });

  it.each([[404, "not_found"], [403, "forbidden"], [500, "server"]])("maps HTTP %s to %s", async (code, kind) => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new ApiError("x", code, {}));
    const { result } = renderHook(() => useMissionExecutionsViewModel("m07-mission"), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.errorKind).toBe(kind);
  });

  it("requires a reason for a return, then submits to the guarded route and keeps the refusal", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(missionBoard());
    const post = vi.spyOn(apiClient, "post").mockRejectedValue(
      new ApiError("x", 409, { detail: { code: "TASK_RUN_IN_FLIGHT", message: "run active" } }));
    const { result } = renderHook(() => useMissionExecutionsViewModel("m07-mission"), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    act(() => result.current.openAction("return", { taskId: "t-running" }));
    // Modal policy: input is typed on the page first; the modal only confirms.
    expect(result.current.status).toBe("editing");
    expect(result.current.hasFields).toBe(true);
    expect(result.current.needsReason).toBe(true);
    expect(result.current.canConfirm).toBe(false);
    act(() => result.current.requestConfirm());
    expect(result.current.status).toBe("editing");
    act(() => result.current.setReason("falta teste"));
    expect(result.current.canConfirm).toBe(true);
    act(() => result.current.requestConfirm());
    expect(result.current.status).toBe("confirming");
    await act(async () => { await result.current.confirmAction(); });
    expect(post).toHaveBeenCalledWith("/api/v1/missions/m07-mission/tasks/t-running:return",
      expect.objectContaining({ execution_id: "e-2", reason: "falta teste" }));
    expect(result.current.actionError).toBe("TASK_RUN_IN_FLIGHT: run active");
    expect(result.current.status).toBe("confirming");
    expect(result.current.reason).toBe("falta teste");
    act(() => result.current.dismissConfirm());
    expect(result.current.status).toBe("editing");
    expect(result.current.reason).toBe("falta teste");
  });

  it("closes the dialog after success and reports it", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue(missionBoard());
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    const { result } = renderHook(() => useMissionExecutionsViewModel("m07-mission"), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    act(() => result.current.openAction("dispatch", { taskId: "t-ready" }));
    expect(result.current.needsReason).toBe(false);
    expect(result.current.hasFields).toBe(false);
    expect(result.current.status).toBe("confirming");
    await act(async () => { await result.current.confirmAction(); });
    expect(post).toHaveBeenCalledWith("/api/v1/tasks/t-ready/dispatch", {});
    expect(result.current.pending).toBeNull();
    expect(result.current.lastResult).toBe("dispatch");
  });
});

describe("actionRequest", () => {
  it("maps every action to an existing guarded route", () => {
    const paths = (["dispatch", "schedule", "assign", "request_review", "return", "pause", "resume", "cancel", "decide_item"] as const)
      .map((kind) => actionRequest("p", { kind, taskId: "t", itemId: "i" }).path);
    expect(paths).toEqual([
      "/api/v1/tasks/t/dispatch", "/api/v1/tasks/t/dispatch", "/api/v1/missions/p/tasks/t:assign",
      "/api/v1/missions/p/tasks/t:request-review", "/api/v1/missions/p/tasks/t:return",
      "/api/v1/missions/p:transition", "/api/v1/missions/p:transition", "/api/v1/missions/p:transition",
      "/api/v1/missions/p/review-items/i:decide",
    ]);
    expect(actionRequest("p", { kind: "assign", taskId: "t", agentId: "a", reason: "r" }).body.idempotency_key)
      .toMatch(/^ui-m07-/);
  });
});
