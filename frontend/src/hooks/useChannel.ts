import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient, getToken } from "@/lib/api";

/**
 * ChatChannel domain -- a real-time room where the logged-in human + N
 * registered Agents share one transcript, distinct from useChat.ts's
 * ChatSession (1 human + 1 owning agent, no shared context). See backend
 * db/models/channel.py's module docstring for the full design rationale.
 */

export const chatChannelMemberSchema = z.object({
  id: z.string(),
  channel_id: z.string(),
  agent_id: z.string().nullable(),
  is_human: z.boolean(),
  hermes_session_id: z.string().nullable().optional(),
  muted: z.boolean(),
  // This agent's function *in this channel* (2026-08-05, see
  // docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md) -- may
  // diverge from the agent's own default_role. Null for the human row.
  role: z.string().nullable().optional(),
  created_at: z.string(),
});

export type ChatChannelMember = z.infer<typeof chatChannelMemberSchema>;

export const chatChannelSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  // Mutable at any time via useAttachChannelProject/useDetachChannelProject
  // -- never a creation-time-only choice (see backend module docstring:
  // "add a project like an MCP").
  project_id: z.string().nullable().optional(),
  working_directory_path: z.string().nullable().optional(),
  archived: z.boolean(),
  turn_policy: z.string(),
  created_by: z.string().nullable().optional(),
  // Purely informational -- "who Marcelo intends as the operational
  // coordinator among this channel's agent members" (2026-08-05, see
  // docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md). Grants no
  // authority by itself; real approval authority is a separate
  // AuthorityDelegation grant.
  orchestrator_agent_id: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type ChatChannel = z.infer<typeof chatChannelSchema>;

export const chatChannelWithMembersSchema = chatChannelSchema.extend({
  members: z.array(chatChannelMemberSchema).default([]),
});

export type ChatChannelWithMembers = z.infer<typeof chatChannelWithMembersSchema>;

// Only the fields the member picker needs from a suggested
// ProjectAgentMembership -- see backend schemas/orchestration.py's
// ProjectAgentMembershipOut for the full shape.
export const suggestedProjectMemberSchema = z.object({
  id: z.string(),
  agent_id: z.string().nullable(),
  sub_agent_id: z.string().nullable(),
  role: z.string(),
});

export const chatChannelCreateResultSchema = z.object({
  channel: chatChannelWithMembersSchema,
  suggested_project_members: z.array(suggestedProjectMemberSchema).default([]),
});

export type ChatChannelCreateResult = z.infer<typeof chatChannelCreateResultSchema>;

export const chatChannelMessageSchema = z.object({
  id: z.string(),
  channel_id: z.string(),
  author_type: z.enum(["human", "agent", "system"]),
  author_agent_id: z.string().nullable().optional(),
  author_label: z.string().nullable().optional(),
  content: z.string(),
  mentioned_agent_ids: z.array(z.string()).nullable().optional(),
  // Set once this message triggered a real Message-domain dispatch (see
  // useDispatchChannelMessage) -- the channel narrates/links to it, never
  // owns execution state itself.
  triggered_demand_id: z.string().nullable().optional(),
  thinking_seconds: z.number().nullable().optional(),
  attachment_names: z.string().nullable().optional(),
  created_at: z.string(),
});

export type ChatChannelMessage = z.infer<typeof chatChannelMessageSchema>;

export const CHANNEL_TASK_STATUSES = ["todo", "doing", "done"] as const;

