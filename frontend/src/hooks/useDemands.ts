import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Agent demand inbox (backend/app/api/routes/demand.py): "like an e-mail"
 * agents can send ForgeHub, converted into a Task/Doc/Artifact/Knowledge
 * Base entry (core/conversions.py). Existing /root/docs notes go through
 * the same 4-way conversion via docs.py's /convert (see useConvertContent).
 */

export const DEMAND_STATUSES = ["new", "read", "converted", "archived"] as const;
export type DemandStatus = (typeof DEMAND_STATUSES)[number];

export const CONVERT_TARGETS = [
  "task",
  "doc",
  "artifact",
  "knowledge_base",
  "planning_item",
  "project_doc",
  "quick_task",
] as const;
export type ConvertTarget = (typeof CONVERT_TARGETS)[number];

// Values are i18next keys (convertMenu.targets.*), not literal text --
// ConvertMenu translates them at render time. See CONVERT_TARGETS' JSDoc
// above for the target list itself.
export const CONVERT_TARGET_LABELS: Record<ConvertTarget, string> = {
  task: "targets.task",
  doc: "targets.doc",
  artifact: "targets.artifact",
  knowledge_base: "targets.knowledge_base",
  project_doc: "targets.project_doc",
  quick_task: "targets.quick_task",
  planning_item: "targets.planning_item",
};

export const attachmentSchema = z.object({
  id: z.string(),
  filename: z.string(),
  size_bytes: z.number(),
  content_type: z.string().nullable(),
  created_at: z.string(),
  /** Optional caption given at upload time; null when none. */
  description: z.string().nullable().optional(),
});

export type DemandAttachment = z.infer<typeof attachmentSchema>;

export const demandSchema = z.object({
  id: z.string(),
  // Human-readable display number (#1, #2, ...) -- reference an existing
  // message as another item's origin by typing this instead of its UUID.
  number: z.number(),
  from_agent: z.string(),
  subject: z.string(),
  body: z.string(),
  status: z.enum(DEMAND_STATUSES),
  // Only meaningful while status="archived" -- which Archived subfolder
  // (demand_groups row) this demand is filed under. Null while unarchived,
  // or archived-but-uncategorized (sits in the Archived root).
  group_id: z.string().nullable(),
  converted_entity_type: z.enum(CONVERT_TARGETS).nullable(),
  converted_reference: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  attachments: z.array(attachmentSchema).default([]),
  // Agent dispatch (backend/app/api/routes/demand.py's /dispatch) -- null
  // target_agent_id means this item has no agent yet ("sem agente", sits
  // outside the agent tree in Marcelo's own evaluation queue).
  target_agent_id: z.string().nullable(),
  from_agent_id: z.string().nullable(),
  // Which project this message is about -- classification only (see the
  // "Controle" tab), independent of ConvertPayload.project_id below (that
  // one picks the project a *converted* entity lands in).
  project_id: z.string().nullable(),
  development_request_id: z.string().nullable().default(null),
  command_text: z.string().nullable(),
  // The cwd the recipient agent's run starts in for this message (2026-08-13,
  // see AgentDemand.working_path's own docstring) -- null means the runtime
  // default applies, not "no folder". Used to show which working directory
  // an agent is actually processing in on the Agent Activity board.
  working_path: z.string().nullable().optional(),
  // Mandatory (2026-07-28) -- always "task" or "incubation", never null.
  // "demand" was retired: an auto-generated return message is now Tipo=task
  // too (see reply_to_id below).
  origin_type: z.enum(["task", "incubation"]),
  // ProjectTask.id when origin_type="task" and this message tracks/dispatches
  // that task -- real, resolved row. The compose form resolves this id to a
  // display number itself. Always null
  // for "incubation", which is a classification, not a link.
  origin_id: z.string().nullable(),
  // Stamped automatically by the backend once the linked task's execution
  // is marked "completed" (exact match on origin_id, see
  // task.py's update_task_execution). Never sent by the compose form.
  task_execution_at: z.string().nullable(),
  // The agent's raw output once a dispatch finishes -- recorded on this
  // same message regardless of requires_response ("processamento",
  // 2026-07-28). See reply_to_id below for when a real return message
  // also gets created.
  dispatch_result: z.string().nullable(),
  // "Retorno" -- whether this message expects a response back. Gates
  // whether a real return message gets created on completion (2026-07-28)
  // -- no longer just routing, see reply_to_id.
  requires_response: z.boolean(),
  // Set only on an auto-generated return message -- points back at the
  // message it answers (2026-07-28, replaces the old origin_type="demand"
  // + origin_id link).
  reply_to_id: z.string().nullable(),
  // Scheduled send -- set together with target_agent_id, dispatched
  // automatically by the backend's poll loop once this time is reached.
  scheduled_at: z.string().nullable(),
  dispatch_status: z.enum(["dispatched", "running", "completed", "failed"]).nullable(),
  // Contingência de despacho (2026-08-13): prazo até o qual a execução
  // precisa retornar, quantas vezes já foi despachada e por que a última
  // falhou. `dispatch_attempts` contra DISPATCH_MAX_ATTEMPTS decide se o
  // reprocessamento ainda é oferecido.
  dispatch_deadline_at: z.string().nullable().default(null),
  dispatch_attempts: z.number().default(0),
  dispatch_error: z.string().nullable().default(null),
  agent_run_id: z.string().nullable(),
  // Return routing and incubation are first-class server state. Keeping
  // them in the parsed client model prevents Zod from silently discarding
  // the fields the operator needs to audit ownership and owed feedback.
  channel: z.enum(["workspace", "assistant", "factory", "agent", "telegram"]).nullable().default(null),
  channel_ref: z.string().nullable().default(null),
  feedback_sent_at: z.string().nullable().default(null),
  incubation_owner_id: z.string().nullable().default(null),
  incubation_state: z.enum(["incubating", "decision_pending", "promoted", "dropped"]).nullable().default(null),
  matures_at: z.string().nullable().default(null),
  drop_reason: z.string().nullable().default(null),
});

