import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { useCreateMissionCriterion, useMissionCriteria } from "@/hooks/useMissions";
import type { MissionTask } from "@/hooks/useMissions";

type Reviewer = { agent_id: string; name: string };

function requestKey() {
  const value = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `mission-criterion-${value}`;
}

function errorText(error: unknown): string {
  if (error instanceof ApiError && error.body && typeof error.body === "object") {
    const root = error.body as { detail?: unknown };
    const detail = root.detail && typeof root.detail === "object"
      ? root.detail as { code?: string; message?: string } : null;
    if (detail?.code) return `${detail.code}: ${detail.message ?? ""}`.trim();
  }
  return error instanceof Error ? error.message : "Request failed";
}

export function MissionCriteria({
  projectId, tasks, reviewers, canManage,
}: {
  projectId: string; tasks: MissionTask[]; reviewers: Reviewer[]; canManage: boolean;
}) {
  const { t } = useTranslation("missions");
  const query = useMissionCriteria(projectId);
  const create = useCreateMissionCriterion(projectId);
  const [code, setCode] = useState("");
  const [statement, setStatement] = useState("");
  const [method, setMethod] = useState("");
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [verifier, setVerifier] = useState("marcelo");
  const uniqueReviewers = useMemo(() => [...new Map(reviewers.map(row => [row.agent_id, row])).values()], [reviewers]);
  const criteria = query.data ?? [];

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!code.trim() || !statement.trim() || !method.trim() || taskIds.length === 0) return;
    create.mutate({
      code: code.trim(), statement: statement.trim(), verification_method: method.trim(), task_ids: taskIds,
      ...(verifier === "marcelo" ? { verifier_is_marcelo: true } : { verifier_agent_id: verifier }),
      idempotency_key: requestKey(),
    }, { onSuccess: () => { setCode(""); setStatement(""); setMethod(""); setTaskIds([]); } });
  }

  return <section className="space-y-4 rounded-lg border bg-card p-4" aria-labelledby="mission-criteria-title">
    <div>
      <h2 id="mission-criteria-title" className="font-semibold">{t("criteria.title")}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{t("criteria.description")}</p>
    </div>
    {query.isLoading ? <p role="status">{t("criteria.loading")}</p>
      : query.isError ? <div role="alert" className="space-y-2"><p>{t("criteria.loadError")}</p>
        <Button size="sm" variant="outline" onClick={() => query.refetch()}>{t("board.retry")}</Button></div>
      : criteria.length === 0 ? <p className="text-sm text-muted-foreground">{t("criteria.empty")}</p>
        : <ul className="divide-y rounded-md border">
          {criteria.map(row => <li key={row.id} className="space-y-1 p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-medium">{row.code} · {row.statement}</h3>
              <span className="rounded-full border px-2 py-0.5 text-xs">{t(`criteria.status.${row.status}`)}</span>
            </div>
            <p className="text-sm text-muted-foreground">{t("criteria.method")}: {row.verification_method}</p>
            <p className="text-xs text-muted-foreground">{t("criteria.verifier")}: {row.verifier_is_marcelo
              ? t("criteria.marcelo")
              : uniqueReviewers.find(person => person.agent_id === row.verifier_agent_id)?.name
                ?? row.verifier_agent_id}</p>
            <p className="text-xs text-muted-foreground">{t("criteria.tasks", { count: row.task_ids.length,
              tasks: row.task_ids.map(id => tasks.find(task => task.task_id === id)?.title ?? id).join(", ") })}</p>
          </li>)}
        </ul>}
    {canManage && <form className="space-y-3 border-t pt-4" onSubmit={submit}>
      <h3 className="text-sm font-semibold">{t("criteria.create")}</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-sm"><span>{t("criteria.code")}</span>
          <Input maxLength={20} value={code} onChange={event => setCode(event.target.value)} required /></label>
        <label className="space-y-1 text-sm"><span>{t("criteria.verifier")}</span>
          <select className="h-10 w-full rounded-md border bg-background px-3" value={verifier}
            onChange={event => setVerifier(event.target.value)} disabled={create.isPending}>
            <option value="marcelo">{t("criteria.marcelo")}</option>
            {uniqueReviewers.map(person => <option key={person.agent_id} value={person.agent_id}>{person.name}</option>)}
          </select></label>
      </div>
      <label className="block space-y-1 text-sm"><span>{t("criteria.statement")}</span>
        <Textarea maxLength={12000} value={statement} onChange={event => setStatement(event.target.value)} required /></label>
      <label className="block space-y-1 text-sm"><span>{t("criteria.verificationMethod")}</span>
        <Textarea maxLength={4000} value={method} onChange={event => setMethod(event.target.value)} required /></label>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">{t("criteria.linkedTasks")}</legend>
        {tasks.length === 0 ? <p className="text-sm text-muted-foreground">{t("criteria.noTasks")}</p>
          : <div className="grid gap-2 sm:grid-cols-2">{tasks.map(task => <label key={task.task_id}
            className="flex items-start gap-2 rounded-md border p-2 text-sm">
            <input type="checkbox" className="mt-1" checked={taskIds.includes(task.task_id)}
              onChange={event => setTaskIds(current => event.target.checked
                ? [...current, task.task_id] : current.filter(id => id !== task.task_id))} />
            <span>{task.number ? `#${task.number} ` : ""}{task.title}</span>
          </label>)}</div>}
      </fieldset>
      {create.isError && <p role="alert" className="text-sm text-destructive">{errorText(create.error)}</p>}
      <Button type="submit" disabled={create.isPending || taskIds.length === 0 || !code.trim() || !statement.trim() || !method.trim()}>
        {create.isPending ? t("criteria.saving") : t("criteria.save")}
      </Button>
    </form>}
  </section>;
}
