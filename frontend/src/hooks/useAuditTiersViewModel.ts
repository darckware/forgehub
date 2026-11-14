import { useState } from "react";
import {
  useAuditStatus,
  useRunAllAuditChecks,
  type AuditFrequency,
  type AuditTier,
} from "@/hooks/useAudit";

/**
 * Auditor frequency tiers (2026-11-13): each tier is one Operação 24x7 audit
 * routine that runs the tier's enabled checks as one Auditor batch. This
 * ViewModel (§21) feeds `AuditTiersPanel`: the tiers from /audit/status and a
 * "run this tier now" action, tracked per tier so only the clicked card spins.
 *
 * `status`: "loading" until the first status read, "error" when it failed,
 * "ready" otherwise; `runningTier` is the tier whose manual batch is in flight.
 */
export interface AuditTiersViewModel {
  status: "loading" | "ready" | "error";
  tiers: AuditTier[];
  scheduleSource: "routines" | "hermes_cron";
  runningTier: AuditFrequency | null;
  runError: string | null;
  runTier: (frequency: AuditFrequency) => void;
}

export function useAuditTiersViewModel(): AuditTiersViewModel {
  const statusQuery = useAuditStatus();
  const runAll = useRunAllAuditChecks();
  const [runningTier, setRunningTier] = useState<AuditFrequency | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  function runTier(frequency: AuditFrequency) {
    setRunError(null);
    setRunningTier(frequency);
    runAll.mutate(frequency, {
      onError: (error) => setRunError(error instanceof Error ? error.message : String(error)),
      onSettled: () => setRunningTier(null),
    });
  }

  return {
    status: statusQuery.isError ? "error" : statusQuery.data ? "ready" : "loading",
    tiers: statusQuery.data?.tiers ?? [],
    scheduleSource: statusQuery.data?.schedule_source ?? "hermes_cron",
    runningTier,
    runError,
    runTier,
  };
}