export type Demand = z.infer<typeof demandSchema>;

/** Entrada (2026-07-27, Marcelo: "a message é como se fosse uma carta, ela
 * anda em cada casa (grupo)", refined 2026-08-15): Incoming is work that
 * *arrived for this agent to run*, which is exactly the self-addressed
 * case -- To left blank resolves to From on submit
 * (DemandFormPanel.tsx's `effectiveTargetAgentId`), and Marcelo's own
 * framing settles which house that lands in: "se o próprio agente que vai
 * executar então ele não tem saída e sim uma entrada". A cross-agent
 * message never visits Incoming at all -- `"pending"` (the only
 * `dispatch_status` value that could have put a cross-agent arrival here)
 * was formally retired 2026-08-15: the backend never wrote it, dispatch
 * goes straight from `NULL` to `"dispatched"` (see
 * `run_scheduled_dispatch_pass`), so the value only ever described a
 * window nothing produced. A cross-agent message instead lives in Outgoing
 * until it starts running, exactly as before.
 *
 * Excludes Running/Completed/Failed (2026-07-28, Marcelo: "as message no
 * Incoming em processamento tem que serem movidas para Running, fim do
 * processamento, deu erro vai para Failed, senão vai para Completed") --
 * each message counts in exactly one of Incoming/Running/Failed/Completed
 * at a time, never two at once. A generated return (`reply_to_id` set) is
 * created already-terminal (`dispatch_status="completed"`, see
 * demand.py's `_finalize_dispatch`), so it goes straight to Completed like
 * any other terminal row -- it never passes through Incoming (reverted
 * 2026-08-15 after a same-day rule change made every reply pile up in
 * Incoming permanently with no further event to move it out; see
 * isCompletedItem's own reply_to_id note below).
 *
 * Shared between pages/demands/index.tsx (the tree's own per-folder
 * counts) and Sidebar.tsx (the global nav badge) -- both must agree, see
 * computeInboxTotalCount below (2026-07-28, Marcelo: "tudo tem que
 * obedecer o total do grupo de entrada... tem que haver sync"). */
