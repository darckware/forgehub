import { ArrowUpRight, Bot, HeartPulse } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import type { ActivityAgent } from "@/hooks/useAgentActivity";

interface AgentInspectorProps {
  agent: ActivityAgent | null;
  onOpenRecord: (canonicalPath: string) => void;
}

function RecordButton({ path, label, onOpen }: { path: string; label: string; onOpen: (path: string) => void }) {
  const handleClick = (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (
      event.defaultPrevented
      || event.button !== 0
      || event.metaKey
      || event.ctrlKey
      || event.shiftKey
      || event.altKey
    ) return;
    event.preventDefault();
    onOpen(path);
  };

  return (
    <a
      href={path}
      onClick={handleClick}
      className="inline-flex cursor-pointer items-center gap-1 rounded-sm font-mono text-[10px] text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {label}
      <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
    </a>
  );
}

export function AgentInspector({ agent, onOpenRecord }: AgentInspectorProps) {
  const { t } = useTranslation("agentActivity");

  return (
    <section aria-labelledby="agent-inspector-title" className="min-h-[19rem] overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex min-h-11 items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-muted">
            <Bot className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 id="agent-inspector-title" className="truncate text-xs font-medium">
              {agent?.name ?? t("inspector.title")}
            </h2>
            <p className="truncate font-mono text-[9px] text-muted-foreground">
              {agent ? `${agent.runtime_type} / ${agent.profile_slug ?? t("inspector.noProfile")}` : t("inspector.selectAgent")}
            </p>
          </div>
        </div>
        {agent && (
          <Badge variant="outline" className="shrink-0 gap-1 text-[9px]">
            <HeartPulse className="h-3 w-3" aria-hidden="true" />
            {t(`availability.${agent.availability}`)}
          </Badge>
        )}
      </div>

      {!agent ? (
        <p className="px-3 py-8 text-center text-xs text-muted-foreground">{t("inspector.selectAgent")}</p>
      ) : (
        <dl className="divide-y divide-border text-[11px]">
          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.runtimeHealth")}</dt>
            <dd>
              <span className="font-medium">{t(`profileStatus.${agent.profile_summary.status}`)}</span>
              {agent.profile_summary.issues.map((issue) => (
                <span key={issue} className="mt-0.5 block text-destructive">{issue}</span>
              ))}
            </dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.currentAction")}</dt>
            <dd>{agent.current_work?.action ?? t("inspector.noActiveWork")}</dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.project")}</dt>
            <dd className="min-w-0">
              {agent.current_work?.project_path && agent.current_work.project_name ? (
                <RecordButton
                  path={agent.current_work.project_path}
                  label={agent.current_work.project_name}
                  onOpen={onOpenRecord}
                />
              ) : (
                t("inspector.notRecorded")
              )}
            </dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.execution")}</dt>
            <dd className="min-w-0 break-all">
              {agent.current_work?.execution_path && agent.current_work.execution_id ? (
                <RecordButton
                  path={agent.current_work.execution_path}
                  label={agent.current_work.execution_id}
                  onOpen={onOpenRecord}
                />
              ) : (
                t("inspector.notRecorded")
              )}
            </dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.branch")}</dt>
            <dd className="break-all font-mono">{agent.current_work?.branch ?? t("inspector.notRecorded")}</dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.workingDirectory")}</dt>
            <dd className="break-all font-mono">{agent.current_work?.working_directory_path ?? t("inspector.notRecorded")}</dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.sourceTask")}</dt>
            <dd className="min-w-0">
              {agent.current_work?.task_path && agent.current_work.task_title ? (
                <RecordButton path={agent.current_work.task_path} label={agent.current_work.task_title} onOpen={onOpenRecord} />
              ) : (
                t("inspector.notRecorded")
              )}
              {agent.current_work?.source_message_path && (
                <span className="mt-1 block">
                  <RecordButton path={agent.current_work.source_message_path} label={t("inspector.sourceMessage")} onOpen={onOpenRecord} />
                </span>
              )}
            </dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.waits")}</dt>
            <dd className="text-amber-700 dark:text-amber-400">
              {agent.availability_reason ?? t("inspector.noWaits")}
            </dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.checkpoint")}</dt>
            <dd>
              {agent.latest_checkpoint ? (
                <>
                  <RecordButton
                    path={agent.latest_checkpoint.canonical_path}
                    label={agent.latest_checkpoint.summary ?? agent.latest_checkpoint.id}
                    onOpen={onOpenRecord}
                  />
                  {agent.latest_checkpoint.verification_summary && (
                    <span className="mt-0.5 block text-muted-foreground">{agent.latest_checkpoint.verification_summary}</span>
                  )}
                </>
              ) : (
                t("inspector.notRecorded")
              )}
            </dd>
          </div>

          <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 px-3 py-2">
            <dt className="text-muted-foreground">{t("inspector.resumeFrom")}</dt>
            <dd className="font-mono">{agent.latest_checkpoint?.resume_from_step_key ?? t("inspector.notRecorded")}</dd>
          </div>

          {agent.latest_checkpoint?.error_code && (
            <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 bg-destructive/5 px-3 py-2">
              <dt className="text-muted-foreground">{t("inspector.error")}</dt>
              <dd className="font-mono text-destructive">{agent.latest_checkpoint.error_code}</dd>
            </div>
          )}

          {(agent.latest_checkpoint?.evidence_summary || agent.latest_checkpoint?.blocker_code) && (
            <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 bg-amber-500/5 px-3 py-2">
              <dt className="text-muted-foreground">{t("inspector.authorization")}</dt>
              <dd>
                <span className="font-medium text-amber-700 dark:text-amber-400">
                  {agent.latest_checkpoint.evidence_summary ?? t("inspector.pendingAuthorization")}
                </span>
                {agent.latest_checkpoint.blocker_code && (
                  <span className="mt-0.5 block font-mono text-muted-foreground">{agent.latest_checkpoint.blocker_code}</span>
                )}
              </dd>
            </div>
          )}
        </dl>
      )}
    </section>
  );
}
