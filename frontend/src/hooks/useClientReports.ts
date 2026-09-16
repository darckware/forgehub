import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface ClientReport {
  id: string;
  client_id: string;
  kind: "monthly" | "on_demand";
  period_start: string;
  period_end: string;
  irregularity_id: string | null;
  generated_at: string;
  generated_by_user_id: string | null;
  reviewed_at: string | null;
  reviewed_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClientReportDetail extends ClientReport {
  snapshot: Record<string, unknown>;
}

export interface GenerateReportPayload {
  period_start: string;
  period_end: string;
  irregularity_id?: string | null;
}

export interface GenerateMonthlyReportPayload {
  month: string;
}

export interface ReadCredential {
  id: string;
  client_id: string;
  expires_at: string | null;
  revoked_at: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReadCredentialIssued {
  credential: ReadCredential;
  token: string;
}

export function useClientReports(clientId: string) {
  return useQuery({
    queryKey: ["client-reports", clientId],
    queryFn: () => apiClient.get<ClientReport[]>(`/api/v1/clients/${clientId}/reports`),
    enabled: Boolean(clientId),
  });
}

export function useClientReport(reportId: string) {
  return useQuery({
    queryKey: ["client-report", reportId],
    queryFn: () => apiClient.get<ClientReportDetail>(`/api/v1/client-reports/${reportId}`),
    enabled: Boolean(reportId),
  });
}

export function useGenerateClientReport(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: GenerateReportPayload) =>
      apiClient.post<ClientReport>(`/api/v1/clients/${clientId}/reports`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["client-reports", clientId] });
    },
  });
}

export function useGenerateMonthlyReport(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: GenerateMonthlyReportPayload) =>
      apiClient.post<ClientReport>(`/api/v1/clients/${clientId}/reports/monthly`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["client-reports", clientId] });
    },
  });
}

export function useReviewClientReport(clientId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reportId, reviewed }: { reportId: string; reviewed: boolean }) =>
      apiClient.patch<ClientReport>(`/api/v1/client-reports/${reportId}/review`, { reviewed }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["client-reports", clientId] });
      queryClient.invalidateQueries({ queryKey: ["client-report"] });
    },
  });
}

export async function downloadReportFile(reportId: string): Promise<void> {
  const { blob, filename } = await apiClient.downloadFile(`/api/v1/client-reports/${reportId}/download`);
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || `client-report-${reportId}.html`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