export function isIncomingItem(d: Demand, agentId: string): boolean {
  return (
    d.status !== "archived" &&
    d.target_agent_id === agentId &&
    d.target_agent_id === d.from_agent_id &&
    d.dispatch_status !== "dispatched" &&
    d.dispatch_status !== "running" &&
    d.dispatch_status !== "completed" &&
    d.dispatch_status !== "failed"
  );
}

/** Total for the Incoming tree's root badge: System's count (genuinely
 * nobody's -- no target *and* no sender, e.g. a human-composed note with
 * neither field set) plus every agent's *arrived* count. Deliberately not
 * every no-target row: an Incubation item with no target yet still has an
 * owner (`incubation_owner_id`, resolved from `from_agent_id` when target
 * is unset -- see the DB's own `ck_agent_demands_incubation_owner`), so
 * counting it here too would double it into a badge it doesn't belong to
 * (Marcelo, 2026-08-15: "não existe anônima" -- every row has an owner,
 * this badge just wasn't checking for it). The single source of truth
 * every "how many incoming" badge in the app must read from -- see
 * isIncomingItem's docstring for why this stopped being safe to
 * approximate with a broader "status=new" count (2026-07-28). */
export function computeInboxTotalCount(demands: Demand[]): number {
  let total = 0;
  for (const d of demands) {
    if (d.status === "archived") continue;
    if (!d.target_agent_id) {
      if (!d.from_agent_id) total += 1;
    } else if (isIncomingItem(d, d.target_agent_id)) {
      total += 1;
    }
  }
  return total;
}

const dispatchStatusResultSchema = z.object({
  dispatch_status: z.enum(["dispatched", "running", "completed", "failed"]).nullable(),
  // Contingência de despacho (2026-08-13): prazo até o qual a execução
  // precisa retornar, quantas vezes já foi despachada e por que a última
  // falhou. `dispatch_attempts` contra DISPATCH_MAX_ATTEMPTS decide se o
  // reprocessamento ainda é oferecido.
  dispatch_deadline_at: z.string().nullable().default(null),
  dispatch_attempts: z.number().default(0),
  dispatch_error: z.string().nullable().default(null),
  agent_run_id: z.string().nullable(),
  reply_demand_id: z.string().nullable().optional(),
});

export type DispatchStatusResult = z.infer<typeof dispatchStatusResultSchema>;

/** A user-created subfolder inside the Inbox's "Archived" bucket --
 * freely nestable via parent_id. "Incoming" and the "Archived" root
 * itself are NOT rows here, they're derived from Demand.status/group_id
 * (see demandSchema's group_id comment) -- only user-created subfolders
 * get a row. */
export const demandGroupSchema = z.object({
  id: z.string(),
  name: z.string(),
  parent_id: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type DemandGroup = z.infer<typeof demandGroupSchema>;

const convertResultSchema = z.object({
  entity_type: z.enum(CONVERT_TARGETS),
  entity_id: z.string().nullable(),
  reference: z.string(),
});

export type ConvertResult = z.infer<typeof convertResultSchema>;

export interface ConvertPayload {
  target: ConvertTarget;
  title?: string;
  planning_item_id?: string;
  path?: string;
  artifact_type?: string;
  /** planning_item / project_doc / quick_task */
  project_id?: string;
  /** planning_item / quick_task -- one of PLANNING_ITEM_TYPES, defaults to
   * "documentation" server-side when omitted. */
  item_type?: string;
  /** doc -- which área de criação (docs_creation_areas) to write into.
   * Omitted = falls back to the original /root/docs mount server-side. */
  area_id?: string;
}

const RESOURCE = "/api/v1/demands";

export const demandKeys = {
  all: ["demands"] as const,
};

const IN_FLIGHT_DISPATCH_STATUSES = new Set(["dispatched", "running"]);

export function useDemands(statusFilter?: DemandStatus) {
  return useQuery({
    queryKey: [...demandKeys.all, statusFilter ?? "all"],
    // Adaptive: while at least one message is actively dispatching, poll
    // fast so a status change (dispatched -> running -> completed/failed)
    // shows up promptly and the sidebar groups it's counted under
    // recompute right away -- every group count/membership is a `useMemo`
    // keyed on this query's data, so a fresh fetch is the only thing that
    // was ever missing (2026-07-27/28, Marcelo: "para cada mudança de
    // status a messages, tem que recalcular os grupos" -- the groups
    // already did recompute on every fetch, the fetch itself just wasn't
    // frequent enough to catch a run that finished between polls). Falls
    // back to the original 30s cadence once nothing is in flight, so an
    // idle inbox doesn't get hammered.
    refetchInterval: (query) => {
      const data = query.state.data as Demand[] | undefined;
      const hasInFlight = data?.some((d) => d.dispatch_status && IN_FLIGHT_DISPATCH_STATUSES.has(d.dispatch_status));
      return hasInFlight ? 3_000 : 30_000;
    },
    // The fast path only matters if it keeps running while the operator is
    // reading a different browser tab / has this one unfocused -- the
    // default pauses background polling, which would silently undo the
    // whole point of polling faster in the first place.
    refetchIntervalInBackground: true,
    queryFn: async () => {
      const data = await apiClient.get<unknown>(RESOURCE, {
        params: statusFilter ? { status_filter: statusFilter } : undefined,
      });
      return z.array(demandSchema).parse(data);
    },
  });
}

function useInvalidateDemands() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: demandKeys.all });
}

