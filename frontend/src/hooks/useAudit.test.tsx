import { QueryClient, QueryClientProvider, focusManager } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { useAuditChecks, useAuditStatus } from "./useAudit";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn() } }));

const startedAt = new Date("2026-11-12T12:00:00Z").getTime();
const expiresAt = startedAt + 30_000;
const recordedAt = new Date(expiresAt - 8 * 24 * 60 * 60 * 1000).toISOString();

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(startedAt);
  vi.mocked(apiClient.get).mockImplementation(async (path) => {
    const stale = Date.now() >= expiresAt;
    if (path.endsWith("/status")) {
      return { total: 1, enabled: 1, ok: stale ? 0 : 1, fail: 0, stale: stale ? 1 : 0,
        never_ran: 0, last_run_at: recordedAt, last_complete_cron_run_at: recordedAt };
    }
    return [{ id: "c1", name: "ECO-001", description: null, category: null, command: "true",
      remediation_description: null, remediation_command: null, workdir: null, agent_profile: "athos",
      enabled: true, timeout_seconds: 55, created_at: recordedAt, updated_at: recordedAt,
      evidence_state: stale ? "stale" : "fresh", expires_at: new Date(expiresAt).toISOString(),
      last_run: { id: "r1", check_id: "c1", status: "ok", exit_code: 0, output: "passed",
        duration_ms: 1, requested_by: "cron", created_at: recordedAt } }];
  });
});

afterEach(() => {
  focusManager.setFocused(undefined);
  vi.useRealTimers();
  vi.clearAllMocks();
});

it.each([true, false])("refreshes both mounted evidence queries within 60 seconds with window focus %s", async (focused) => {
  focusManager.setFocused(focused);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result, unmount } = renderHook(() => ({ checks: useAuditChecks(), status: useAuditStatus() }), { wrapper });
  try {
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(result.current.checks.data?.[0].evidence_state).toBe("fresh");
    expect(result.current.status.data?.ok).toBe(1);
    expect(apiClient.get).toHaveBeenCalledTimes(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(59_000); });
    expect(apiClient.get).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
    expect(result.current.checks.data?.[0].evidence_state).toBe("stale");
    expect(result.current.checks.data?.[0].last_run?.status).toBe("ok");
    expect(result.current.status.data?.ok).toBe(0);
    expect(result.current.status.data?.stale).toBe(1);
    expect(apiClient.get).toHaveBeenCalledTimes(4);
  } finally {
    unmount();
    client.clear();
  }
});

it("refreshes both queries on return after a browser suspends background timers", async () => {
  focusManager.setFocused(true);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result, unmount } = renderHook(() => ({ checks: useAuditChecks(), status: useAuditStatus() }), { wrapper });
  try {
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(result.current.status.data?.ok).toBe(1);
    await act(async () => { focusManager.setFocused(false); });
    // Simulate a suspended tab: wall time moves, but polling timers do not run.
    vi.setSystemTime(expiresAt + 1_000);
    await act(async () => {
      focusManager.setFocused(true);
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(result.current.checks.data?.[0].evidence_state).toBe("stale");
    expect(result.current.status.data?.ok).toBe(0);
    expect(result.current.status.data?.stale).toBe(1);
    expect(apiClient.get).toHaveBeenCalledTimes(4);
  } finally {
    unmount();
    client.clear();
  }
});
