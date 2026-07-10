import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Governance domain (see docs/SPEC.md 4.8 Governance Domain / PRD.md 5.7, 6.2, 6.5):
 *   approvals, audit_events, policies
 *
 * Approval is the primary entity -- it records the outcome of a gated
 * transition, targeted polymorphically via (entity_type, entity_id).
 * AuditEvent is read-mostly: every major entity transition produces one
 * (create + list/get only, no update/delete, by design -- audit
 * integrity). Policy is a governed rule that approvals are evaluated
 * against.
 *
 * Backend contract (backend/app/api/routes/governance.py), all under the
 * /api/v1/governance prefix:
 *   Approval:   POST/GET /approvals, GET /approvals/{id},
 *               POST /approvals/{id}/approve, POST /approvals/{id}/reject
 *               (no update/delete -- a decided approval is final)
 *   AuditEvent: POST/GET /audit-events, GET /audit-events/{id}
 *   Policy:     POST/GET /policies, GET/PUT/DELETE /policies/{id}
 */

export const APPROVAL_STATUSES = ["pending", "approved", "rejected"] as const;
export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number];

// Free-text discriminator on the backend (Approval.entity_type) -- these
// are the values used elsewhere in this codebase, not an enforced enum.
export const APPROVAL_ENTITY_TYPES = [
  "pipeline_stage_gate",
  "release",
  "skill",
  "change_request",
  "artifact",
] as const;
export type ApprovalEntityType = (typeof APPROVAL_ENTITY_TYPES)[number];

// ---------------------------------------------------------------------------
// Schemas (field names match backend/app/api/schemas/governance.py exactly)
// ---------------------------------------------------------------------------

export const approvalSchema = z.object({
  id: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  approval_type: z.string(),
  status: z.enum(APPROVAL_STATUSES).default("pending"),
  policy_id: z.string().nullable().optional(),
  requested_by: z.string(),
  decided_by: z.string().nullable().optional(),
  comments: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type Approval = z.infer<typeof approvalSchema>;

export const auditEventSchema = z.object({
  id: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  event_type: z.string(),
  actor: z.string(),
  payload: z.record(z.unknown()).nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type AuditEvent = z.infer<typeof auditEventSchema>;

export const policySchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  policy_type: z.string(),
  rules: z.record(z.unknown()).nullable().optional(),
  is_active: z.boolean().default(true),
  entity_type: z.string().nullable().optional(),
  entity_id: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type Policy = z.infer<typeof policySchema>;

// Payload schema (what the create form submits) for the primary entity --
// matches ApprovalCreate (backend/app/api/schemas/governance.py:49-59).
export const approvalCreateSchema = z.object({
  entity_type: z.string().min(1, "Entity type is required").max(100, "Too long"),
  entity_id: z.string().min(1, "Entity ID is required").max(200, "Entity ID is too long"),
  approval_type: z.string().min(1, "Approval type is required").max(100, "Too long"),
  requested_by: z.string().min(1, "Requested by is required").max(150, "Too long"),
  comments: z.string().max(4000, "Too long").optional().or(z.literal("")),
  policy_id: z.string().optional().or(z.literal("")),
});

export type ApprovalCreateInput = z.infer<typeof approvalCreateSchema>;

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const governanceKeys = {
  all: ["governance"] as const,
  detail: (id: string) => ["governance", id] as const,
  auditEvents: ["governance-audit-events"] as const,
  policies: ["governance-policies"] as const,
};

const RESOURCE = "/api/v1/governance";

// ---------------------------------------------------------------------------
// Approval hooks (primary entity)
// ---------------------------------------------------------------------------

export function useApprovals() {
  return useQuery({
    queryKey: governanceKeys.all,
    queryFn: () => apiClient.get<Approval[]>(`${RESOURCE}/approvals`),
  });
}

export function useApproval(id: string | undefined) {
  return useQuery({
    queryKey: governanceKeys.detail(id ?? ""),
    queryFn: () => apiClient.get<Approval>(`${RESOURCE}/approvals/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateApproval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalCreateInput) =>
      apiClient.post<Approval>(`${RESOURCE}/approvals`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: governanceKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Audit event hooks (read-mostly -- no update/delete by design)
// ---------------------------------------------------------------------------

export function useAuditEvents() {
  return useQuery({
    queryKey: governanceKeys.auditEvents,
    queryFn: () => apiClient.get<AuditEvent[]>(`${RESOURCE}/audit-events`),
  });
}

export function useAuditEvent(id: string | undefined) {
  return useQuery({
    queryKey: [...governanceKeys.auditEvents, id],
    queryFn: () => apiClient.get<AuditEvent>(`${RESOURCE}/audit-events/${id}`),
    enabled: Boolean(id),
  });
}

// ---------------------------------------------------------------------------
// Policy hooks
// ---------------------------------------------------------------------------

export function usePolicies() {
  return useQuery({
    queryKey: governanceKeys.policies,
    queryFn: () => apiClient.get<Policy[]>(`${RESOURCE}/policies`),
  });
}

export function usePolicy(id: string | undefined) {
  return useQuery({
    queryKey: [...governanceKeys.policies, id],
    queryFn: () => apiClient.get<Policy>(`${RESOURCE}/policies/${id}`),
    enabled: Boolean(id),
  });
}

export interface PolicyInput {
  name: string;
  description?: string;
  policy_type: string;
  rules?: Record<string, unknown>;
  is_active?: boolean;
  entity_type?: string;
  entity_id?: string;
}

export function useCreatePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PolicyInput) => apiClient.post<Policy>(`${RESOURCE}/policies`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: governanceKeys.policies }),
  });
}

export function useUpdatePolicy(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<PolicyInput>) =>
      apiClient.put<Policy>(`${RESOURCE}/policies/${id}`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: governanceKeys.policies }),
  });
}

export function useDeletePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`${RESOURCE}/policies/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: governanceKeys.policies }),
  });
}