export interface DemandOriginInput {
  /** "Tipo" da mensagem -- mandatory, always "task" or "incubation" (2026-07-28).
   * "task" resolves a real vínculo from a display number (never a UUID)
   * against ProjectTask.number. "incubation" é classificação, não vínculo:
   * marca trabalho estacionado, nunca carrega número e nunca dispara.
   * `originNumber` só faz sentido junto com "task". */
  originType?: "task" | "incubation";
  originNumber?: number;
}

/** JWT-authenticated create -- backs the chat composer's "/demanda"
 * command (see ChatPane.tsx): ForgeHub itself files the row on the
 * logged-in user's behalf, as opposed to /submit's bridge-token path
 * for autonomous host-side agents. Also backs the "New note" panel, which
 * can set a target agent and/or an origin right away instead of a
 * separate PATCH afterward. */
export function useCreateDemand() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: (
      payload: {
        from_agent: string;
        /** Picks a real registered Agent as sender ("From (agent)") --
         * needed for the requires_response relay (see demand.py's
         * get_dispatch_status: a reply routes back to this agent). */
        fromAgentId?: string;
        subject: string;
        body: string;
        targetAgentId?: string;
        /** Which project this message is about -- see demandSchema's
         * project_id comment. */
        projectId?: string;
        developmentRequestId?: string;
        requiresResponse?: boolean;
        /** ISO datetime string -- backend 400s if set without targetAgentId. */
        scheduledAt?: string;
        /** Files straight into Notes (Archived) instead of Incoming --
         * e.g. Origin="Note" compose. Omitted = "new" (Incoming), as before. */
        status?: DemandStatus;
      } & DemandOriginInput
    ) =>
      apiClient.post<Demand>(RESOURCE, {
        from_agent: payload.from_agent,
        from_agent_id: payload.fromAgentId,
        subject: payload.subject,
        body: payload.body,
        target_agent_id: payload.targetAgentId,
        project_id: payload.projectId,
        development_request_id: payload.developmentRequestId,
        origin_type: payload.originType,
        origin_number: payload.originNumber,
        requires_response: payload.requiresResponse ?? false,
        scheduled_at: payload.scheduledAt,
        status: payload.status,
      }),
    onSuccess: invalidate,
  });
}

/** Full edit ("Alterar" button) -- subject/body/target agent/origin, on
 * top of the narrower useUpdateDemandStatus/useMoveDemand mutations below
 * (kept separate since drag-and-drop and status toggles are hot paths that
 * shouldn't need to build this whole payload shape). */