export const chatChannelTaskSchema = z.object({
  id: z.string(),
  channel_id: z.string(),
  title: z.string(),
  status: z.enum(CHANNEL_TASK_STATUSES),
  assignee_agent_id: z.string().nullable().optional(),
  created_message_id: z.string().nullable().optional(),
  // Null until promoted -- see usePromoteChannelTask. This row stays
  // display-only once set; the real ProjectTask is the source of truth.
  project_task_id: z.string().nullable().optional(),
  // -- 2026-08-05 additions, see
  // docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md --
  role_required: z.string().nullable().optional(),
  created_by_agent_id: z.string().nullable().optional(),
  // Points at a real governance.Approval when an agent proposed this task
  // FOR ANOTHER agent -- null means it never needed anyone's sign-off.
  approval_id: z.string().nullable().optional(),
  // Read-only, computed from the joined Approval row -- "pending" blocks
  // the task in the UI; decide it via the existing Governance approve/
  // reject actions (useApproveApproval/useRejectApproval), not anything
  // channel-specific.
  approval_status: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type ChatChannelTask = z.infer<typeof chatChannelTaskSchema>;

const RESOURCE = "/api/v1/channels";

export const channelKeys = {
  list: (projectId?: string) => ["channels", projectId ?? "all"] as const,
  detail: (channelId: string) => ["channels", "detail", channelId] as const,
  messages: (channelId: string) => ["channels", "messages", channelId] as const,
  tasks: (channelId: string) => ["channels", "tasks", channelId] as const,
};

export function useChannels(projectId?: string, includeArchived = false) {
  return useQuery({
    queryKey: channelKeys.list(projectId),
    queryFn: () =>
      apiClient.get<ChatChannel[]>(RESOURCE, {
        params: { project_id: projectId, include_archived: includeArchived },
      }),
  });
}

export function useChannel(channelId: string | undefined) {
  return useQuery({
    queryKey: channelKeys.detail(channelId ?? ""),
    queryFn: () => apiClient.get<ChatChannelWithMembers>(`${RESOURCE}/${channelId}`),
    enabled: Boolean(channelId),
    // A delegated agent can add/remove a member or change a role via its
    // own agt_ credential, straight against the API -- entirely outside
    // this tab's own mutation hooks, so their onSuccess invalidation
    // never fires. Polling is what actually picks that up (2026-08-06,
    // Marcelo: "quando o agente solicitar as configurações no canal é
    // preciso dar uma atualização no display... para mostrar os ajustes
    // nos agentes do canal e suas funções"). Same interval class as
    // useRemoteAccess/useSystemStats' own polling.
    refetchInterval: 15_000,
  });
}

export function useCreateChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      name: string;
      description?: string | null;
      project_id?: string | null;
      working_directory_path?: string | null;
      /** Explicit choice made right now, at creation -- never derived from
       * the project's team even when project_id is set. See
       * suggested_project_members on the result for candidates to offer
       * the user, not to auto-apply. */
      member_agent_ids: string[];
      /** Per-member override of the Agent.default_role prefill, keyed by
       * agent_id -- lets the human pick each specialist's function right
       * at creation time (2026-08-05). Omit an agent_id to keep its
       * default_role prefill. */
      member_roles?: Record<string, string>;
      /** Must be one of member_agent_ids. See ChatChannel.orchestrator_agent_id. */
      orchestrator_agent_id?: string | null;
    }) => apiClient.post<ChatChannelCreateResult>(RESOURCE, payload),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: channelKeys.list(result.channel.project_id ?? undefined) });
      queryClient.invalidateQueries({ queryKey: channelKeys.list() });
    },
  });
}

export function useUpdateChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      { channelId, ...payload }: {
        channelId: string;
        name?: string;
        description?: string | null;
        archived?: boolean;
        orchestrator_agent_id?: string | null;
      }
    ) => apiClient.patch<ChatChannel>(`${RESOURCE}/${channelId}`, payload),
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: channelKeys.detail(channel.id) });
      queryClient.invalidateQueries({ queryKey: channelKeys.list() });
    },
  });
}

export function useDeleteChannel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: string) => apiClient.delete<void>(`${RESOURCE}/${channelId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.list() });
    },
  });
}

/** Lighter than useDeleteChannel -- wipes the transcript (and every
 * member's hermes_session_id, see the backend route's docstring) but
 * keeps the channel/membership/tasks (2026-08-06, Marcelo: "adicione um
 * icone de limpeza do chat"). */
export function useClearChannelMessages() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: string) => apiClient.delete<void>(`${RESOURCE}/${channelId}/messages`),
    onSuccess: (_data, channelId) => {
      queryClient.invalidateQueries({ queryKey: channelKeys.messages(channelId) });
      queryClient.invalidateQueries({ queryKey: channelKeys.detail(channelId) });
    },
  });
}

/** The "add a project to the conversation like an MCP" action -- mutable at
 * any point, not just at creation. Never touches membership. */
export function useAttachChannelProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ channelId, projectId }: { channelId: string; projectId: string }) =>
      apiClient.post<ChatChannel>(`${RESOURCE}/${channelId}/project`, { project_id: projectId }),
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: channelKeys.detail(channel.id) });
      queryClient.invalidateQueries({ queryKey: channelKeys.list() });
    },
  });
}

export function useDetachChannelProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (channelId: string) => apiClient.delete<ChatChannel>(`${RESOURCE}/${channelId}/project`),
    onSuccess: (channel) => {
      queryClient.invalidateQueries({ queryKey: channelKeys.detail(channel.id) });
      queryClient.invalidateQueries({ queryKey: channelKeys.list() });
    },
  });
}

export function useAddChannelMember(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) =>
      apiClient.post<ChatChannelMember>(`${RESOURCE}/${channelId}/members`, { agent_id: agentId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.detail(channelId) });
    },
  });
}

/** Sets/edits a member's function *in this channel* -- see
 * chatChannelMemberSchema.role's docstring. Marcelo-only in the UI. */
export function useUpdateChannelMember(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: string | null }) =>
      apiClient.patch<ChatChannelMember>(`${RESOURCE}/${channelId}/members/${memberId}`, { role }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.detail(channelId) });
    },
  });
}

export function useRemoveChannelMember(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) => apiClient.delete<void>(`${RESOURCE}/${channelId}/members/${memberId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.detail(channelId) });
    },
  });
}

