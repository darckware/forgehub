import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface Client {
  id: string;
  name: string;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  support_plan: string | null;
  notes: string | null;
  headscale_tag: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClientCreate {
  name: string;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  support_plan?: string | null;
  notes?: string | null;
}

export type ClientUpdate = Partial<ClientCreate>;

const CLIENTS_KEY = ["clients"] as const;

export function useClients() {
  return useQuery<Client[]>({
    queryKey: CLIENTS_KEY,
    queryFn: () => apiClient.get("/api/v1/clients"),
    staleTime: 30_000,
  });
}

export function useCreateClient() {
  const qc = useQueryClient();
  return useMutation<Client, Error, ClientCreate>({
    mutationFn: (data) => apiClient.post("/api/v1/clients", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLIENTS_KEY }),
  });
}

export function useUpdateClient() {
  const qc = useQueryClient();
  return useMutation<Client, Error, { id: string; data: ClientUpdate }>({
    mutationFn: ({ id, data }) => apiClient.put(`/api/v1/clients/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLIENTS_KEY }),
  });
}

export function useDeleteClient() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/clients/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLIENTS_KEY }),
  });
}
