import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Client demands console (2026-10-04) -- backend `api/routes/client_ops.py`.
 * Darckware stores clients, tickets, demands and e-mails; ForgeHub operates
 * them. Nothing here is a ForgeHub table: every query is a live read of
 * Darckware through the backend proxy.
 */

export type WorkItemKind = "ticket" | "demand";
export type WorkItemTipo = "desenvolvimento" | "servico";
export type WorkItemStage = "novo" | "em_andamento" | "aguardando_cliente" | "resolvido" | "fechado";
export const WORK_ITEM_STAGES: WorkItemStage[] = ["novo", "em_andamento", "aguardando_cliente", "resolvido", "fechado"];

export interface OutboundEmail {
  id: string;
  status: string;
  kind: string;
  to_email: string;
  cc?: string | null;
  subject: string;
  body_text: string;
  version: number;
  body_hash: string;
  sender?: { email: string; name: string };
  client_account_id?: string | null;
  demand_id?: string | null;
  ticket_id?: string | null;
  lead_id?: string | null;
  source_system: string;
  created_by: string;
  approved_by?: string | null;
  approved_at?: string | null;
  approval_valid: boolean;
  rejected_reason?: string | null;
  sent_at?: string | null;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  preview_html?: string;
}

export interface WorkItem {
  kind: WorkItemKind;
  id: string;
  title: string;
  description?: string | null;
  client_account_id?: string | null;
  company_name?: string | null;
  tipo: WorkItemTipo;
  category?: string | null;
  status: string;
  stage: WorkItemStage;
  priority?: string | null;
  requester_name?: string | null;
  requester_email?: string | null;
  source?: string | null;
  billable_hours?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkItemDetail extends WorkItem {
  timeline: { at: string; actor: string; type: string; note?: string | null }[];
  time_entries: { id: string; billable_hours: number; description: string }[];
  emails: OutboundEmail[];
}

export interface WorkItemList {
  items: WorkItem[];
  total: number;
  by_stage: Record<WorkItemStage, number>;
}

export interface ClientOpsStatus {
  configured: boolean;
  reachable: boolean;
  approver_configured?: boolean;
  pending_emails: number;
  error?: string;
}

export interface DarckwareClient {
  id: string;
  company_name: string;
  contact_name?: string;
  email?: string;
}

export interface WorkItemFilters {
  client_account_id?: string;
  kind?: WorkItemKind;
  tipo?: WorkItemTipo;
  stage?: WorkItemStage | "open";
}

export interface EmailDraft {
  subject: string;
  body_text: string;
  to_email?: string;
}

export type WorkItemAction = "start" | "wait-customer" | "resolve" | "reopen";

const BASE = "/api/v1/client-ops";

function qs(params: Record<string, string | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v) as [string, string][];
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}

export function useClientOpsStatus() {
  return useQuery<ClientOpsStatus>({
    queryKey: ["client-ops", "status"],
    queryFn: () => apiClient.get(`${BASE}/status`),
    refetchInterval: 60_000,
  });
}

export function useDarckwareClients() {
  return useQuery<{ items: DarckwareClient[] }>({
    queryKey: ["client-ops", "clients"],
    queryFn: () => apiClient.get(`${BASE}/clients`),
    retry: false,
  });
}

export function useWorkItems(filters: WorkItemFilters) {
  return useQuery<WorkItemList>({
    queryKey: ["client-ops", "work-items", filters],
    queryFn: () => apiClient.get(`${BASE}/work-items${qs({ ...filters })}`),
    retry: false,
  });
}

export function useWorkItem(kind?: WorkItemKind, id?: string) {
  return useQuery<WorkItemDetail>({
    queryKey: ["client-ops", "work-item", kind, id],
    queryFn: () => apiClient.get(`${BASE}/work-items/${kind}/${id}`),
    enabled: Boolean(kind && id),
    retry: false,
  });
}

function useInvalidateClientOps() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["client-ops"] });
}

export const workItemCreateSchema = z.object({
  kind: z.enum(["ticket", "demand"]),
  client_account_id: z.string().uuid({ message: "required" }),
  title: z.string().trim().min(1, "required").max(200),
  description: z.string().trim().min(1, "required").max(4000),
  tipo: z.enum(["desenvolvimento", "servico"]),
  priority: z.enum(["baixa", "media", "alta", "urgente"]),
});
export type WorkItemCreateInput = z.infer<typeof workItemCreateSchema>;

export function useCreateWorkItem() {
  const invalidate = useInvalidateClientOps();
  return useMutation<WorkItemDetail, Error, WorkItemCreateInput>({
    mutationFn: (payload) => apiClient.post(`${BASE}/work-items`, payload),
    onSettled: invalidate,
  });
}

export interface WorkItemActionInput {
  kind: WorkItemKind;
  id: string;
  action: WorkItemAction;
  text?: string;
  email?: EmailDraft;
}

/** Body shape per action: resolve takes `resolution`, reopen `reason`, the rest `note`. */
export function actionBody(action: WorkItemAction, text: string | undefined, email?: EmailDraft) {
  if (action === "resolve") return { resolution: text ?? "", email };
  if (action === "reopen") return { reason: text ?? "" };
  return { note: text || undefined, email };
}

export function useWorkItemAction() {
  const invalidate = useInvalidateClientOps();
  return useMutation<WorkItemDetail & { queued_email?: OutboundEmail | null }, Error, WorkItemActionInput>({
    mutationFn: ({ kind, id, action, text, email }) =>
      apiClient.post(`${BASE}/work-items/${kind}/${id}:${action}`, actionBody(action, text, email)),
    onSettled: invalidate,
  });
}

export function useOutboundEmails(status?: string) {
  return useQuery<{ items: OutboundEmail[]; total: number }>({
    queryKey: ["client-ops", "emails", status ?? "all"],
    queryFn: () => apiClient.get(`${BASE}/emails${qs({ status })}`),
    retry: false,
  });
}

export function useOutboundEmail(id?: string) {
  return useQuery<OutboundEmail>({
    queryKey: ["client-ops", "email", id],
    queryFn: () => apiClient.get(`${BASE}/emails/${id}`),
    enabled: Boolean(id),
    retry: false,
  });
}

export function useUpdateOutboundEmail() {
  const invalidate = useInvalidateClientOps();
  return useMutation<OutboundEmail, Error, { id: string; subject?: string; body_text?: string; to_email?: string }>({
    mutationFn: ({ id, ...body }) => apiClient.patch(`${BASE}/emails/${id}`, body),
    onSettled: invalidate,
  });
}

export function useApproveOutboundEmail() {
  const invalidate = useInvalidateClientOps();
  return useMutation<OutboundEmail, Error, { id: string; version: number; body_hash: string }>({
    mutationFn: ({ id, version, body_hash }) => apiClient.post(`${BASE}/emails/${id}:approve`, { version, body_hash }),
    onSettled: invalidate,
  });
}

export function useRejectOutboundEmail() {
  const invalidate = useInvalidateClientOps();
  return useMutation<OutboundEmail, Error, { id: string; reason: string }>({
    mutationFn: ({ id, reason }) => apiClient.post(`${BASE}/emails/${id}:reject`, { reason }),
    onSettled: invalidate,
  });
}

export function useCancelOutboundEmail() {
  const invalidate = useInvalidateClientOps();
  return useMutation<OutboundEmail, Error, string>({
    mutationFn: (id) => apiClient.post(`${BASE}/emails/${id}:cancel`, {}),
    onSettled: invalidate,
  });
}
