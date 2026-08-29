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
  // When set, this session's agent terminal runs from this folder instead
  // of the agent's own profile home (see backend chat.py's /stream +
  // host-bridge/hermes_stream.py's --cwd). Plain path, not tied to a
  // registered Project -- same as the Workspace toolbar's WorkingDirPicker.
  working_directory_path: z.string().nullable().optional(),
  // Exclusive with working_directory_path above -- a session sits in
  // Project XOR Group XOR neither (loose list). See ChatGroup below.
  group_id: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type ChatSession = z.infer<typeof chatSessionSchema>;

export const chatGroupSchema = z.object({
  id: z.string(),
  name: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type ChatGroup = z.infer<typeof chatGroupSchema>;

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
  groups: ["chat-groups"] as const,
};

/** One ChatSession's (or ChatSessionParticipant's) Hermes-side liveness --
 * backs System Control's "Chat Sessions" card (2026-08-24), mirroring
 * useTerminalSessions' tmux liveness check but for a resumed Hermes
 * conversation instead of a pane. See get_chat_sessions_host_status. */
export const chatSessionHostStatusSchema = z.object({
  session_id: z.string(),
  participant_id: z.string().nullable(),
  session_title: z.string(),
  agent_id: z.string(),
  agent_name: z.string(),
  hermes_session_id: z.string(),
  exists: z.boolean(),
  hermes_title: z.string().nullable(),
  last_activity_at: z.number().nullable(),
  message_count: z.number().nullable(),
  running: z.boolean(),
});

export type ChatSessionHostStatus = z.infer<typeof chatSessionHostStatusSchema>;

const chatSessionsHostStatusKey = ["chat-sessions-host-status"] as const;

export function useChatSessionsHostStatus(enabled = true) {
  return useQuery({
    queryKey: chatSessionsHostStatusKey,
    queryFn: () => apiClient.get<ChatSessionHostStatus[]>(`${RESOURCE}/sessions/host-status`),
    enabled,
  });
}

/** Forgets the stored hermes_session_id (session's own, or one
 * participant's) so the next message opens a fresh Hermes session instead
 * of repeating a resume known to fail -- never touches Hermes' own
 * history, see reset_chat_session_hermes_link's docstring. */
export function useResetChatSessionHermesLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, participantId }: { sessionId: string; participantId?: string | null }) =>
      apiClient.post<ChatSession>(`${RESOURCE}/sessions/${sessionId}:reset-hermes-session`, undefined, {
        params: participantId ? { participant_id: participantId } : undefined,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatSessionsHostStatusKey }),
  });
}

/** Permanently deletes a chat session (and its messages) -- the "delete"
 * icon on System Control's Chat Sessions card, mirroring Terminal
 * Sessions' kill button. Distinct from useDeleteChatSession below only in
 * which cache it invalidates: this card lists sessions across every agent
 * (chatSessionsHostStatusKey), not one agent's own list
 * (chatKeys.sessions(agentId)). */
export function useDeleteChatSessionHostStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => apiClient.delete<void>(`${RESOURCE}/sessions/${sessionId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chatSessionsHostStatusKey }),
  });
}

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
    mutationFn: (payload: { agent_id: string; title?: string; working_directory_path?: string | null }) =>
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
      /** Also doubles as "move this chat to a different folder/project"
       * after creation -- same PATCH, no special-cased endpoint. */
      working_directory_path?: string | null;
      /** Moves this chat to a Group -- exclusive with
       * working_directory_path above, enforced backend-side. */
      group_id?: string | null;
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

// --------------------------------------------------------------------------
// ChatGroup -- user-created named folders for the Workspace sidebar (see
// backend db/models/chat.py's ChatGroup docstring). Not scoped to an
// agent, unlike sessions -- one flat roster shared across every tab.
// --------------------------------------------------------------------------

export function useChatGroups() {
  return useQuery({
    queryKey: chatKeys.groups,
    queryFn: () => apiClient.get<ChatGroup[]>(`${RESOURCE}/groups`),
  });
}

export function useCreateChatGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => apiClient.post<ChatGroup>(`${RESOURCE}/groups`, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.groups });
    },
  });
}

export function useUpdateChatGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, name }: { groupId: string; name: string }) =>
      apiClient.patch<ChatGroup>(`${RESOURCE}/groups/${groupId}`, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.groups });
    },
  });
}

export function useDeleteChatGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (groupId: string) => apiClient.delete<void>(`${RESOURCE}/groups/${groupId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.groups });
      // A deleted group's sessions return to the loose list (backend's
      // ON DELETE SET NULL) -- every agent's session list may now show
      // one differently, so invalidate broadly rather than guessing which.
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
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
  | {
      type: "tool_complete";
      toolId: string;
      name: string;
      summary?: string;
      /** Set only for mcp__forgehub_messages__send_agent_message -- the
       * #number of the message it just created (2026-07-28). Lets the UI
       * render a live status card for a mid-conversation delegation
       * instead of just a "done" checkmark -- see FORGEHUB_MESSAGE.md's
       * "Delegating to another agent mid-conversation". */
      demandNumber?: number;
    }
  | { type: "approval_request"; streamId: string; command?: string; description?: string; patternKeys?: string[] }
  /** The backend's ActiveTurn id for this turn (2026-08-14) -- the one thing
   * a live tab needs from the stream to target Stop at this specific turn,
   * since the turn itself now runs detached from this connection (see
   * chat.py's `_run_chat_turn`). Previously unparsed/dropped entirely. */
  | { type: "turn_started"; turnId: string }
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
  if (typeof data.turn_id === "string") return { type: "turn_started", turnId: data.turn_id };
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
      demandNumber: data.tool_complete.demand_number,
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

    // Connection resilience (2026-07-28, see the plan's Fase 5 item 5):
    // a self-maintenance turn against ForgeHub's own repo can trigger a
    // backend restart (uvicorn --reload) at the exact moment this fetch
    // opens -- a brief window where the connection is flat-out refused,
    // not a mid-stream drop. Retry ONLY the initial connect (nothing
    // received yet, so the server has almost certainly not persisted the
    // user message yet either -- safe to resend as-is). Once any SSE
    // bytes have arrived, the server-side persistence may already have
    // happened; no retry from here on -- the existing "connection
    // interrupted mid-response" handling below already covers that
    // without risking a duplicated user turn.
    const CONNECT_RETRY_DELAYS_MS = [1000, 2000];
    let resp: Response | undefined;
    for (let attempt = 0; ; attempt++) {
      try {
        resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, signal });
        break;
      } catch (err) {
        if (signal?.aborted || attempt >= CONNECT_RETRY_DELAYS_MS.length) throw err;
        await new Promise((r) => setTimeout(r, CONNECT_RETRY_DELAYS_MS[attempt]));
      }
    }
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

/** Asks this session's own agent to rewrite a draft per an improvement
 * instruction -- a private utility call, never a real turn (see backend
 * chat.py's stream_improve_prompt docstring). Ported from useChannel.ts's
 * useStreamImprovePrompt, which shipped first for the Channels room
 * (2026-08-06). Resolves to the improved text; the caller decides what to
 * do with it (replace the compose draft, never auto-sent). */
export function useStreamImprovePrompt(sessionId: string) {
  return async function improvePrompt(
    draft: string,
    instruction: string,
    techniqueCode: string,
    signal?: AbortSignal
  ): Promise<string> {
    const token = getToken() ?? "";
    const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
    const url = `${apiBase}${RESOURCE}/sessions/${sessionId}/improve-prompt/stream`;

    const resp = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ draft, instruction, technique_code: techniqueCode }),
      signal,
    });
    if (!resp.ok) {
      // The session-agent lookup fails before any streaming starts -- a
      // plain JSON error, not SSE framing.
      let detail = `HTTP ${resp.status}`;
      try {
        detail = (await resp.json()).detail ?? detail;
      } catch {
        // Body wasn't JSON -- keep the generic HTTP status message.
      }
      throw new Error(detail);
    }
    if (!resp.body) throw new Error("Empty response body");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "message";
    let improvedText: string | null = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
            continue;
          }
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          if (currentEvent === "error") {
            const parsed = JSON.parse(raw || "{}");
            throw new Error(parsed.detail ?? "improve-prompt stream error");
          }
          if (currentEvent === "done") {
            currentEvent = "message";
            continue;
          }
          const parsed = JSON.parse(raw || "{}");
          if (typeof parsed.improved_text === "string") improvedText = parsed.improved_text;
          currentEvent = "message";
        }
      }
    } finally {
      reader.releaseLock();
    }

    if (improvedText === null) throw new Error("The agent didn't return any text.");
    return improvedText;
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

/** Ends a running turn on purpose (2026-08-14) -- the Stop button's actual
 * mechanism now that a turn survives the browser disconnecting on its own
 * (see the backend's `_run_chat_turn`). Aborting the fetch alone no longer
 * stops anything server-side; this is what does. Needs the ActiveTurn id,
 * which arrives as a `turn_started` stream event once the turn has one --
 * before that point there is nothing running yet to stop. */
export function useStopChatTurn() {
  return useMutation({
    mutationFn: ({ sessionId, turnId }: { sessionId: string; turnId: string }) =>
      apiClient.post<{ status: string }>(`${RESOURCE}/sessions/${sessionId}/turns/${turnId}/stop`),
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
