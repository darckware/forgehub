import { useMutation, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

export const PROMPT_TECHNIQUE_CATEGORIES = [
  "text", "structure", "reasoning", "software", "agentic", "research", "content", "marketing", "social_media", "soft_skills", "agent_skills", "design", "automation", "image", "video",
] as const;

const promptTechniqueSchema = z.object({
  id: z.string().uuid(),
  code: z.string(),
  category: z.enum(PROMPT_TECHNIQUE_CATEGORIES),
  name: z.string(),
  summary: z.string(),
  when_to_use: z.string(),
  when_to_avoid: z.string().nullable(),
  requirements: z.array(z.string()),
  compatible_with: z.array(z.string()),
  conflicts_with: z.array(z.string()),
  example: z.string().nullable(),
  effort: z.enum(["low", "medium", "high", "very_high"]),
  selection_mode: z.enum(["primary", "addon", "both"]),
  template_version: z.number().int(),
  sort_order: z.number().int(),
  is_builtin: z.boolean(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type PromptTechnique = z.infer<typeof promptTechniqueSchema>;

export const promptTechniqueKeys = { all: ["prompt-techniques"] as const };

export function usePromptTechniques() {
  return useQuery({
    queryKey: promptTechniqueKeys.all,
    queryFn: async () => {
      const data = await apiClient.get<unknown>("/api/v1/prompt-techniques");
      return z.array(promptTechniqueSchema).parse(data);
    },
    staleTime: 5 * 60_000,
  });
}

const recommendationSchema = z.object({
  technique_code: z.string(),
  score: z.number().int(),
  matched_terms: z.array(z.string()),
});

export function useRecommendPromptTechnique() {
  return useMutation({
    mutationFn: async (draft: string) => {
      const data = await apiClient.post<unknown>("/api/v1/prompt-techniques/recommend", { draft });
      return z.array(recommendationSchema).parse(data);
    },
  });
}
