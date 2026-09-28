import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAgentActivityStreamViewModel } from "./useAgentActivityStreamViewModel";

const FRAME = {
  generated_at: "2026-09-28T12:00:00Z",
  agents: [
    {
      agent_id: "22222222-2222-4222-8222-222222222222",
      live: null,
      spark: [0, 1],
      tokens_last_hour: 0,
      cost_today: 0,
    },
  ],
  pulse: {
    agents_total: 1, agents_reporting: 0, agents_active: 0, agents_in_turn: 0, agents_degraded: 0,
    turns_last_hour: 0, tools_last_hour: 0, failures_last_hour: 0, pending_total: 0,
    llm_calls_last_hour: null, tokens_last_hour: null, cost_today: null, turns_per_minute: [0],
  },
};

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useAgentActivityStreamViewModel", () => {
  it("goes live on a snapshot frame (even split across chunks) and reconnects when the stream ends", async () => {
    const payload = JSON.stringify(FRAME);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        sseResponse([`event: snapshot\ndata: ${payload.slice(0, 20)}`, `${payload.slice(20)}\n\n`]),
      )
      .mockImplementation(() => new Promise(() => {})); // the reconnect attempt stays pending
    vi.stubGlobal("fetch", fetchMock);

    const { result, unmount } = renderHook(() => useAgentActivityStreamViewModel());
    await waitFor(() => expect(result.current.snapshot?.agents).toHaveLength(1));
    await waitFor(() => expect(result.current.status).toBe("reconnecting"));
    expect(result.current.snapshot?.pulse.cost_today).toBeNull();
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/v1\/agent-activity\/stream$/);
    unmount();
  });

  it("does not connect when disabled", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useAgentActivityStreamViewModel(false));
    expect(result.current.status).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
