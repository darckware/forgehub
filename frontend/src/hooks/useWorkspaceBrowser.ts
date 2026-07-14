import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface WorkspaceBrowserPointerState {
  x: number;
  y: number;
  at: string;
}

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
  last_pointer: WorkspaceBrowserPointerState | null;
  control_owner: "user" | "agent" | null;
}

/** What Automations/Macro operate on -- a registered Product, or a
 * lightweight standalone app (name + URL, no Product onboarding). Exactly
 * one of product_id/standalone_app_id is set on every routine/macro row. */
export type AutomationTarget = { type: "product"; id: string } | { type: "app"; id: string };

function targetQuery(target: AutomationTarget): string {
  return target.type === "product" ? `product_id=${target.id}` : `standalone_app_id=${target.id}`;
}

function targetPayload(target: AutomationTarget): { product_id?: string; standalone_app_id?: string } {
  return target.type === "product" ? { product_id: target.id } : { standalone_app_id: target.id };
}

function targetKey(target: AutomationTarget | undefined): [string, string] | [undefined, undefined] {
  return target ? [target.type, target.id] : [undefined, undefined];
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
  product_id: string | null;
  standalone_app_id: string | null;
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

export interface StandaloneApp {
  id: string;
  name: string;
  url: string;
  created_at: string;
  updated_at: string;
}

export interface MacroInstructionSet {
  id: string;
  product_id: string | null;
  standalone_app_id: string | null;
  name: string;
  description?: string | null;
  lines: string[];
  created_at: string;
  updated_at: string;
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

export function useStandaloneApps() {
  return useQuery<StandaloneApp[]>({
    queryKey: ["workspace-browser", "standalone-apps"],
    queryFn: () => apiClient.get("/api/v1/workspace-browser/standalone-apps"),
  });
}

export function useCreateStandaloneApp() {
  const queryClient = useQueryClient();
  return useMutation<StandaloneApp, Error, { name: string; url: string }>({
    mutationFn: (payload) => apiClient.post("/api/v1/workspace-browser/standalone-apps", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspace-browser", "standalone-apps"] }),
  });
}

export function useDeleteStandaloneApp() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/workspace-browser/standalone-apps/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspace-browser", "standalone-apps"] }),
  });
}

export function useWebAutomationRoutines(target: AutomationTarget | undefined) {
  return useQuery<WebAutomationRoutine[]>({
    queryKey: ["workspace-browser", "routines", ...targetKey(target)],
    queryFn: () => apiClient.get(`/api/v1/workspace-browser/routines?${targetQuery(target!)}`),
    enabled: Boolean(target),
  });
}

export function useCreateWebAutomationRoutine() {
  const queryClient = useQueryClient();
  return useMutation<WebAutomationRoutine, Error, { target: AutomationTarget; name: string; description?: string; steps: WebAutomationStep[] }>({
    mutationFn: ({ target, ...payload }) => apiClient.post("/api/v1/workspace-browser/routines", { ...payload, ...targetPayload(target) }),
    onSuccess: (routine) => queryClient.invalidateQueries({
      queryKey: ["workspace-browser", "routines", ...targetKey(routine.product_id ? { type: "product", id: routine.product_id } : { type: "app", id: routine.standalone_app_id! })],
    }),
  });
}

export function useUpdateWebAutomationRoutine() {
  const queryClient = useQueryClient();
  return useMutation<WebAutomationRoutine, Error, { id: string; target: AutomationTarget; name: string; description?: string; steps: WebAutomationStep[] }>({
    mutationFn: ({ id, target: _target, ...payload }) => apiClient.put(`/api/v1/workspace-browser/routines/${id}`, payload),
    onSuccess: (routine) => queryClient.invalidateQueries({
      queryKey: ["workspace-browser", "routines", ...targetKey(routine.product_id ? { type: "product", id: routine.product_id } : { type: "app", id: routine.standalone_app_id! })],
    }),
  });
}

export function useDeleteWebAutomationRoutine() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { id: string; target: AutomationTarget }>({
    mutationFn: ({ id }) => apiClient.delete(`/api/v1/workspace-browser/routines/${id}`),
    onSuccess: (_, variables) => queryClient.invalidateQueries({ queryKey: ["workspace-browser", "routines", ...targetKey(variables.target)] }),
  });
}

export function useRunWebAutomationRoutine() {
  const queryClient = useQueryClient();
  return useMutation<WebAutomationRun, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/workspace-browser/routines/${id}:run`, {}),
    onSuccess: (result) => queryClient.setQueryData(browserKey, result.browser),
  });
}

export function useMacroInstructionSets(target: AutomationTarget | undefined) {
  return useQuery<MacroInstructionSet[]>({
    queryKey: ["workspace-browser", "macros", ...targetKey(target)],
    queryFn: () => apiClient.get(`/api/v1/workspace-browser/macros?${targetQuery(target!)}`),
    enabled: Boolean(target),
  });
}

export function useCreateMacroInstructionSet() {
  const queryClient = useQueryClient();
  return useMutation<MacroInstructionSet, Error, { target: AutomationTarget; name: string; description?: string; lines: string[] }>({
    mutationFn: ({ target, ...payload }) => apiClient.post("/api/v1/workspace-browser/macros", { ...payload, ...targetPayload(target) }),
    onSuccess: (macro) => queryClient.invalidateQueries({
      queryKey: ["workspace-browser", "macros", ...targetKey(macro.product_id ? { type: "product", id: macro.product_id } : { type: "app", id: macro.standalone_app_id! })],
    }),
  });
}

export function useUpdateMacroInstructionSet() {
  const queryClient = useQueryClient();
  return useMutation<MacroInstructionSet, Error, { id: string; target: AutomationTarget; name: string; description?: string; lines: string[] }>({
    mutationFn: ({ id, target: _target, ...payload }) => apiClient.put(`/api/v1/workspace-browser/macros/${id}`, payload),
    onSuccess: (macro) => queryClient.invalidateQueries({
      queryKey: ["workspace-browser", "macros", ...targetKey(macro.product_id ? { type: "product", id: macro.product_id } : { type: "app", id: macro.standalone_app_id! })],
    }),
  });
}

export function useDeleteMacroInstructionSet() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { id: string; target: AutomationTarget }>({
    mutationFn: ({ id }) => apiClient.delete(`/api/v1/workspace-browser/macros/${id}`),
    onSuccess: (_, variables) => queryClient.invalidateQueries({ queryKey: ["workspace-browser", "macros", ...targetKey(variables.target)] }),
  });
}
