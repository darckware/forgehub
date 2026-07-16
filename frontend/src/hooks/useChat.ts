import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient, getToken } from "@/lib/api";

/**
 * Chat domain -- talks to real Hermes agents (Athos, Atlas, ...) through
 * the backend's chat bridge proxy (see backend/app/api/routes/chat.py).
 * Only agents with a profile_slug (Hermes-synced) can be chatted with.
 */

export const chatMessageRoleSchema = z.enum(["user", "assistant"]);

export const chatSessionSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  title: z.string(),
  pinned: z.boolean(),
  hermes_session_id: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type ChatSession = z.infer<typeof chatSessionSchema>;

export const chatMessageSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  role: chatMessageRoleSchema,
  content: z.string(),
  attachment_names: z.string().nullable().optional(),
  responding_agent_id: z.string().nullable().optional(),
  thinking_seconds: z.number().nullable().optional(),
  created_at: z.string(),
});

export type ChatMessage = z.infer<typeof chatMessageSchema>;

export const chatSendResultSchema = z.object({
  user_message: chatMessageSchema,
  assistant_message: chatMessageSchema,
  session: chatSessionSchema,
});

export type ChatSendResult = z.infer<typeof chatSendResultSchema>;

const RESOURCE = "/api/v1/chat";

export const chatArtifactSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  path: z.string(),
  name: z.string(),
  created_at: z.string(),
});

export type ChatArtifact = z.infer<typeof chatArtifactSchema>;

export const chatKeys = {
  sessions: (agentId?: string) => ["chat-sessions", agentId ?? "all"] as const,
  messages: (sessionId: string) => ["chat-messages", sessionId] as const,
  artifacts: (sessionId: string) => ["chat-artifacts", sessionId] as const,
};

export function useChatSessions(agentId: string | undefined) {
  return useQuery({
    queryKey: chatKeys.sessions(agentId),
    queryFn: () =>
      apiClient.get<ChatSession[]>(`${RESOURCE}/sessions`, { params: { agent_id: agentId } }),
    enabled: Boolean(agentId),
  });
}

/** Matches on session title OR any message's content in that session
 * (see search_chat_sessions in chat.py). Only fires once `query` is
 * non-empty -- callers should debounce keystrokes before passing it in. */
export function useSearchChatSessions(query: string, agentId: string | undefined) {
  return useQuery({
    queryKey: ["chat-sessions-search", agentId ?? "all", query],
    queryFn: () =>
      apiClient.get<ChatSession[]>(`${RESOURCE}/sessions/search`, { params: { q: query, agent_id: agentId } }),
    enabled: query.trim().length > 0,
  });
}

export function useCreateChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { agent_id: string; title?: string }) =>
      apiClient.post<ChatSession>(`${RESOURCE}/sessions`, payload),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: chatKeys.sessions(session.agent_id) });
    },
  });
}

export function useUpdateChatSession(agentId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      sessionId,
      ...payload
    }: {
      sessionId: string;
      title?: string;
      pinned?: boolean;
    }) => apiClient.patch<ChatSession>(`${RESOURCE}/sessions/${sessionId}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.sessions(agentId) });
    },
  });
}

export function useDeleteChatSession(agentId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => apiClient.delete<void>(`${RESOURCE}/sessions/${sessionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.sessions(agentId) });
    },
  });
}

export function useChatMessages(sessionId: string | undefined) {
  return useQuery({
    queryKey: chatKeys.messages(sessionId ?? ""),
    queryFn: () => apiClient.get<ChatMessage[]>(`${RESOURCE}/sessions/${sessionId}/messages`),
    enabled: Boolean(sessionId),
  });
}

export function useChatArtifacts(sessionId: string | undefined) {
  return useQuery({
    queryKey: chatKeys.artifacts(sessionId ?? ""),
    queryFn: () => apiClient.get<ChatArtifact[]>(`${RESOURCE}/sessions/${sessionId}/artifacts`),
    enabled: Boolean(sessionId),
  });
}

