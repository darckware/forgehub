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
});

export type DemandAttachment = z.infer<typeof attachmentSchema>;

export const demandSchema = z.object({
  id: z.string(),
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
});

export type Demand = z.infer<typeof demandSchema>;

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

export function useDemands(statusFilter?: DemandStatus) {
  return useQuery({
    queryKey: [...demandKeys.all, statusFilter ?? "all"],
    refetchInterval: 30_000,
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

/** JWT-authenticated create -- backs the chat composer's "/demanda"
 * command (see ChatPane.tsx): ForgeHub itself files the row on the
 * logged-in user's behalf, as opposed to /submit's bridge-token path
 * for autonomous host-side agents. */
export function useCreateDemand() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: (payload: { from_agent: string; subject: string; body: string }) =>
      apiClient.post<Demand>(RESOURCE, payload),
    onSuccess: invalidate,
  });
}

/** "Notify via Telegram" -- proxies through the backend to Hermes's
 * cross-channel gateway (backend/app/api/routes/demand.py's
 * /notify-telegram, host-bridge/send_message.py). No target picker: it
 * always goes to the configured home channel (the user's own Telegram). */
export function useNotifyTelegram() {
  return useMutation({
    mutationFn: (demandId: string) =>
      apiClient.post<{ success?: boolean; note?: string }>(`${RESOURCE}/${demandId}/notify-telegram`, {}),
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

export function useConvertDemand() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: string; payload: ConvertPayload }) =>
      convertResultSchema.parse(await apiClient.post<unknown>(`${RESOURCE}/${id}/convert`, payload)),
    onSuccess: invalidate,
  });
}

export function useUploadDemandAttachment() {
  const invalidate = useInvalidateDemands();
  return useMutation({
    mutationFn: ({ demandId, file }: { demandId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
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
