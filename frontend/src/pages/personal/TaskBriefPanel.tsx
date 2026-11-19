import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Loader2, Sparkles, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { TaskBrief, WorkAction } from "@/hooks/useAgentTasksViewModel";
import type { AgentWorkItem } from "@/hooks/useDemands";

type Props = {
  brief: { data?: TaskBrief; isLoading: boolean; isError: boolean; refetch: () => unknown };
  onClose: () => void;
  onAction: (item: AgentWorkItem, action: WorkAction) => void;
};

/**
 * "Analisar" (2026-11-19, Marcelo: "preciso ter referencia do que vou fazer"): what the task is,
 * why it is stuck, what already happened and what each option does. Rule-based on the server,
 * so it answers even when the model provider is down.
 */
export function TaskBriefPanel({ brief, onClose, onAction }: Props) {
  const { t, i18n } = useTranslation("personal");
  const panel = useRef<HTMLElement>(null);
  const data = brief.data;
  useEffect(() => { panel.current?.scrollIntoView?.({ block: "start", behavior: "smooth" }); }, [data?.id]);
  const date = (value: string | null | undefined) => value ? new Date(value).toLocaleString(i18n.language) : "—";
  const ref = (row: { id: string; number: number; subject: string }) =>
    <Link className="text-primary underline" to={`/demands?message=${row.id}`}>#{row.number} · {row.subject}</Link>;
  const actionLabel = (action: string) => t(`agentTasks.actions.${action}`, { defaultValue: action });

  return <section ref={panel} aria-label={t("agentTasks.brief.title")} className="space-y-4 rounded-md border border-primary/40 bg-card p-4">
    <div className="flex items-start justify-between gap-2">
      <h3 className="flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4 shrink-0" />
        {data ? <span className="break-words">{t("agentTasks.brief.title")} · #{data.number} {data.about.subject}</span> : t("agentTasks.brief.title")}</h3>
      <Button size="icon" variant="ghost" aria-label={t("agentTasks.brief.close")} onClick={onClose}><X className="h-4 w-4" /></Button>
    </div>
    {brief.isLoading ? <p role="status" className="flex items-center gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" />{t("agentTasks.loading")}</p>
      : brief.isError || !data ? <div role="alert" className="space-y-2 text-sm"><p>{t("agentTasks.brief.error")}</p>
          <Button size="sm" variant="outline" onClick={() => void brief.refetch()}>{t("agentTasks.retryLoad")}</Button></div>
      : <>
        <div className="space-y-1 text-sm">
          <h4 className="font-medium">1. {t("agentTasks.brief.about")}</h4>
          <p className="text-muted-foreground">{[data.about.requested_by && t("agentTasks.brief.requestedBy", { name: data.about.requested_by }),
            data.about.executor && t("agentTasks.brief.executor", { name: data.about.executor }), data.about.context, date(data.about.created_at)].filter(Boolean).join(" · ")}</p>
          {data.about.working_path && <p className="break-all font-mono text-xs text-muted-foreground">{data.about.working_path}</p>}
          <p className="whitespace-pre-wrap break-words rounded bg-muted/50 p-2">{data.about.summary || "—"}</p>
        </div>

        <div className="space-y-1 text-sm">
          <h4 className="font-medium">2. {t("agentTasks.brief.why")}</h4>
          {data.stuck ? <>
            <p><Badge variant="warning">{t(`agentTasks.stuck.${data.stuck.reason}`)}</Badge>
              {data.stuck.since && <span className="ml-2 text-muted-foreground">{t("agentTasks.brief.since", { date: date(data.stuck.since) })}</span>}</p>
            <p>{t(`agentTasks.brief.reasons.${data.stuck.reason}`, { held: data.stuck.held ?? 0 })}</p>
            {data.stuck.detail && <p className="text-muted-foreground">{data.stuck.detail}</p>}
            {data.stuck.blocker && <p className="text-muted-foreground">{t(`agentTasks.blocked.${data.stuck.blocker}`)}</p>}
            {data.held_by && <p>{t("agentTasks.brief.heldBy")} {ref(data.held_by)}</p>}
          </> : <p className="text-muted-foreground">{t("agentTasks.brief.notStuck")}</p>}
        </div>

        <div className="space-y-1 text-sm">
          <h4 className="font-medium">3. {t("agentTasks.brief.happened")}</h4>
          <p>{t("agentTasks.brief.attempts", { count: data.history.attempts, limit: data.history.retry_limit })}</p>
          {data.history.last_error && <p className="break-words text-destructive">{data.history.last_error}</p>}
          {data.history.checks.length > 0 && <ul className="space-y-1">{data.history.checks.map(check => <li key={check.id}>
            {t("agentTasks.brief.check")} {ref(check)}{check.verdict && <Badge className="ml-2" variant={check.verdict === "completed" ? "outline" : "warning"}>{t(`agentTasks.brief.verdict.${check.verdict}`)}</Badge>}</li>)}</ul>}
          {data.history.replies.length > 0 && <ul className="space-y-1">{data.history.replies.map(row => <li key={row.id}>{t("agentTasks.brief.reply")} {ref(row)}</li>)}</ul>}
          {data.history.mentioned_by.length > 0 && <div><p>{t("agentTasks.brief.mentionedBy")}</p>
            <ul className="space-y-1">{data.history.mentioned_by.map(row => <li key={row.id}>{ref(row)} <span className="text-muted-foreground">({t(`agentTasks.brief.dispatch.${row.dispatch_status ?? "none"}`, { defaultValue: row.dispatch_status ?? "" })})</span></li>)}</ul></div>}
          {data.history.consolidated_into && <p>{t("agentTasks.brief.consolidated")} {ref(data.history.consolidated_into)}</p>}
          {data.history.last_result && <details><summary className="cursor-pointer">{t("agentTasks.result")}</summary>
            <p className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">{data.history.last_result}</p></details>}
        </div>

        <div className="space-y-1 text-sm">
          <h4 className="font-medium">4. {t("agentTasks.brief.elsewhere")}</h4>
          <p className="text-muted-foreground">{t("agentTasks.brief.elsewhereLater")}</p>
        </div>

        <div className="space-y-2 text-sm">
          <h4 className="font-medium">5. {t("agentTasks.brief.todo")}</h4>
          {data.options.length === 0 && <p className="text-muted-foreground">{t("agentTasks.brief.noOptions")}</p>}
          <ul className="space-y-2">{data.options.map(option => <li key={option.action} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
            <Button size="sm" className="max-md:h-auto max-md:min-h-9 max-md:py-2 max-md:whitespace-normal sm:w-56 sm:justify-start" variant={option.recommended ? "default" : "outline"}
              onClick={() => onAction(data.item, option.action as WorkAction)}>
              {option.recommended && "★ "}{actionLabel(option.action)}</Button>
            <span className="text-muted-foreground">{option.recommended && <span className="font-medium text-foreground">{t("agentTasks.brief.recommended")} </span>}
              {t(`agentTasks.brief.consequence.${option.action}`, { defaultValue: "" })}</span>
          </li>)}</ul>
          {Object.keys(data.blocked).length > 0 && <details><summary className="cursor-pointer text-muted-foreground">{t("agentTasks.brief.unavailable")}</summary>
            <ul className="mt-1 space-y-1 text-muted-foreground">{Object.entries(data.blocked).filter(([action]) => action !== "restore").map(([action, reason]) => <li key={action}>
              <span className="font-medium">{actionLabel(action)}:</span> {t(`agentTasks.blocked.${reason}`, { defaultValue: reason })}</li>)}</ul></details>}
          <Link className="inline-block text-primary underline" to={`/demands?message=${data.id}`}>{t("agentTasks.openMessages")}</Link>
        </div>
      </>}
  </section>;
}
