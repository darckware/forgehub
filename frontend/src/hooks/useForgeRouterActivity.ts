import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

export const forgeRouterActivityEventSchema = z.object({
  request_id: z.string(),
  agent_name: z.string().nullable(),
  required_capability: z.string(),
  demand: z.string().nullable(),
  status: z.string(),
  created_at: z.string(),
  prompt_preview: z.string().nullable(),
  cost: z.number().nullable(),
});

export type ForgeRouterActivityEvent = z.infer<typeof forgeRouterActivityEventSchema>;

/** Recent `ai_router.route_events` (backend/app/core/forgerouter_sync.py) --
 * every LLM call ForgeRouter routed for an agent, regardless of whether it
 * was triggered by a ForgeHub Messages dispatch (a cron job, a live chat
 * session, an "aegis-reviewer" skill run all show up here too). This is
 * the only real signal for "is this agent actively calling an LLM right
 * now" between a Demand's dispatched/running/completed states -- see
 * useAgentActivityViewModel, which merges this into the board. Polls
 * fairly fast (4s) since route_events land multiple-per-second for a busy
 * agent and the board wants to feel live, not because anything here is
 * expensive to fetch (LIMIT-bounded, indexed by created_at). */
export function useForgeRouterActivity(sinceSeconds = 90) {
  return useQuery({
    queryKey: ["forgerouter-activity", sinceSeconds],
    queryFn: async () => {
      const data = await apiClient.get<unknown>("/api/v1/forgerouter/activity", {
        params: { since_seconds: sinceSeconds, limit: 150 },
      });
      return z.array(forgeRouterActivityEventSchema).parse(data);
    },
    refetchInterval: 4_000,
    refetchIntervalInBackground: true,
    // Recent-window telemetry from an infra DB, not app state -- a missed
    // poll here isn't worth surfacing as a page-level error.
    retry: 1,
  });
}
