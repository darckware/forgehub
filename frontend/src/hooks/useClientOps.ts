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

export interface FactoryProject {
  id: string;
  name: string;
  status: string;
  product_version_id: string;
  darckware_origin_type?: WorkItemKind | null;
  darckware_origin_id?: string | null;
  created_at?: string | null;
}

export interface FactoryProduct {
  id: string;
  name: string;
  status: string;
  darckware_client_id?: string | null;
  darckware_client_name?: string | null;
}

export interface WorkItemDetail extends WorkItem {
  timeline: { at: string; actor: string; type: string; note?: string | null }[];
  time_entries: {
    id: string;
    billable_hours: number;
    description: string;
    start_time?: string;
    service_type?: string;
    recorded_by?: string | null;
  }[];
  emails: OutboundEmail[];
  /** The Software Factory project opened for this item, if any (Onda 3). */
  project?: FactoryProject | null;
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

// ---------------------------------------------------------------------------
// Onda 2 -- clients, contracts and lead conversion
// ---------------------------------------------------------------------------

export type ContractType = "suporte_horas" | "desenvolvimento";
export type ContractStatus = "ativo" | "suspenso" | "encerrado";

export interface Contract {
  id: string;
  client_account_id: string;
  contract_type: ContractType;
  status: ContractStatus;
  is_active: boolean;
  plan_name: string;
  monthly_hours_quota?: number | null;
  monthly_price?: number | null;
  extra_hour_rate?: number | null;
  billing_cycle_day?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  total_value?: number | null;
  scope_summary?: string | null;
  document_url?: string | null;
  created_by?: string | null;
  hours_used_current_cycle?: number;
  hours_remaining?: number;
  extra_hours?: number;
}

export interface ClientSummary {
  id: string;
  company_name: string;
  contact_name: string;
  email: string;
  is_active: boolean;
  contacts: { id: string; name: string; email: string; phone: string; department: string; is_authorized: boolean; is_primary: boolean }[];
  contracts: Contract[];
  open_tickets: number;
  open_demands: number;
  converted_from_leads: { id: string; name?: string | null; converted_at?: string | null }[];
}

export interface DarckwareLead {
  id: string;
  name?: string | null;
  company?: string | null;
  email?: string | null;
  phone?: string | null;
  need_summary?: string | null;
  client_account_id?: string | null;
  converted_at?: string | null;
}

export interface ConversionProposal {
  id: string;
  lead_id: string;
  lead?: DarckwareLead | null;
  proposed_by: string;
  payload: {
    company_name?: string | null;
    contact_name?: string | null;
    email?: string | null;
    phone?: string | null;
    department?: string | null;
    notes?: string | null;
    contract?: Partial<ContractInput>;
  };
  status: "proposta" | "aprovada" | "rejeitada";
  created_at?: string | null;
}

/** Empty inputs come through as "", NaN (valueAsNumber) or a missing key -- all mean "not set". */
const optionalNumber = (schema: z.ZodNumber) =>
  z.preprocess(
    (v) => (v === undefined || v === "" || v === null || (typeof v === "number" && Number.isNaN(v)) ? undefined : Number(v)),
    schema.optional(),
  );

export const contractSchema = z
  .object({
    contract_type: z.enum(["suporte_horas", "desenvolvimento"]),
    plan_name: z.string().trim().min(1, "required").max(100),
    monthly_hours_quota: optionalNumber(z.number().positive()),
    monthly_price: optionalNumber(z.number().min(0)),
    extra_hour_rate: optionalNumber(z.number().min(0)),
    billing_cycle_day: optionalNumber(z.number().int().min(1).max(28)),
    start_date: z.string().optional(),
    end_date: z.string().optional(),
    total_value: optionalNumber(z.number().min(0)),
    scope_summary: z.string().optional(),
    document_url: z.string().optional(),
  })
  .superRefine((c, ctx) => {
    // Same rule Darckware enforces: a support contract needs its monthly quota and price.
    if (c.contract_type === "suporte_horas") {
      if (c.monthly_hours_quota === undefined) ctx.addIssue({ code: "custom", path: ["monthly_hours_quota"], message: "required" });
      if (c.monthly_price === undefined) ctx.addIssue({ code: "custom", path: ["monthly_price"], message: "required" });
    }
    if (c.start_date && c.end_date && c.end_date < c.start_date) {
      ctx.addIssue({ code: "custom", path: ["end_date"], message: "endBeforeStart" });
    }
  });
export type ContractInput = z.infer<typeof contractSchema>;

export const conversionSchema = z.object({
  company_name: z.string().trim().min(1, "required").max(200),
  contact_name: z.string().trim().min(1, "required").max(200),
  email: z.string().trim().email("email"),
  phone: z.string().optional(),
  department: z.string().optional(),
  existing_client_account_id: z.string().optional(),
  contract: contractSchema,
});
export type ConversionInput = z.infer<typeof conversionSchema>;

/** Drops empty strings so Darckware never receives "" for an optional field. */
export function compact<T extends Record<string, unknown>>(obj: T): Partial<T> {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== "")) as Partial<T>;
}

export function conversionBody(input: ConversionInput) {
  const { existing_client_account_id, contract, ...data } = input;
  return {
    data: { ...compact(data), contract: compact(contract) },
    existing_client_account_id: existing_client_account_id || undefined,
  };
}

export function useDarckwareClient(id?: string) {
  return useQuery<ClientSummary>({
    queryKey: ["client-ops", "client", id],
    queryFn: () => apiClient.get(`${BASE}/clients/${id}`),
    enabled: Boolean(id),
    retry: false,
  });
}

