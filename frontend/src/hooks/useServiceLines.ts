import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface ServiceLine {
  id: string;
  slug: string;
  name: string;
  is_active: boolean;
  description: string | null;
  stages: string[];
  required_documents: string[];
  evidence_types: string[];
  default_agents: string[];
  sla_hours: number | null;
  darckware_contract_type: string | null;
  client_visible: boolean;
}

export function useServiceLines() {
  return useQuery({
    queryKey: ["service-lines"],
    queryFn: () => apiClient.get<ServiceLine[]>("/api/v1/service-lines"),
  });
}
