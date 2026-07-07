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

export const CONVERT_TARGETS = ["task", "doc", "artifact", "knowledge_base"] as const;
export type ConvertTarget = (typeof CONVERT_TARGETS)[number];

export const CONVERT_TARGET_LABELS: Record<ConvertTarget, string> = {
  task: "Task",
  doc: "Documento",
  artifact: "Artefato",
  knowledge_base: "Knowledge Base",
};

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
