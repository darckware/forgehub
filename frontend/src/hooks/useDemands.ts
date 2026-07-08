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

export const CONVERT_TARGET_LABELS: Record<ConvertTarget, string> = {
  task: "Task (item existente)",
  doc: "Documento",
  artifact: "Artefato",
  knowledge_base: "Base de Conhecimento",
  project_doc: "Projeto específico (doc)",
  quick_task: "Task avulsa (novo item)",
  planning_item: "Planejamento do projeto",
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
  converted_entity_type: z.enum(CONVERT_TARGETS).nullable(),
  converted_reference: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  attachments: z.array(attachmentSchema).default([]),
});

export type Demand = z.infer<typeof demandSchema>;

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
}

const RESOURCE = "/api/v1/demands";

export const demandKeys = {
  all: ["demands"] as const,
};

export function useDemands(statusFilter?: DemandStatus) {
  return useQuery({
    queryKey: [...demandKeys.all, statusFilter ?? "all"],
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

/** "Encaminhar pro Telegram" -- proxies through the backend to Hermes's
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
