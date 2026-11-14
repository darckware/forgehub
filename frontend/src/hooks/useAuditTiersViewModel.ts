import { useState } from "react";
import {
  useAuditStatus,
  useRunAuditRoutineNow,
  type AuditFrequency,
  type AuditTier,
} from "@/hooks/useAudit";

/**
 * Auditor frequency tiers (2026-11-13): each tier is one Operação 24x7 audit
 * routine that runs the tier's enabled checks as one Auditor batch. This
 * ViewModel (§21) feeds `AuditTiersPanel`: the tiers from /audit/status and a
 * "run this tier now" action. That action is the tier routine's run-now: the
 * batch starts in the background (and waits its turn behind any other batch),
 * so a long tier never times out an HTTP request.
 *
 * `status`: "loading" until the first status read, "error" when it failed,
 * "ready" otherwise; `runningTier` is the tier whose request is in flight and
 * `startedTier` the last one whose batch was started.
 */
export interface AuditTiersViewModel {
  status: "loading" | "ready" | "error";
  tiers: AuditTier[];
  scheduleSource: "routines" | "hermes_cron";
  runningTier: AuditFrequency | null;
  startedTier: AuditFrequency | null;
  runError: string | null;
  runTier: (tier: AuditTier) => void;
}

export function useAuditTiersViewModel(): AuditTiersViewModel {
  const statusQuery = useAuditStatus();
  const runNow = useRunAuditRoutineNow();
  const [runningTier, setRunningTier] = useState<AuditFrequency | null>(null);
  const [startedTier, setStartedTier] = useState<AuditFrequency | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  function runTier(tier: AuditTier) {
    if (!tier.routine_id) return;
    setRunError(null);
    setStartedTier(null);
    setRunningTier(tier.frequency);
    runNow.mutate(tier.routine_id, {
      onSuccess: () => setStartedTier(tier.frequency),
      onError: (error) => setRunError(error instanceof Error ? error.message : String(error)),
      onSettled: () => setRunningTier(null),
    });
  }

  return {
    status: statusQuery.isError ? "error" : statusQuery.data ? "ready" : "loading",
    tiers: statusQuery.data?.tiers ?? [],
    scheduleSource: statusQuery.data?.schedule_source ?? "hermes_cron",
    runningTier,
    startedTier,
    runError,
    runTier,
  };
}