export function useUpdateDemand() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: ({
      id,
      subject,
      body,
      targetAgentId,
      fromAgentId,
      projectId,
      developmentRequestId,
      originType,
      originNumber,
      requiresResponse,
      scheduledAt,
    }: {
      id: string;
      subject?: string;
      body?: string;
      targetAgentId?: string | null;
      fromAgentId?: string | null;
      /** Which project this message is about, or null to clear. */
      projectId?: string | null;
      developmentRequestId?: string | null;
      requiresResponse?: boolean;
      /** ISO datetime string, or null to clear. */
      scheduledAt?: string | null;
    } & DemandOriginInput) =>
      apiClient.patch<Demand>(`${RESOURCE}/${id}`, {
        // Fields left `undefined` here are dropped by JSON.stringify, so
        // they never appear in the PATCH body -- matching the backend's
        // exclude_unset semantics (untouched, not cleared). Callers that
        // want to explicitly clear the origin must pass originType:
        // undefined together with an explicit originNumber: null (backend
        // 400s on only one of the pair being set) -- not needed by the
        // current edit panel, which always sends both or neither.
        subject,
        body,
        target_agent_id: targetAgentId,
        from_agent_id: fromAgentId,
        project_id: projectId,
        development_request_id: developmentRequestId,
        origin_type: originType,
        scheduled_at: scheduledAt,
        origin_number: originNumber,
        requires_response: requiresResponse,
      }),
    onSuccess: invalidate,
  });
}

export function useUpdateDemandStatus() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: DemandStatus }) =>
      apiClient.patch<Demand>(`${RESOURCE}/${id}`, { status }),
    onSuccess: invalidate,
  });
}

/** Inbox drag-and-drop: file a demand into an Archived subfolder
 * (groupId set -- the backend forces status="archived") or drag it back
 * to Incoming (groupId: null, explicit status so it doesn't stay archived). */
export function useMoveDemand() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: ({ id, groupId, status }: { id: string; groupId: string | null; status?: DemandStatus }) =>
      apiClient.patch<Demand>(`${RESOURCE}/${id}`, status ? { group_id: groupId, status } : { group_id: groupId }),
    onSuccess: invalidate,
  });
}

