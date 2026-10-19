/** A machine's maintenance history (2026-10-19): every run that reached it --
 * by a person or an agent, why, for which client ticket/demand -- SSH sessions
 * opened on it and access events. One machine account (`darckware`), so this
 * is where "who did what" is read. Data: useMachineMaintenance. */
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Bot, History, KeyRound, Loader2, SquareTerminal, User, X } from "lucide-react";

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
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true" aria-labelledby="maintenance-title">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 my-auto w-full max-w-2xl rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id="maintenance-title" className="flex items-center gap-2 text-base font-semibold">
            <History className="h-4 w-4" aria-hidden="true" /> {t("maintenance.title", { name: machine.name })}
          </h2>
          <button type="button" onClick={onClose} aria-label={t("cancel")} className="cursor-pointer text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-4">
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
                      <span className="font-medium">{entry.title}</span>
                    )}
                    {entry.status && <VerdictBadge verdict={entry.status as ExecResultStatus} />}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {fmt.format(new Date(entry.at))} · {entry.agent_name ? t("maintenance.byAgent", { name: entry.agent_name }) : entry.actor}
                    {entry.darckware_item_id && ` · ${t(`maintenance.item.${entry.darckware_item_kind}`, { id: entry.darckware_item_id })}`}
                  </p>
                  {entry.reason && <p className="text-xs">{entry.reason}</p>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
