/** Customer-service rules of the agents that talk to people outside the ecosystem (2026-11-14,
 * Marcelo): one document per agent + channel, stored in ForgeHub and mirrored by the backend into
 * the agent's profile file `ATENDIMENTO_<CANAL>.md`. `file_state` says whether that file still
 * matches what ForgeHub holds. API: `/api/v1/personal/service-rules`. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

const BASE = "/api/v1/personal/service-rules";

export const SERVICE_RULE_AGENTS = ["lara", "maia"] as const;
export const SERVICE_RULE_CHANNELS = ["whatsapp", "site", "email"] as const;
export const SERVICE_RULE_FILE_STATES = ["in_sync", "missing", "differs", "unknown"] as const;

export const serviceRuleSchema = z.object({
  agent: z.enum(SERVICE_RULE_AGENTS),
  channel: z.enum(SERVICE_RULE_CHANNELS),
  file_name: z.string(),
  file_path: z.string(),
  content: z.string(),
  content_hash: z.string().nullable(),
  chars: z.number(),
  max_chars: z.number(),
  updated_at: z.string().nullable(),
  updated_by: z.string().nullable(),
  file_state: z.enum(SERVICE_RULE_FILE_STATES),
});
export type ServiceRule = z.infer<typeof serviceRuleSchema>;
export type ServiceRuleAgent = ServiceRule["agent"];
export type ServiceRuleChannel = ServiceRule["channel"];
export type ServiceRuleFileState = ServiceRule["file_state"];

export const serviceRuleHistoryEntrySchema = z.object({
  at: z.string(),
  actor: z.string(),
  content_hash: z.string(),
  previous_hash: z.string().nullable(),
  chars: z.number(),
});
export type ServiceRuleHistoryEntry = z.infer<typeof serviceRuleHistoryEntrySchema>;

/** A pair's stable key, e.g. "lara:whatsapp". */
export function serviceRuleKey(rule: Pick<ServiceRule, "agent" | "channel">): string {
  return `${rule.agent}:${rule.channel}`;
}

export const serviceRulesKey = ["personal", "service-rules"] as const;
export const serviceRuleHistoryKey = (agent: string, channel: string) =>
  [...serviceRulesKey, "history", agent, channel] as const;

export function useServiceRules() {
  return useQuery({
    queryKey: serviceRulesKey,
    queryFn: async () => z.array(serviceRuleSchema).parse(await apiClient.get(BASE)),
  });
}

export function useServiceRuleHistory(agent: string | undefined, channel: string | undefined, enabled = true) {
  return useQuery({
    queryKey: serviceRuleHistoryKey(agent ?? "", channel ?? ""),
    enabled: Boolean(agent && channel) && enabled,
    queryFn: async () =>
      z.array(serviceRuleHistoryEntrySchema).parse(await apiClient.get(`${BASE}/${agent}/${channel}/history`)),
  });
}

export interface SaveServiceRuleInput {
  agent: ServiceRuleAgent;
  channel: ServiceRuleChannel;
  content: string;
  expected_hash: string | null;
}

export function useSaveServiceRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ agent, channel, content, expected_hash }: SaveServiceRuleInput) =>
      serviceRuleSchema.parse(await apiClient.put(`${BASE}/${agent}/${channel}`, { content, expected_hash })),
    // Put the saved item in the list right away, so the editor never flashes the old text while
    // the list refetches.
    onSuccess: (saved) => {
      qc.setQueryData<ServiceRule[]>(serviceRulesKey, (list) =>
        list?.map((rule) => (serviceRuleKey(rule) === serviceRuleKey(saved) ? saved : rule)),
      );
    },
    onSettled: (_data, _error, vars) => {
      void qc.invalidateQueries({ queryKey: serviceRulesKey, exact: true });
      void qc.invalidateQueries({ queryKey: serviceRuleHistoryKey(vars.agent, vars.channel) });
    },
  });
}