/** Removes the ForgeHub-side reference only -- never touches the real
 * file on the host (see backend's delete_chat_artifact docstring). */
export function useDeleteChatArtifact(sessionId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (artifactId: string) => apiClient.delete<void>(`${RESOURCE}/artifacts/${artifactId}`),
    onSuccess: () => {
      if (sessionId) queryClient.invalidateQueries({ queryKey: chatKeys.artifacts(sessionId) });
    },
  });
}

export const chatArtifactGlobalSchema = chatArtifactSchema.extend({ agent_name: z.string() });
export type ChatArtifactGlobal = z.infer<typeof chatArtifactGlobalSchema>;

/** Cross-session, cross-agent artifact search backing the "$Artefato"
 * picker -- unlike useChatArtifacts, not scoped to one conversation. */
export function useSearchChatArtifacts(query: string) {
  return useQuery({
    queryKey: ["chat-artifacts-search", query],
    queryFn: () => apiClient.get<ChatArtifactGlobal[]>(`${RESOURCE}/artifacts`, { params: { q: query } }),
  });
}

/** Fetches the artifact's bytes (with auth) and triggers a browser save --
 * a plain <a href> can't carry the Bearer token this endpoint requires. */
export async function downloadChatArtifact(artifactId: string) {
  const { blob, filename } = await apiClient.downloadFile(`${RESOURCE}/artifacts/${artifactId}/download`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function useSendChatMessage(agentId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      sessionId,
      message,
      files,
    }: {
      sessionId: string;
      message: string;
      files?: File[] | null;
    }) => {
      const form = new FormData();
      form.set("message", message);
      for (const file of files ?? []) form.append("files", file);
      return apiClient.postForm<ChatSendResult>(`${RESOURCE}/sessions/${sessionId}/messages`, form);
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: chatKeys.messages(result.session.id) });
      queryClient.invalidateQueries({ queryKey: chatKeys.sessions(agentId) });
    },
  });
}

/** Backs the composer's "!command" prefix -- runs a raw bash command via
 * the bridge, no agent/LLM call at all. */
export function useExecChatCommand(agentId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, command, cwd }: { sessionId: string; command: string; cwd?: string }) =>
      apiClient.post<ChatSendResult>(`${RESOURCE}/sessions/${sessionId}/exec`, { command, cwd }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: chatKeys.messages(result.session.id) });
      queryClient.invalidateQueries({ queryKey: chatKeys.sessions(agentId) });
    },
  });
}

/** Deletes a single message -- used by the "Regenerate" action to drop the
 * assistant's last reply before requesting a fresh one. */
export function useDeleteChatMessage(sessionId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => apiClient.delete<void>(`${RESOURCE}/messages/${messageId}`),
    onSuccess: () => {
      if (sessionId) queryClient.invalidateQueries({ queryKey: chatKeys.messages(sessionId) });
    },
  });
}

export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "tool_start"; toolId: string; name: string; context?: string; detail?: string }
  | { type: "tool_complete"; toolId: string; name: string; summary?: string }
  | { type: "approval_request"; streamId: string; command?: string; description?: string; patternKeys?: string[] }
  | { type: "done"; reply: string }
  | { type: "error"; message: string };

function parseChatStreamLine(raw: string): ChatStreamEvent | null {
  let data: any;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (data.error) return { type: "error", message: String(data.error) };
  if (data.done) return { type: "done", reply: data.reply ?? "" };
  if (data.tool_start) {
    return {
      type: "tool_start",
      toolId: data.tool_start.tool_id,
      name: data.tool_start.name,
      context: data.tool_start.context,
      // Exact primary argument (full command/path/query) -- `context` is an
      // 80-char label; the UI shows this verbatim in the shell block.
      detail: data.tool_start.detail,
    };
  }
  if (data.tool_complete) {
    return {
      type: "tool_complete",
      toolId: data.tool_complete.tool_id,
      name: data.tool_complete.name,
      summary: data.tool_complete.summary,
    };
  }
  if (data.approval_request) {
    return {
      type: "approval_request",
      streamId: data.approval_request.stream_id,
      command: data.approval_request.command,
      description: data.approval_request.description,
      patternKeys: data.approval_request.pattern_keys,
    };
  }
  if (typeof data.delta === "string") return { type: "delta", text: data.delta };
  return null;
}

