/** A machine's maintenance history (2026-10-19): every run that reached it --
 * by a person or an agent, why, for which client ticket/demand -- SSH sessions
 * opened on it and access events. One machine account (`darckware`), so this
 * is where "who did what" is read. A read-only right-hand panel
 * (2026-11-11). Data: useMachineMaintenance. */
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Bot, History, KeyRound, Loader2, SquareTerminal, User } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { SidePanel } from "@/components/ui/side-panel";
import type { ExecResultStatus } from "@/hooks/useHostExecutions";
import { useMachineMaintenance, type MaintenanceEntry } from "@/hooks/useHostInventory";
import type { Server } from "@/hooks/useServers";
import { VerdictBadge } from "./VerdictBadge";

function EntryIcon({ entry }: { entry: MaintenanceEntry }) {
  const cls = "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground";
  if (entry.kind === "terminal") return <SquareTerminal className={cls} aria-hidden="true" />;
  if (entry.kind === "event") return <KeyRound className={cls} aria-hidden="true" />;
  return entry.agent_name ? <Bot className={cls} aria-hidden="true" /> : <User className={cls} aria-hidden="true" />;
}

export function MaintenanceDialog({ machine, onClose }: { machine: Server; onClose: () => void }) {
  const { t, i18n } = useTranslation("remoteAccess");
  const history = useMachineMaintenance(machine.id);
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });

  return (
    <SidePanel
      onClose={onClose}
      size="2xl"
      titleId="maintenance-title"
      icon={<History className="h-4 w-4" aria-hidden="true" />}
      title={t("maintenance.title", { name: machine.name })}
      closeLabel={t("cancel")}
      bodyClassName="space-y-0"
    >
      <p className="mb-3 text-xs text-muted-foreground">{t("maintenance.help")}</p>
      {history.isLoading && <Loader2 className="mx-auto h-5 w-5 motion-safe:animate-spin" aria-label={t("maintenance.loading")} />}
      {history.isError && <p role="alert" className="text-sm text-destructive">{t("maintenance.loadError")}</p>}
      {history.data?.length === 0 && <p className="text-sm text-muted-foreground">{t("maintenance.empty")}</p>}
      <ol className="divide-y divide-border">
        {history.data?.map((entry, i) => (
          <li key={`${entry.at}-${i}`} className="flex gap-3 py-2.5 text-sm">
            <EntryIcon entry={entry} />
            <div className="min-w-0 flex-1 space-y-0.5">
              <div className="flex flex-wrap items-center gap-2">
                {entry.execution_id ? (
                  <Link to={`/remote-access/executions/${entry.execution_id}`} className="font-medium hover:underline">{entry.title}</Link>
                ) : (
                  <span className="font-medium">{entry.transfer_direction ? t(`maintenance.transfer.${entry.transfer_direction}`) : entry.title}</span>
                )}
                {entry.status && <VerdictBadge verdict={entry.status as ExecResultStatus} />}
                {entry.direct_access_id && (
                  <Badge variant="secondary">
                    {t("direct.historyBadge", { purpose: t(`direct.purposes.${entry.direct_access_purpose ?? "support"}`) })}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {fmt.format(new Date(entry.at))} · {entry.agent_name ? t("maintenance.byAgent", { name: entry.agent_name }) : entry.actor}
                {entry.darckware_item_id && ` · ${t(`maintenance.item.${entry.darckware_item_kind}`, { id: entry.darckware_item_id })}`}
                {entry.message_number && <> · <Link to="/demands" className="underline">{t("askAgent.message", { number: entry.message_number })}</Link></>}
              </p>
              {entry.reason && <p className="text-xs">{entry.reason}</p>}
              {entry.output_expired && <p className="text-xs text-muted-foreground">{t("execution.outputExpired")}</p>}
              {entry.transfer_direction && <div className="space-y-1 break-all text-xs text-muted-foreground">
                <p><code>{entry.transfer_local_path}</code> {entry.transfer_direction === "upload" ? "→" : "←"} <code>{entry.transfer_remote_path}</code></p>
                {entry.transfer_size != null && <p>{entry.transfer_size.toLocaleString(i18n.language)} B</p>}
                {entry.transfer_sha256 && <p>SHA-256: {entry.transfer_sha256}</p>}
                {entry.transfer_overwrite && <p>{t("maintenance.transfer.overwrite")}</p>}
              </div>}
            </div>
          </li>
        ))}
      </ol>
    </SidePanel>
  );
}
