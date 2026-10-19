/** One machine's color and label (backend `classify_status`), shared by the
 * Machines table and the execution composer so both read the same way. */
import type { HostReadinessEntry, HostStatus } from "@/hooks/useHostInventory";

export const STATUS_DOT: Record<HostStatus, string> = {
  complete: "bg-emerald-500",
  partial: "bg-amber-500",
  not_prepared: "bg-orange-600",
  offline: "bg-muted-foreground/40",
  disabled: "bg-muted-foreground/40",
  unknown: "border border-dashed border-muted-foreground bg-transparent",
};

export const STATUS_BADGE: Record<HostStatus, string> = {
  complete: "border-transparent bg-emerald-100 text-emerald-800",
  partial: "border-transparent bg-amber-100 text-amber-800",
  not_prepared: "border-transparent bg-orange-100 text-orange-800",
  offline: "border-border text-foreground",
  disabled: "border-border text-muted-foreground",
  unknown: "border-dashed border-border text-muted-foreground",
};

export const hasSsh = (entry: HostReadinessEntry | undefined) =>
  entry?.readiness === "ready" || entry?.readiness === "busy";

/** i18n key under `status.`: "partial" names the missing channel. */
export function statusKey(entry: HostReadinessEntry | undefined): string {
  const status = entry?.status ?? "unknown";
  if (status !== "partial") return status;
  return hasSsh(entry) ? "partial_no_rustdesk" : "partial_no_ssh";
}