export function useDeleteDemand() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${RESOURCE}/${id}`),
    onSuccess: invalidate,
  });
}

/** Bulk-cleanup for the Messages toolbar's "Keep last N days"/"Clear all"
 * buttons and each sidebar group's cleanup icon -- there's no bulk-delete
 * endpoint, so this fires one DELETE per id (the caller computes which ids
 * qualify, from the already-loaded list -- no extra fetch) and invalidates
 * once at the end. */
export function useCleanupDemands() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: async (ids: string[]) => {
      await Promise.all(ids.map((id) => apiClient.delete<void>(`${RESOURCE}/${id}`)));
      return ids.length;
    },
    onSuccess: invalidate,
  });
}

/** Bulk-archive for a whole sidebar group's archive icon (Completed,
 * Failed) -- same one-PATCH-per-id, invalidate-once shape as
 * useCleanupDemands, just `status: "archived"` instead of DELETE. A
 * finished message (ran, one way or another) doesn't need to keep
 * cluttering Finalizado/Falhas once its result has been seen, but
 * shouldn't be gone outright the way the trash icon next to it makes it
 * gone -- archiving keeps the history, filed under Arquivadas. */
export function useArchiveDemands() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: async (ids: string[]) => {
      await Promise.all(
        ids.map((id) => apiClient.patch<Demand>(`${RESOURCE}/${id}`, { status: "archived" }))
      );
      return ids.length;
    },
    onSuccess: invalidate,
  });
}

/** Máximo de tentativas de despacho por mensagem -- espelha
 * DISPATCH_MAX_ATTEMPTS no backend (db/models/demand.py). Atingido o limite,
 * a UI deixa de oferecer o reprocessamento: insistir sem corrigir a causa só
 * repete a mesma falha. */
export const DISPATCH_MAX_ATTEMPTS = 3;

/** Uma falha pode ser reprocessada? Só falhas, e só enquanto restarem
 * tentativas. Mesmas condições que o backend valida (400/409) -- aqui apenas
 * para não oferecer um botão que já se sabe que será recusado. */
export function canReprocess(demand: Demand): boolean {
  return (
    demand.dispatch_status === "failed" &&
    (demand.dispatch_attempts ?? 0) < DISPATCH_MAX_ATTEMPTS &&
    Boolean(demand.target_agent_id)
  );
}

/** Devolve uma falha à fila de despacho. Não despacha na hora: limpa o
 * estado de execução e deixa o loop agendado pegá-la, então um reprocesso em
 * massa continua respeitando o teto de concorrência em vez de subir dezenas
 * de execuções de uma vez. */
export function useReprocessDemands() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: async (ids: string[]) => {
      // Sequencial, não Promise.all: cada chamada altera a fila que a
      // seguinte lê, e o backend limita por tentativa/estado.
      const done: string[] = [];
      for (const id of ids) {
        await apiClient.post<Demand>(`${RESOURCE}/${id}:reprocess`, {});
        done.push(id);
      }
      return done.length;
    },
    onSuccess: invalidate,
  });
}

export function useConvertDemand() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: string; payload: ConvertPayload }) =>
      convertResultSchema.parse(await apiClient.post<unknown>(`${RESOURCE}/${id}/convert`, payload)),
    onSuccess: invalidate,
  });
}

export interface DispatchPayload {
  targetAgentId?: string;
  replyToSender?: boolean;
  commandText?: string;
}

/** "Send to Outgoing" -- sends this item's context (+ commandText, if any)
 * as a prompt to the target agent's CLI (backend's /dispatch, backed by
 * the host-bridge's governed /v1/agent-runs). Never blocks -- the mutation
 * resolves as soon as the run starts; poll useDispatchStatus for progress. */
export function useDispatchDemand() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: DispatchPayload }) =>
      apiClient.post<Demand>(`${RESOURCE}/${id}/dispatch`, {
        target_agent_id: payload.targetAgentId,
        reply_to_sender: payload.replyToSender ?? false,
        command_text: payload.commandText,
      }),
    onSuccess: invalidate,
  });
}

/** Polls a dispatched item's run status. Only meaningful once
 * dispatch_status *and* agent_run_id are both set -- pass `enabled: false`
 * otherwise (the 400 the backend returns for an item with no agent_run_id
 * isn't worth a request). dispatch_status alone isn't enough: a scheduled
 * dispatch that fails before ever starting a run (e.g. the target agent
 * has no runtime_type) sets dispatch_status="failed" with agent_run_id
 * still NULL, since _execute_dispatch never got that far. */
export function useDispatchStatus(demandId: string, enabled: boolean) {
  const invalidate = useInvalidateDemands();
  return useQuery({
    queryKey: [...demandKeys.all, demandId, "dispatch-status"],
    enabled,
    refetchInterval: (query) => {
      const status = query.state.data?.dispatch_status;
      return status === "dispatched" || status === "running" ? 3_000 : false;
    },
    queryFn: async () => {
      const data = await apiClient.get<unknown>(`${RESOURCE}/${demandId}/dispatch-status`);
      const parsed = dispatchStatusResultSchema.parse(data);
      // A reply item just landed -- refresh the list so it shows up
      // without waiting for the next 30s poll.
      if (parsed.reply_demand_id) invalidate();
      return parsed;
    },
  });
}

export function useUploadDemandAttachment() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: ({
      demandId,
      file,
      description,
    }: {
      demandId: string;
      file: File;
      description?: string;
    }) => {
      const form = new FormData();
      form.append("file", file);
      // Only sent when there is one: the backend stores "" as NULL anyway,
      // and an empty part just adds noise to the request.
      if (description?.trim()) form.append("description", description.trim());
      return apiClient.postForm<DemandAttachment>(`${RESOURCE}/${demandId}/attachments`, form);
    },
    onSuccess: invalidate,
  });
}

export function useDeleteDemandAttachment() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: ({ demandId, attachmentId }: { demandId: string; attachmentId: string }) =>
      apiClient.delete<void>(`${RESOURCE}/${demandId}/attachments/${attachmentId}`),
    onSuccess: invalidate,
  });
}

export async function downloadDemandAttachment(demandId: string, attachment: DemandAttachment): Promise<void> {
  const { blob } = await apiClient.downloadFile(`${RESOURCE}/${demandId}/attachments/${attachment.id}/download`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = attachment.filename;
  a.click();
  URL.revokeObjectURL(url);
}

const GROUPS_RESOURCE = `${RESOURCE}/groups`;

export const demandGroupKeys = {
  all: ["demand-groups"] as const,
};

export function useDemandGroups() {
  return useQuery({
    queryKey: demandGroupKeys.all,
    queryFn: async () => {
      const data = await apiClient.get<unknown>(GROUPS_RESOURCE);
      return z.array(demandGroupSchema).parse(data);
    },
  });
}

function useInvalidateDemandGroups() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: demandGroupKeys.all });
}

export function useCreateDemandGroup() {
  const invalidate = useInvalidateDemandGroups();
  return useMutation({
    mutationFn: (payload: { name: string; parent_id?: string | null }) =>
      apiClient.post<DemandGroup>(GROUPS_RESOURCE, payload),
    onSuccess: invalidate,
  });
}

/** Rename and/or reparent (drag a folder onto another folder, or onto the
 * Archived root by passing parentId: null). */
export function useUpdateDemandGroup() {
  const invalidate = useInvalidateDemandGroups();
  return useMutation({
    mutationFn: ({ id, name, parentId }: { id: string; name?: string; parentId?: string | null }) => {
      const payload: { name?: string; parent_id?: string | null } = {};
      if (name !== undefined) payload.name = name;
      if (parentId !== undefined) payload.parent_id = parentId;
      return apiClient.patch<DemandGroup>(`${GROUPS_RESOURCE}/${id}`, payload);
    },
    onSuccess: invalidate,
  });
}

/** Limpa o grupo Arquivadas por inteiro: as mensagens **e** as subpastas.
 *
 * O ícone de limpeza do grupo apagava só mensagens, então com a caixa já
 * vazia ele não fazia nada visível — as pastas continuavam na árvore e o
 * clique parecia não funcionar (2026-08-13, Marcelo: "o icone de excluir na
 * pasta de arquivadas não está funcionando. clico e não limpa"). Se o grupo
 * mostra pastas, limpar o grupo tem de levá-las.
 *
 * Mensagens primeiro: apagar uma pasta só desprende as mensagens dela
 * (ondelete=SET NULL), então a ordem inversa deixaria mensagens órfãs na
 * raiz de Arquivadas. Só as pastas raiz são pedidas — as filhas caem por
 * cascade, e pedir a exclusão de uma já removida daria 404. */
export function useCleanupArchived() {
  const invalidate = useInvalidateDemands();
  const invalidateGroups = useInvalidateDemandGroups();
  return useMutation({
    mutationFn: async ({ demandIds, rootGroupIds }: { demandIds: string[]; rootGroupIds: string[] }) => {
      await Promise.all(demandIds.map((id) => apiClient.delete<void>(`${RESOURCE}/${id}`)));
      for (const id of rootGroupIds) {
        await apiClient.delete<void>(`${GROUPS_RESOURCE}/${id}`);
      }
      return demandIds.length + rootGroupIds.length;
    },
    onSuccess: () => {
      invalidate();
      invalidateGroups();
    },
  });
}

export function useDeleteDemandGroup() {
  const invalidate = useInvalidateDemandGroups();
  const invalidateDemands = useInvalidateDemands();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${GROUPS_RESOURCE}/${id}`),
    onSuccess: () => {
      invalidate();
      // Demands filed under the deleted folder fall back to the Archived
      // root server-side (ondelete=SET NULL) -- refresh the list too.
      invalidateDemands();
    },
  });
}

/** Convert an existing /root/docs note/annotation the same way a demand
 * converts -- POST /api/v1/docs/convert, sourcing content from the file
 * instead of a demand row. */
export function useConvertDoc() {
  return useMutation({
    mutationFn: async ({
      sourcePath,
      payload,
    }: {
      sourcePath: string;
      payload: ConvertPayload;
    }) =>
      convertResultSchema.parse(
        await apiClient.post<unknown>("/api/v1/docs/convert", {
          ...payload,
          source_path: sourcePath,
        })
      ),
  });
}