export function useChannelMessages(channelId: string | undefined) {
  return useQuery({
    queryKey: channelKeys.messages(channelId ?? ""),
    queryFn: () => apiClient.get<ChatChannelMessage[]>(`${RESOURCE}/${channelId}/messages`),
    enabled: Boolean(channelId),
  });
}

/** Non-streaming send -- posts the human turn and waits for every
 * #-mentioned member's full reply before returning. Prefer
 * useStreamChannelMessage in the UI so mentioned agents' replies appear as
 * they finish rather than all at once. */
export function usePostChannelMessage(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { content: string; attachment_names?: string | null }) =>
      apiClient.post<ChatChannelMessage[]>(`${RESOURCE}/${channelId}/messages`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.messages(channelId) });
    },
  });
}

/** SSE stream: one event per completed message (human echo, then each
 * #-mentioned agent's full reply as its turn finishes) -- see backend
 * channel.py's stream_channel_message docstring for why this is
 * per-message rather than per-token. */
export function useStreamChannelMessage(channelId: string) {
  const queryClient = useQueryClient();
  return async function streamMessage(
    content: string,
    onMessage: (message: ChatChannelMessage) => void,
    signal?: AbortSignal,
    attachmentNames?: string
  ): Promise<void> {
    const token = getToken() ?? "";
    const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
    let url = `${apiBase}${RESOURCE}/${channelId}/messages/stream?content=${encodeURIComponent(content)}`;
    if (attachmentNames) url += `&attachment_names=${encodeURIComponent(attachmentNames)}`;

    const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, signal });
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "message";

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
            throw new Error(parsed.detail ?? "channel stream error");
          }
          if (currentEvent === "done") {
            currentEvent = "message";
            continue;
          }
          const parsed = chatChannelMessageSchema.safeParse(JSON.parse(raw));
          if (parsed.success) onMessage(parsed.data);
          currentEvent = "message";
        }
      }
    } finally {
      reader.releaseLock();
      queryClient.invalidateQueries({ queryKey: channelKeys.messages(channelId) });
    }
  };
}

/** Asks the channel's orchestrator to rewrite a draft per an improvement
 * instruction -- a private utility call, never a real channel turn (see
 * backend channel.py's stream_improve_prompt docstring). Resolves to the
 * improved text; the caller decides what to do with it (replace the
 * compose draft, never auto-sent). */
export function useStreamImprovePrompt(channelId: string) {
  return async function improvePrompt(
    draft: string,
    instruction: string,
    signal?: AbortSignal
  ): Promise<string> {
    const token = getToken() ?? "";
    const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
    const url =
      `${apiBase}${RESOURCE}/${channelId}/improve-prompt/stream` +
      `?draft=${encodeURIComponent(draft)}&instruction=${encodeURIComponent(instruction)}`;

    const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, signal });
    if (!resp.ok) {
      // The orchestrator precondition fails before any streaming starts
      // (see the backend docstring) -- a plain JSON 400, not SSE framing.
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

    if (improvedText === null) throw new Error("The orchestrator didn't return any text.");
    return improvedText;
  };
}

/** Explicit, never-automatic bridge from "conversation" to "real
 * execution" -- creates/dispatches a real Message-domain AgentDemand
 * through the same pipeline every other task dispatch uses. */
export function useDispatchChannelMessage(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, agentId, projectTaskId }: { messageId: string; agentId: string; projectTaskId?: string | null }) =>
      apiClient.post<ChatChannelMessage>(`${RESOURCE}/${channelId}/messages/${messageId}:dispatch-task`, {
        agent_id: agentId,
        project_task_id: projectTaskId ?? null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.messages(channelId) });
    },
  });
}

// --------------------------------------------------------------------------
// Lightweight channel tasks
// --------------------------------------------------------------------------

export function useChannelTasks(channelId: string | undefined) {
  return useQuery({
    queryKey: channelKeys.tasks(channelId ?? ""),
    queryFn: () => apiClient.get<ChatChannelTask[]>(`${RESOURCE}/${channelId}/tasks`),
    enabled: Boolean(channelId),
  });
}

export function useCreateChannelTask(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      title: string;
      assignee_agent_id?: string | null;
      created_message_id?: string | null;
      promote_immediately?: boolean;
    }) => apiClient.post<ChatChannelTask>(`${RESOURCE}/${channelId}/tasks`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.tasks(channelId) });
    },
  });
}

export function useUpdateChannelTask(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, ...payload }: { taskId: string; title?: string; status?: string; assignee_agent_id?: string | null }) =>
      apiClient.patch<ChatChannelTask>(`${RESOURCE}/${channelId}/tasks/${taskId}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.tasks(channelId) });
    },
  });
}

/** Reuses the Messages domain's existing "quick_task" conversion verbatim
 * (see backend core/conversions.py) -- only valid once the channel has a
 * project attached. */
export function usePromoteChannelTask(channelId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => apiClient.post<ChatChannelTask>(`${RESOURCE}/${channelId}/tasks/${taskId}:promote`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: channelKeys.tasks(channelId) });
    },
  });
}
