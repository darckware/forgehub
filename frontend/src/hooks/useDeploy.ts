import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface DeployInstallation {
  id: string;
  name: string;
  description: string | null;
  group_name: string | null;
  order_index: number;
  container_name: string | null;
  compose_file: string | null;
  restart_command: string | null;
  ports: string[] | null;
  links: { label: string; url: string }[] | null;
  notes: string | null;
  product_id: string | null;
  product_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface DockerContainer {
  id: string;
  name: string;
  image: string;
  status: string;
  ports: string;
  state: "running" | "stopped";
  health: "healthy" | "unhealthy" | "starting" | null;
}

export interface DeployInstallationCreate {
  name: string;
  description?: string | null;
  group_name?: string | null;
  order_index?: number;
  container_name?: string | null;
  compose_file?: string | null;
  restart_command?: string | null;
  ports?: string[] | null;
  links?: { label: string; url: string }[] | null;
  notes?: string | null;
  product_id?: string | null;
}

export type DeployInstallationUpdate = Partial<DeployInstallationCreate>;

export interface DeployGroup {
  id: string;
  name: string;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export interface DeployGroupCreate {
  name: string;
  order_index?: number;
}

export type DeployGroupUpdate = Partial<DeployGroupCreate>;

const INSTALL_KEY = ["deploy", "installations"] as const;
const CONTAINERS_KEY = ["deploy", "containers"] as const;
const GROUPS_KEY = ["deploy", "groups"] as const;

export function useInstallations() {
  return useQuery<DeployInstallation[]>({
    queryKey: INSTALL_KEY,
    queryFn: () => apiClient.get("/api/v1/deploy/installations"),
    staleTime: 30_000,
  });
}

export function useDockerContainers() {
  return useQuery<DockerContainer[]>({
    queryKey: CONTAINERS_KEY,
    queryFn: () => apiClient.get("/api/v1/deploy/containers"),
    staleTime: 15_000,
    retry: false,
  });
}

export function useContainerLogs(containerName: string | null, lines = 200) {
  return useQuery<{ logs: string; container: string }>({
    queryKey: ["deploy", "logs", containerName, lines],
    queryFn: () =>
      apiClient.get(`/api/v1/deploy/containers/${containerName}/logs?lines=${lines}`),
    enabled: !!containerName,
    staleTime: 0,
  });
}

export function useCreateInstallation() {
  const qc = useQueryClient();
  return useMutation<DeployInstallation, Error, DeployInstallationCreate>({
    mutationFn: (data) => apiClient.post("/api/v1/deploy/installations", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: INSTALL_KEY }),
  });
}

export function useUpdateInstallation() {
  const qc = useQueryClient();
  return useMutation<
    DeployInstallation,
    Error,
    { id: string; data: DeployInstallationUpdate }
  >({
    mutationFn: ({ id, data }) =>
      apiClient.put(`/api/v1/deploy/installations/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: INSTALL_KEY }),
  });
}

export function useDeleteInstallation() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/deploy/installations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: INSTALL_KEY }),
  });
}

export function useDeployGroups() {
  return useQuery<DeployGroup[]>({
    queryKey: GROUPS_KEY,
    queryFn: () => apiClient.get("/api/v1/deploy/groups"),
    staleTime: 30_000,
  });
}

export function useCreateDeployGroup() {
  const qc = useQueryClient();
  return useMutation<DeployGroup, Error, DeployGroupCreate>({
    mutationFn: (data) => apiClient.post("/api/v1/deploy/groups", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: GROUPS_KEY }),
  });
}

export function useUpdateDeployGroup() {
  const qc = useQueryClient();
  return useMutation<DeployGroup, Error, { id: string; data: DeployGroupUpdate }>({
    mutationFn: ({ id, data }) => apiClient.put(`/api/v1/deploy/groups/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: GROUPS_KEY });
      // Rename propagates to installations' group_name on the backend.
      qc.invalidateQueries({ queryKey: INSTALL_KEY });
    },
  });
}

export function useDeleteDeployGroup() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/deploy/groups/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: GROUPS_KEY });
      qc.invalidateQueries({ queryKey: INSTALL_KEY });
    },
  });
}

export function useRemoveContainer() {
  const qc = useQueryClient();
  return useMutation<
    { ok: boolean; container: string; installations_removed: number },
    Error,
    string
  >({
    mutationFn: (name) => apiClient.delete(`/api/v1/deploy/containers/${name}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CONTAINERS_KEY });
      qc.invalidateQueries({ queryKey: INSTALL_KEY });
    },
  });
}

export function useRestartContainer() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean; container: string }, Error, string>({
    mutationFn: (name) =>
      apiClient.post(`/api/v1/deploy/containers/${name}/restart`, {}),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: CONTAINERS_KEY }), 3000);
    },
  });
}

export interface DockerVolume {
  name: string;
  driver: string;
  mountpoint: string;
  scope: string;
  labels: Record<string, string>;
  containers: string[];
}

export interface DockerNetworkContainer {
  name: string;
  ipv4: string;
}

export interface DockerNetwork {
  id: string;
  name: string;
  driver: string;
  scope: string;
  internal: boolean;
  ipv6: boolean;
  subnets: string[];
  containers: DockerNetworkContainer[];
}

export interface SyncResult {
  created: number;
  updated: number;
  skipped: number;
  ignored: number;
  names_created: string[];
  names_updated: string[];
}

export function useDockerVolumes() {
  return useQuery<DockerVolume[]>({
    queryKey: ["deploy", "volumes"],
    queryFn: () => apiClient.get("/api/v1/deploy/volumes"),
    staleTime: 30_000,
    retry: false,
  });
}

export function useRemoveVolume() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean; volume: string }, Error, string>({
    mutationFn: (name) => apiClient.delete(`/api/v1/deploy/volumes/${name}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deploy", "volumes"] }),
  });
}

export function useRemoveNetwork() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean; network: string }, Error, string>({
    mutationFn: (name) => apiClient.delete(`/api/v1/deploy/networks/${name}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deploy", "networks"] }),
  });
}

export function useDockerNetworks() {
  return useQuery<DockerNetwork[]>({
    queryKey: ["deploy", "networks"],
    queryFn: () => apiClient.get("/api/v1/deploy/networks"),
    staleTime: 30_000,
    retry: false,
  });
}

export interface DockerImage {
  id: string;
  repository: string;
  tag: string;
  size: string;
  created_since: string;
  dangling: boolean;
  in_use: boolean;
}

export function useDockerImages() {
  return useQuery<DockerImage[]>({
    queryKey: ["deploy", "images"],
    queryFn: () => apiClient.get("/api/v1/deploy/images"),
    staleTime: 30_000,
    retry: false,
  });
}

export function useRemoveImage() {
  const qc = useQueryClient();
  return useMutation<{ ok: boolean; image: string }, Error, string>({
    // `ref` is "repo:tag" (or, for dangling images, the bare ID) -- passed
    // as a query param since a repo can contain slashes (registry
    // namespaces), which would collide with path-segment routing.
    mutationFn: (ref) => apiClient.delete(`/api/v1/deploy/images`, { params: { ref } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deploy", "images"] }),
  });
}

export function useSyncFromDocker() {
  const qc = useQueryClient();
  return useMutation<SyncResult, Error>({
    mutationFn: () => apiClient.post("/api/v1/deploy/sync", {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: INSTALL_KEY }),
  });
}
