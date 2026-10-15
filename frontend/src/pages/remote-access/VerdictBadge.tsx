import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { ExecResultStatus, ExecVerdict } from "@/hooks/useHostExecutions";

const VARIANT = {
  running: "secondary",
  pending: "outline",
  succeeded: "success",
  failed: "destructive",
  skipped: "outline",
  nothing_ran: "outline",
} as const;

/** One badge for both an execution's verdict and a machine's result status. */
export function VerdictBadge({ verdict }: { verdict: ExecVerdict | ExecResultStatus }) {
  const { t } = useTranslation("remoteAccess");
  return (
    <Badge variant={VARIANT[verdict]} className="gap-1 whitespace-nowrap">
      {verdict === "running" && <Loader2 className="h-3 w-3 motion-safe:animate-spin" aria-hidden="true" />}
      {t(`verdict.${verdict}`)}
    </Badge>
  );
}
