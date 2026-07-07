import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Source SKILL.md of a registered skill, resolved by the backend across
 * every profile's skills/ tree (backend/app/api/routes/foundation.py
 * get_skill_content). `path` is the host-side path, for display.
 */

const skillContentSchema = z.object({
  name: z.string(),
  profile: z.string(),
  path: z.string(),
  content: z.string(),
});

export type SkillContent = z.infer<typeof skillContentSchema>;

export function useSkillFileContent(name: string | null) {
  return useQuery({
    queryKey: ["skill-file-content", name],
    queryFn: async () => {
      const data = await apiClient.get<unknown>(
        `/api/v1/foundation/skills/${encodeURIComponent(name ?? "")}/content`
      );
      return skillContentSchema.parse(data);
    },
    enabled: Boolean(name),
  });
}

/** Overwrite the skill's SKILL.md on disk. The DB skill row keeps its
 * synced metadata until the next Hermes Foundation sync re-imports the
 * frontmatter. */
export function useUpdateSkillFileContent(name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (content: string) => {
      const data = await apiClient.put<unknown>(
        `/api/v1/foundation/skills/${encodeURIComponent(name)}/content`,
        { content }
      );
      return skillContentSchema.parse(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["skill-file-content", name] });
    },
  });
}
