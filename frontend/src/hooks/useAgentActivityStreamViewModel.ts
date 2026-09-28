import { useEffect, useRef, useState } from "react";
import { getToken } from "@/lib/api";
import { agentLiveSnapshotSchema, type AgentLiveSnapshot } from "./useAgentActivity";

export type AgentActivityStreamStatus = "idle" | "connecting" | "live" | "reconnecting" | "error";

export interface AgentActivityStreamViewModel {
  status: AgentActivityStreamStatus;
  snapshot: AgentLiveSnapshot | null;
  /** When the last frame arrived (ms epoch) -- drives the "updated" clock. */
  receivedAt: number | null;
  /** Consecutive failed attempts; resets on the first good frame. */
  attempts: number;
}

/** Backoff between reconnects: 1 s, 2 s, 5 s, then 10 s. */
export const RECONNECT_DELAYS_MS = [1_000, 2_000, 5_000, 10_000];
/** After this many consecutive failures the status reads "error" (it keeps retrying). */
export const ERROR_AFTER_ATTEMPTS = 4;
/** The server sends a frame at least every 10 s; silence past this means a dead connection. */
export const STALE_AFTER_MS = 25_000;

/**
 * Consumes GET /api/v1/agent-activity/stream (SSE, `event: snapshot` frames).
 *
 * `fetch` + a stream reader instead of EventSource because EventSource can't send the
 * Authorization header (same approach as useChat/useAiDraft). Each frame is a whole
 * snapshot, so a reconnect needs no catch-up logic: the next frame is the truth.
 * The status machine: idle -> connecting -> live, and on any drop -> reconnecting
 * (-> error after ERROR_AFTER_ATTEMPTS in a row), never giving up while mounted.
 */
export function useAgentActivityStreamViewModel(enabled = true): AgentActivityStreamViewModel {
  const [state, setState] = useState<AgentActivityStreamViewModel>({
    status: "idle",
    snapshot: null,
    receivedAt: null,
    attempts: 0,
  });
  const attemptsRef = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let controller: AbortController | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let staleTimer: ReturnType<typeof setTimeout> | null = null;

    const armStaleTimer = () => {
      if (staleTimer) clearTimeout(staleTimer);
      staleTimer = setTimeout(() => controller?.abort(), STALE_AFTER_MS);
    };

    const scheduleReconnect = () => {
      if (cancelled) return;
      attemptsRef.current += 1;
      const attempts = attemptsRef.current;
      setState((prev) => ({
        ...prev,
        attempts,
        status: attempts >= ERROR_AFTER_ATTEMPTS ? "error" : "reconnecting",
      }));
      const delay = RECONNECT_DELAYS_MS[Math.min(attempts - 1, RECONNECT_DELAYS_MS.length - 1)];
      retryTimer = setTimeout(connect, delay);
    };

    const handleFrame = (event: string, raw: string) => {
      if (event !== "snapshot") return;
      const parsed = agentLiveSnapshotSchema.safeParse(JSON.parse(raw || "{}"));
      if (!parsed.success) return;
      attemptsRef.current = 0;
      setState({ status: "live", snapshot: parsed.data, receivedAt: Date.now(), attempts: 0 });
    };

    async function connect() {
      if (cancelled) return;
      controller = new AbortController();
      setState((prev) => ({ ...prev, status: prev.snapshot ? prev.status : "connecting" }));
      const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
      try {
        const resp = await fetch(`${apiBase}/api/v1/agent-activity/stream`, {
          headers: { Authorization: `Bearer ${getToken() ?? ""}`, Accept: "text/event-stream" },
          signal: controller.signal,
        });
        if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
        armStaleTimer();
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let currentEvent = "message";
        while (!cancelled) {
          const { done, value } = await reader.read();
          if (done) break;
          armStaleTimer();
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            if (line.startsWith("event:")) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              try {
                handleFrame(currentEvent, line.slice(5).trim());
              } catch {
                // A malformed frame is skipped; the next one replaces it anyway.
              }
              currentEvent = "message";
            }
          }
        }
      } catch {
        // Network error, abort by the stale timer, or HTTP error -- all end in a reconnect.
      } finally {
        if (staleTimer) clearTimeout(staleTimer);
      }
      scheduleReconnect();
    }

    connect();
    return () => {
      cancelled = true;
      controller?.abort();
      if (retryTimer) clearTimeout(retryTimer);
      if (staleTimer) clearTimeout(staleTimer);
    };
  }, [enabled]);

  return state;
}
