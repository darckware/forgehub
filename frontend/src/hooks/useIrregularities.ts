import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface Irregularity {
  id: string;
  workstation_id: string;
  rule_key: string;
  severity: "info" | "warning" | "critical";
  detail: string;
  status: "open" | "acknowledged" | "resolved";
  detected_at: string;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
}

export interface IrregularityFilters {
  status_filter?: string;
  severity?: string;
  workstation_id?: string;
}

export function useIrregularities(filters: IrregularityFilters = {}) {
  return useQuery({
    queryKey: ["irregularities", filters],
    // Spread into a fresh object literal for the `params` call: a named
    // interface variable (no index signature) fails RequestOptions.params'
    // Record<string, ...> assignability check under this repo's strict tsc
    // settings, while a fresh literal with the same keys/values does not --
    // same request payload, just satisfies the type checker.
    queryFn: () => apiClient.get<Irregularity[]>("/api/v1/irregularities", { params: { ...filters } }),
  });
}

export function useUpdateIrregularityStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "acknowledged" | "resolved" }) =>
      apiClient.patch<Irregularity>(`/api/v1/irregularities/${id}`, { body: { status } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["irregularities"] });
    },
  });
}