/** Text-mode streaming send -- hits the SSE subprocess path (full tool-calling),
 * unlike useSendChatMessage's one-shot POST. No file-upload support (GET-only). */
export function useStreamChatMessage(agentId: string | undefined) {
  const queryClient = useQueryClient();
  return async function streamMessage(
    sessionId: string,
    message: string,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
    options?: { regenerate?: boolean; targetAgentId?: string; skipUserMessage?: boolean; hidden?: boolean }
  ): Promise<void> {
    const token = getToken() ?? "";
    // Same-origin by default (nginx proxies /api/ to the backend) -- a
    // hardcoded localhost fallback breaks every chat message when the UI
    // is opened via a LAN IP or tunnel hostname ("Failed to fetch").
    const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
    let extraParams = options?.regenerate ? "&regenerate=true" : "";
    if (options?.targetAgentId) extraParams += `&target_agent_id=${options.targetAgentId}`;
    if (options?.skipUserMessage) extraParams += "&skip_user_message=true";
    // Internal priming turn (see ChatPane's primingMessage): persisted
    // wrapped in hidden markers on both sides, dropped from the transcript.
    if (options?.hidden) extraParams += "&hidden=true";
    const url = `${apiBase}${RESOURCE}/sessions/${sessionId}/messages/stream?message=${encodeURIComponent(message)}${extraParams}`;
    const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, signal });
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let lineBuffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        lineBuffer += decoder.decode(value, { stream: true });
        const lines = lineBuffer.split("\n");
        lineBuffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const event = parseChatStreamLine(line.slice(5).trim());
          if (!event) continue;
          onEvent(event);
          if (event.type === "error") throw new Error(event.message);
          if (event.type === "done") {
            queryClient.invalidateQueries({ queryKey: chatKeys.messages(sessionId) });
            queryClient.invalidateQueries({ queryKey: chatKeys.sessions(agentId) });
            queryClient.invalidateQueries({ queryKey: chatKeys.artifacts(sessionId) });
            return;
          }
        }
      }
      // Stream closed without a done/error event: the connection dropped
      // mid-turn. Treating this as success made the in-flight turn vanish
      // from the UI with no trace ("like a refresh"). The backend persists
      // any partial reply -- refetch it, then surface the failure.
      queryClient.invalidateQueries({ queryKey: chatKeys.messages(sessionId) });
      queryClient.invalidateQueries({ queryKey: chatKeys.artifacts(sessionId) });
      throw new Error("connection interrupted mid-response (the partial reply was saved to the conversation)");
    } finally {
      reader.releaseLock();
    }
  };
}

/** choice values match Hermes's own tools/approval.py vocabulary directly
 * (resolve_gateway_approval): "once" allows just this command, "session"
 * also remembers the pattern for the rest of this Hermes session (skips
 * future prompts for the same dangerous-command pattern), "deny" blocks it.
 * Hermes also supports "always" (permanent, cross-session allowlist) but
 * that's a bigger escalation than "remember for this session" -- not
 * exposed here. */
export function useApproveChat() {
  return useMutation({
    mutationFn: ({ streamId, choice }: { streamId: string; choice: "once" | "session" | "deny" }) =>
      apiClient.post<{ status: string }>(`${RESOURCE}/approve`, { stream_id: streamId, choice }),
  });
}

export function useTranscribeAudio() {
  return useMutation({
    mutationFn: async (audioBlob: Blob) => {
      const form = new FormData();
      form.set("audio", audioBlob, "recording.webm");
      return apiClient.postForm<{ text: string }>(`${RESOURCE}/transcribe`, form);
    },
  });
}
