import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface WorkspaceBrowserState {
  running: boolean;
  cdp_url: string;
  url: string;
  title: string;
  ready_state: string;
  viewport_width: number;
  viewport_height: number;
  image_base64: string | null;
  captured_at: string;
}

export type WebAutomationAction = "navigate" | "click" | "type" | "select" | "press" | "scroll" | "wait" | "assert_text";

export interface WebAutomationStep {
  action: WebAutomationAction;
  selector?: string;
  value?: string;
  url?: string;
  delta_y?: number;
  wait_ms?: number;
}

export interface WebAutomationRoutine {
  id: string;
  product_id: string;
  name: string;
  description?: string | null;
  steps: WebAutomationStep[];
  created_at: string;
  updated_at: string;
}

export interface WebAutomationRun {
  routine_id: string;
  status: "passed" | "failed";
  steps: Array<{ index: number; action: string; status: string; outcome: string }>;
  browser: WorkspaceBrowserState;
}

const browserKey = ["workspace-browser"] as const;

export function useWorkspaceBrowserState(enabled: boolean) {
  return useQuery<WorkspaceBrowserState>({
    queryKey: browserKey,
    queryFn: () => apiClient.get("/api/v1/workspace-browser/state"),
    enabled,
    refetchInterval: enabled ? 1_250 : false,
    retry: false,
  });
}

function useBrowserCommand<T>(path: string) {
  const queryClient = useQueryClient();
  return useMutation<WorkspaceBrowserState, Error, T>({
    mutationFn: (payload) => apiClient.post(path, payload),
    onSuccess: (state) => queryClient.setQueryData(browserKey, state),
  });
}

export function useStartWorkspaceBrowser() {
  return useBrowserCommand<{ url: string }>("/api/v1/workspace-browser/start");
}

export function useNavigateWorkspaceBrowser() {
  return useBrowserCommand<{ url: string }>("/api/v1/workspace-browser/navigate");
}

export function useWorkspaceBrowserPointer() {
  return useBrowserCommand<{ x: number; y: number; end_x?: number; end_y?: number }>("/api/v1/workspace-browser/pointer");
}

export function useWorkspaceBrowserText() {
  return useBrowserCommand<{ text: string }>("/api/v1/workspace-browser/text");
}

export function useWorkspaceBrowserScroll() {
  return useBrowserCommand<{ x: number; y: number; delta_y: number }>("/api/v1/workspace-browser/scroll");
}

export function useReloadWorkspaceBrowser() {
  return useBrowserCommand<Record<string, never>>("/api/v1/workspace-browser/reload");
}

export function useBackWorkspaceBrowser() {
  return useBrowserCommand<Record<string, never>>("/api/v1/workspace-browser/back");
}

export function useLoginWorkspaceBrowser() {
  return useBrowserCommand<{ url: string }>("/api/v1/workspace-browser/login-forgehub");
}

export function useWebAutomationRoutines(productId: string | undefined) {
  return useQuery<WebAutomationRoutine[]>({
    queryKey: ["workspace-browser", "routines", productId],
    queryFn: () => apiClient.get(`/api/v1/workspace-browser/routines?product_id=${productId}`),
    enabled: Boolean(productId),
  });
}

export function useCreateWebAutomationRoutine() {
  const queryClient = useQueryClient();
  return useMutation<WebAutomationRoutine, Error, { product_id: string; name: string; description?: string; steps: WebAutomationStep[] }>({
    mutationFn: (payload) => apiClient.post("/api/v1/workspace-browser/routines", payload),
    onSuccess: (routine) => queryClient.invalidateQueries({ queryKey: ["workspace-browser", "routines", routine.product_id] }),
  });
}

export function useUpdateWebAutomationRoutine() {
  const queryClient = useQueryClient();
  return useMutation<WebAutomationRoutine, Error, { id: string; product_id: string; name: string; description?: string; steps: WebAutomationStep[] }>({
    mutationFn: ({ id, product_id: _productId, ...payload }) => apiClient.put(`/api/v1/workspace-browser/routines/${id}`, payload),
    onSuccess: (routine) => queryClient.invalidateQueries({ queryKey: ["workspace-browser", "routines", routine.product_id] }),
  });
}

export function useDeleteWebAutomationRoutine() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { id: string; productId: string }>({
    mutationFn: ({ id }) => apiClient.delete(`/api/v1/workspace-browser/routines/${id}`),
    onSuccess: (_, variables) => queryClient.invalidateQueries({ queryKey: ["workspace-browser", "routines", variables.productId] }),
  });
}

export function useRunWebAutomationRoutine() {
  const queryClient = useQueryClient();
  return useMutation<WebAutomationRun, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/workspace-browser/routines/${id}:run`, {}),
    onSuccess: (result) => queryClient.setQueryData(browserKey, result.browser),
  });
}
