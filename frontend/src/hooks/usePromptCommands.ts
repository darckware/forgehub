import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

export const promptCommandSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  prompt: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type PromptCommand = z.infer<typeof promptCommandSchema>;

export type PromptCommandInput = {
  name: string;
  description: string;
  prompt: string;
};

export const RESERVED_PROMPT_COMMAND_NAMES = ["model", "status", "help", "version", "title", "profile"];

const promptCommandListSchema = z.array(promptCommandSchema);

export const promptCommandKeys = {
  all: ["prompt-commands"] as const,
};

export function normalizePromptCommandName(name: string): string {
  return name
    .trim()
    .replace(/^\/+/, "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
}

export function usePromptCommands() {
  return useQuery({
    queryKey: promptCommandKeys.all,
    queryFn: async () => {
      const data = await apiClient.get<unknown>("/api/v1/prompt-commands");
      return promptCommandListSchema.parse(data);
    },
    staleTime: 30_000,
  });
}

export function useCreatePromptCommand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PromptCommandInput) =>
      apiClient.post<unknown>("/api/v1/prompt-commands", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: promptCommandKeys.all }),
  });
}

export function useUpdatePromptCommand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: PromptCommandInput }) =>
      apiClient.put<unknown>(`/api/v1/prompt-commands/${id}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: promptCommandKeys.all }),
  });
}

export function useDeletePromptCommand() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<unknown>(`/api/v1/prompt-commands/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: promptCommandKeys.all }),
  });
}