export function useConversions(status = "proposta") {
  return useQuery<{ items: ConversionProposal[] }>({
    queryKey: ["client-ops", "conversions", status],
    queryFn: () => apiClient.get(`${BASE}/conversions${qs({ status })}`),
    retry: false,
  });
}

export function useDarckwareLeads(search: string, enabled: boolean) {
  return useQuery<{ leads: DarckwareLead[] }>({
    queryKey: ["client-ops", "leads", search],
    queryFn: () => apiClient.get(`${BASE}/leads${qs({ search: search || undefined })}`),
    enabled,
    retry: false,
  });
}

export interface ConversionResult {
  client_account_id: string;
  contract: Contract;
  welcome_email_id: string;
}

export function useApproveConversion() {
  const invalidate = useInvalidateClientOps();
  return useMutation<ConversionResult, Error, { id: string; input: ConversionInput }>({
    mutationFn: ({ id, input }) => apiClient.post(`${BASE}/conversions/${id}:approve`, conversionBody(input)),
    onSettled: invalidate,
  });
}

export function useConvertLead() {
  const invalidate = useInvalidateClientOps();
  return useMutation<ConversionResult, Error, { leadId: string; input: ConversionInput; notes?: string }>({
    mutationFn: ({ leadId, input, notes }) =>
      apiClient.post(`${BASE}/leads/${leadId}:convert`, { ...conversionBody(input), notes: notes || undefined }),
    onSettled: invalidate,
  });
}

export function useRejectConversion() {
  const invalidate = useInvalidateClientOps();
  return useMutation<ConversionProposal, Error, { id: string; reason: string }>({
    mutationFn: ({ id, reason }) => apiClient.post(`${BASE}/conversions/${id}:reject`, { reason }),
    onSettled: invalidate,
  });
}

export function useCreateContract() {
  const invalidate = useInvalidateClientOps();
  return useMutation<Contract, Error, { clientId: string; input: ContractInput }>({
    mutationFn: ({ clientId, input }) => apiClient.post(`${BASE}/clients/${clientId}/contracts`, compact(input)),
    onSettled: invalidate,
  });
}

export function useUpdateContract() {
  const invalidate = useInvalidateClientOps();
  return useMutation<Contract, Error, { id: string; changes: Partial<ContractInput> & { status?: ContractStatus } }>({
    mutationFn: ({ id, changes }) => apiClient.patch(`${BASE}/contracts/${id}`, changes),
    onSettled: invalidate,
  });
}


// ---------------------------------------------------------------------------
// Onda 3 -- Software Factory per client
// ---------------------------------------------------------------------------

export interface ClientFactory {
  products: FactoryProduct[];
  projects: FactoryProject[];
  /** Products not linked to any client yet -- candidates to link. */
  unlinked_products: FactoryProduct[];
}

export function useClientFactory(clientId?: string | null) {
  return useQuery<ClientFactory>({
    queryKey: ["client-ops", "factory", clientId],
    queryFn: () => apiClient.get(`${BASE}/clients/${clientId}/factory`),
    enabled: Boolean(clientId),
    retry: false,
  });
}

export function useLinkProduct() {
  const queryClient = useQueryClient();
  return useMutation<FactoryProduct, Error, { clientId: string; productId: string }>({
    mutationFn: ({ clientId, productId }) => apiClient.post(`${BASE}/clients/${clientId}/products`, { product_id: productId }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["client-ops"] });
      void queryClient.invalidateQueries({ queryKey: ["factory", "cockpit"] });
    },
  });
}

export interface CreateProjectInput {
  kind: WorkItemKind;
  id: string;
  product_id?: string;
  new_product_name?: string;
  project_name?: string;
}

export function useCreateProjectFromItem() {
  const queryClient = useQueryClient();
  return useMutation<{ project: FactoryProject; product: FactoryProduct }, Error, CreateProjectInput>({
    mutationFn: ({ kind, id, ...body }) => apiClient.post(`${BASE}/work-items/${kind}/${id}:create-project`, body),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["client-ops"] });
      // the new product/project must show up in the Cockpit and project lists too
      void queryClient.invalidateQueries({ queryKey: ["factory", "cockpit"] });
      void queryClient.invalidateQueries({ queryKey: ["products"] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}


// ---------------------------------------------------------------------------
// Onda 4 -- hours and monthly report
// ---------------------------------------------------------------------------

export interface LogTimeInput {
  ticketId: string;
  start_time: string;
  end_time: string;
  description: string;
  service_type: "remoto" | "presencial";
}

export function useLogTime() {
  const invalidate = useInvalidateClientOps();
  return useMutation<WorkItemDetail, Error, LogTimeInput>({
    mutationFn: ({ ticketId, ...body }) => apiClient.post(`${BASE}/work-items/ticket/${ticketId}:log-time`, body),
    onSettled: invalidate,
  });
}

export interface MonthlyReportResult {
  created: boolean;
  email: OutboundEmail;
  cycle: { start: string; end: string };
}

export function useGenerateMonthlyReport() {
  const invalidate = useInvalidateClientOps();
  return useMutation<MonthlyReportResult, Error, { clientId: string; reference?: string }>({
    mutationFn: ({ clientId, reference }) =>
      apiClient.post(`${BASE}/clients/${clientId}/monthly-report`, { reference: reference || undefined }),
    onSettled: invalidate,
  });
}

/** Local date + "HH:MM" -> ISO instant (the browser's own timezone). */
export function localDateTimeToIso(day: string, hhmm: string): string {
  return new Date(`${day}T${hhmm}:00`).toISOString();
}
