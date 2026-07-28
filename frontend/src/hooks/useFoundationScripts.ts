import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Hermes scripts registry (backend/app/api/routes/cron_scripts.py).
 * DB-backed catalog: POST /api/v1/scripts/sync populates from the
 * mounted script dirs; GET /api/v1/scripts returns only the scripts
 * cron jobs actually reference (with live cross-references computed at
 * query time) -- the full per-profile catalog is the Agent Tools page.
 */

export const cronJobRefSchema = z.object({
  job_id: z.string(),
  job_name: z.string(),
  profile: z.string(),
  schedule_display: z.string().nullable(),
  enabled: z.boolean(),
  last_status: z.string().nullable(),
  last_run_at: z.string().nullable(),
  last_error: z.string().nullable(),
});

export type CronJobRef = z.infer<typeof cronJobRefSchema>;

export const scriptSchema = z.object({
  id: z.string(),
  name: z.string(),
  location: z.string(),
  agent: z.string().nullable(),
  category: z.string().nullable(),
  description: z.string().nullable(),
  path: z.string(),
  executable: z.boolean(),
  active: z.boolean(),
  exists_on_disk: z.boolean(),
  is_symlink: z.boolean(),
  symlink_target: z.string().nullable(),
  escapes_scripts_dir: z.boolean(),
  status: z.enum(["ok", "broken", "unused"]),
  referenced_by: z.array(cronJobRefSchema),
});

export type Script = z.infer<typeof scriptSchema>;

const scriptListSchema = z.object({ scripts: z.array(scriptSchema) });

export const scriptKeys = {
  list: ["scripts"] as const,
};

export function useFoundationScripts() {
  return useQuery({
    queryKey: scriptKeys.list,
    queryFn: async () => {
      const data = await apiClient.get<unknown>("/api/v1/scripts");
      return scriptListSchema.parse(data).scripts;
    },
  });
}

/**
 * The *full* per-profile script catalog, straight off the filesystem
 * (`/api/v1/foundation/scripts`) — not the DB-backed `/api/v1/scripts` above,
 * which deliberately returns only scripts a cron job references. The Agents
 * overview needs everything a profile owns, including scripts no cron calls.
 *
 * The response shape is the same `scriptSchema` minus the DB row's `id`, and
 * with `exists` rather than `exists_on_disk`; normalised here so consumers see
 * one `Script` type.
 */
const foundationScriptSchema = scriptSchema
  .omit({ id: true, exists_on_disk: true, active: true, category: true, referenced_by: true })
  .extend({
    exists: z.boolean(),
    description: z.string().nullable().default(null),
    // foundation.py's CronJobRefOut carries no last_run_at, unlike the
    // DB-backed /api/v1/scripts ref above — reusing cronJobRefSchema here
    // would reject every script a cron job actually references.
    referenced_by: z
      .array(cronJobRefSchema.omit({ last_run_at: true }))
      .default([]),
  });

export type FoundationScript = z.infer<typeof foundationScriptSchema>;

const foundationScriptListSchema = z.object({ scripts: z.array(foundationScriptSchema) });

export const foundationScriptKeys = {
  list: ["foundation-scripts"] as const,
};

export function useFoundationAllScripts() {
  return useQuery({
    queryKey: foundationScriptKeys.list,
    queryFn: async () => {
      const data = await apiClient.get<unknown>("/api/v1/foundation/scripts");
      return foundationScriptListSchema.parse(data).scripts;
    },
  });
}

export function useSyncScripts() {
  return { sync: () => apiClient.post<unknown>("/api/v1/scripts/sync", {}) };
}

export interface ScriptLocationRef {
  location: string;
  name: string;
}

const scriptContentSchema = z.object({ content: z.string(), path: z.string() });
export type ScriptContent = z.infer<typeof scriptContentSchema>;

async function fetchScriptContent(ref: ScriptLocationRef): Promise<ScriptContent> {
  const data = await apiClient.get<unknown>(
    `/api/v1/foundation/scripts/${encodeURIComponent(ref.location)}/${encodeURIComponent(ref.name)}/content`
  );
  return scriptContentSchema.parse(data);
}

/**
 * A cron job's `script` filename can exist under the job's own profile
 * scripts/ dir, the central catalog, or neither (broken job) -- try each
 * candidate location in order and return the first readable hit.
 */
export async function fetchScriptContentWithFallback(
  candidates: ScriptLocationRef[]
): Promise<ScriptContent | null> {
  for (const candidate of candidates) {
    try {
      return await fetchScriptContent(candidate);
    } catch {
      // try the next candidate location
    }
  }
  return null;
}

export function useScriptFileContent(candidates: ScriptLocationRef[], enabled: boolean) {
  return useQuery({
    queryKey: ["foundation-script-content", candidates],
    queryFn: async () => {
      const result = await fetchScriptContentWithFallback(candidates);
      if (!result) throw new Error("Script file not found or unreadable");
      return result;
    },
    enabled,
  });
}
