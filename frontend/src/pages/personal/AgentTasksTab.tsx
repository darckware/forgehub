import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";
import { WORK_VIEWS, useAgentTasksViewModel, workState } from "@/hooks/useAgentTasksViewModel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/Markdown";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function AgentTasksTab() {
  const { t, i18n } = useTranslation("personal");
  const vm = useAgentTasksViewModel();
  const [governed, setGoverned] = useState<{ id: string; decision: "approved" | "rejected" } | null>(null);
  const [comments, setComments] = useState("");
  const [question, setQuestion] = useState<{ id: string; text: string } | null>(null);
  const [answer, setAnswer] = useState("");
  const shown = vm.items;
  const selected = vm.selected;
  const action = vm.confirmation?.action;
  const evidenceRequired = action === "authorize_retry" || action === "record_investigation" || action === "confirm_inactive";
  const reasonRequired = action === "reject" || action === "postpone" || action === "drop" || evidenceRequired;
  const date = (value: string | null) => value ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";

  return <div className="space-y-4 pt-4">
    <p className="text-sm text-muted-foreground">{t("agentTasks.description")}</p>
    {vm.notice && <p role="status" className="text-sm">{t("agentTasks.saved")}</p>}
    <div className="flex flex-wrap gap-2">
      <Select aria-label={t("agentTasks.view")} value={vm.view} onChange={e => vm.setView(e.target.value)} className="w-full sm:w-56">
        {WORK_VIEWS.map(view => <option key={view} value={view}>{t(`agentTasks.views.${view}`)}{vm.counts[view] !== undefined ? ` (${vm.counts[view]})` : ""}</option>)}
      </Select>
      <Select aria-label={t("agentTasks.context")} value={vm.context} onChange={e => vm.setContext(e.target.value)} className="w-full sm:w-56">
        <option value="all">{t("agentTasks.allContexts")}</option>
        {vm.contexts.map(context => <option key={context.key} value={context.key}>{context.label ?? t("agentTasks.unclassified")}</option>)}
      </Select>
      <Select aria-label={t("agentTasks.agentFilter")} value={vm.agent} onChange={e => vm.setAgent(e.target.value)} className="w-full sm:w-52">
        <option value="all">{t("agentTasks.allAgents")}</option>{vm.agents.map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
      </Select>
      <Input aria-label={t("agentTasks.search")} placeholder={t("agentTasks.search")} value={vm.search} onChange={e => vm.setSearch(e.target.value)} onCompositionStart={() => vm.setComposing(true)} onCompositionEnd={() => vm.setComposing(false)} className="min-w-0 sm:max-w-xs" />
      <label className="space-y-1 text-sm">{t("agentTasks.createdFrom")}<Input type="date" value={vm.from} onChange={e => vm.setFrom(e.target.value)} /></label>
      <label className="space-y-1 text-sm">{t("agentTasks.createdTo")}<Input type="date" value={vm.to} min={vm.from || undefined} onChange={e => vm.setTo(e.target.value)} /></label>
    </div>
    {vm.selectedIds.length > 0 && <div className="flex flex-wrap items-center gap-2" role="region" aria-label={t("agentTasks.bulkSelection")}>
      <span className="text-sm">{t("agentTasks.selectedCount", { count: vm.selectedIds.length })}</span>
      <Button variant="outline" size="sm" onClick={() => vm.askBulk(vm.view === "archived" ? "restore" : "archive")}>{t(vm.view === "archived" ? "agentTasks.bulkRestore" : "agentTasks.bulkArchive")}</Button>
    </div>}
    {vm.bulkResults.length > 0 && <ul role="status" className="space-y-1 text-sm">{vm.bulkResults.map(result => <li key={result.id}>
      {result.number ? `#${result.number} · ${result.subject}` : result.subject ?? result.id}: {t(`agentTasks.bulkStatus.${result.status}`)}{result.detail ? ` — ${result.detail}` : ""}
    </li>)}</ul>}
    {vm.query.isLoading ? <p role="status" className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />{t("agentTasks.loading")}</p>
      : vm.query.isError ? <div role="alert"><p>{t("agentTasks.loadError")}</p><Button variant="outline" onClick={() => void vm.query.refetch()}>{t("agentTasks.retryLoad")}</Button></div>
      : <>
        <div className="overflow-x-auto rounded-md border">
          <Table><TableHeader><TableRow>
            <TableHead><input ref={element => { if (element) element.indeterminate = vm.selectedIds.length > 0 && vm.selectedIds.length < shown.length; }} type="checkbox" aria-label={t("agentTasks.selectPage")} checked={shown.length > 0 && vm.selectedIds.length === shown.length} disabled={!shown.length} onChange={vm.togglePage} /></TableHead>
            <TableHead>{t("agentTasks.task")}</TableHead><TableHead>{t("agentTasks.owner")}</TableHead>
            <TableHead>{t("agentTasks.context")}</TableHead><TableHead>{t("agentTasks.state")}</TableHead><TableHead>{t("agentTasks.deadline")}</TableHead>
          </TableRow></TableHeader><TableBody>
            {!shown.length && <TableRow><TableCell colSpan={6} className="py-8 text-center text-muted-foreground">{t("agentTasks.empty")}</TableCell></TableRow>}
            {shown.map(item => <TableRow key={item.id} data-state={selected?.id === item.id ? "selected" : undefined}>
              <TableCell><input type="checkbox" aria-label={t("agentTasks.selectItem", { number: item.number })} checked={vm.selectedIds.includes(item.id)} onChange={() => vm.toggle(item.id)} /></TableCell>
              <TableCell className="min-w-56 max-w-lg"><button type="button" className="text-left font-medium hover:underline focus-visible:outline focus-visible:outline-2" onClick={() => vm.setSelectedId(item.id)}>
                <span className="mr-2 font-mono text-muted-foreground">#{item.number}</span>{item.subject}
              </button></TableCell>
              <TableCell>{vm.agentName(item)}</TableCell><TableCell>{vm.contextName(item) ?? t("agentTasks.unclassified")}</TableCell>
              <TableCell><Badge variant={["uncertain", "failed", "overdue"].includes(vm.state(item)) ? "warning" : "outline"}>{t(`agentTasks.states.${vm.state(item)}`)}</Badge></TableCell>
              <TableCell className="whitespace-nowrap">{date(item.matures_at)}</TableCell>
            </TableRow>)}
          </TableBody></Table>
        </div>
        <div className="flex items-center justify-between gap-2 text-sm" role="status">
          <span>{t("agentTasks.pageTotal", { page: vm.page, count: vm.total })}</span>
          <div className="flex gap-2"><Button variant="outline" size="sm" disabled={vm.page <= 1} onClick={() => vm.setPage(vm.page - 1)}>{t("agentTasks.previous")}</Button>
            <Button variant="outline" size="sm" disabled={vm.page * 25 >= vm.total} onClick={() => vm.setPage(vm.page + 1)}>{t("agentTasks.next")}</Button></div>
        </div>
      </>}
    {selected && <section aria-label={t("agentTasks.detail")} className="space-y-3 rounded-md border p-4">
      <h3 className="font-semibold">#{selected.number} · {selected.subject}</h3>
      <p className="text-sm text-muted-foreground">{vm.agentName(selected)} · {t("agentTasks.attempts", { count: selected.dispatch_attempts })}</p>
      {selected.dispatch_error && <p className="break-words text-sm text-destructive"><AlertCircle className="mr-1 inline h-4 w-4" />{selected.dispatch_error}</p>}
      {workState(selected) === "uncertain" && <p className="text-sm">{t("agentTasks.uncertainHint")}</p>}
      {selected.requires_approval && <p className="text-sm">{t("agentTasks.approvalHint")}</p>}
      {selected.decision_reason && <p className="whitespace-pre-wrap text-sm">{t("agentTasks.reason")}: {selected.decision_reason}</p>}
      <div className="flex flex-wrap gap-2">
        {(["approve", "reject", "postpone", "drop", "restore", "reconcile", "record_investigation", "confirm_inactive", "retry", "authorize_retry", "archive", "delete"] as const).filter(action => vm.allowed(selected, action)).map(action => <Button key={action} size="sm" variant={action === "delete" ? "destructive" : action === "approve" ? "default" : "outline"} onClick={() => vm.ask(selected, action)}>{t(`agentTasks.actions.${action}`)}</Button>)}
        <Link className="self-center text-sm text-primary underline" to={`/demands?message=${selected.id}`}>{t("agentTasks.openMessages")}</Link>
      </div>
      {selected.blocked_actions?.approve && selected.dispatch_status === null && <p className="text-sm text-muted-foreground">{t(`agentTasks.blocked.${selected.blocked_actions.approve}`)}</p>}
      {vm.dependenciesError && <p role="alert">{t("agentTasks.dependenciesError")}</p>}
      {vm.sourcesError && <p role="alert">{t("agentTasks.sourcesError")}</p>}
      {vm.dependencies.length > 0 && <div><h4 className="text-sm font-medium">{t("agentTasks.dependencies")}</h4><ul className="mt-1 space-y-1 text-sm">
        {vm.dependencies.map(task => task && <li key={task.id}>#{task.number} · {task.title} — {t(`agentTasks.taskStates.${task.status}`)}</li>)}
      </ul></div>}
      {vm.sources.length > 0 && <div><h4 className="text-sm font-medium">{t("agentTasks.sources")}</h4><ul className="mt-1 space-y-1 text-sm">
        {vm.sources.map(item => <li key={item.id}><Link className="text-primary underline" to={`/demands?message=${item.id}`}>#{item.number} · {item.subject}</Link>
          {item.dispatch_error?.includes("uncertain") && <span className="ml-2">{t("agentTasks.states.uncertain")}</span>}</li>)}
      </ul></div>}
      {selected.consolidated_into_id && <Link className="text-sm text-primary underline" to={`/demands?message=${selected.consolidated_into_id}`}>{t("agentTasks.openSummary")}</Link>}
      <div className="max-h-96 overflow-auto break-words text-sm"><Markdown content={selected.body} /></div>
      {selected.dispatch_result && <details><summary className="cursor-pointer text-sm">{t("agentTasks.result")}</summary><div className="mt-2 max-h-96 overflow-auto break-words text-sm"><Markdown content={selected.dispatch_result} /></div></details>}
      <details><summary className="cursor-pointer text-sm">{t("agentTasks.history")}</summary>
        {vm.history.isLoading ? <p role="status">{t("agentTasks.loading")}</p> : vm.history.isError ? <p role="alert">{t("agentTasks.historyError")}</p> : <ol className="mt-2 space-y-3 text-sm">{(vm.history.data ?? []).map(event => <li key={event.id} className="border-l-2 pl-3">
          <p>{t(`agentTasks.events.${event.action}`, { defaultValue: event.action })} · {event.actor} · {date(event.created_at)}</p>
          {Boolean(event.payload?.run_id) && <p className="break-all font-mono text-xs">{String(event.payload?.run_id)}</p>}
          {Boolean(event.payload?.reason) && <p>{String(event.payload?.reason)}</p>}
          {Boolean(event.payload?.evidence_ref) && <p className="break-words">{t("agentTasks.evidence")}: {String(event.payload?.evidence_ref)}</p>}
          {Boolean(event.payload?.error) && <p className="break-words text-destructive">{String(event.payload?.error)}</p>}
          {Boolean(event.payload?.result) && <details><summary>{t("agentTasks.result")}</summary><Markdown content={String(event.payload?.result)} /></details>}
        </li>)}</ol>}
      </details>
    </section>}
    {vm.approvals.isError && <p role="alert">{t("agentTasks.governedError")}</p>}
    {["attention", "approval"].includes(vm.view) && (vm.approvals.data ?? []).filter(request => request.target_type === "project_task").map(request => <section key={request.id} className="space-y-2 rounded-md border p-4">
      <h3 className="font-medium">{t("agentTasks.governedTitle")}: {vm.taskName(request.target_id)}</h3>
      <p className="text-sm text-muted-foreground">{request.requested_by_name} · {date(request.created_at)}</p>
      <div className="flex gap-2"><Button size="sm" onClick={() => { setGoverned({ id: request.id, decision: "approved" }); setComments(""); vm.decideApproval.reset(); }}>{t("agentTasks.actions.approve")}</Button>
        <Button size="sm" variant="outline" onClick={() => { setGoverned({ id: request.id, decision: "rejected" }); setComments(""); vm.decideApproval.reset(); }}>{t("agentTasks.actions.reject")}</Button></div>
    </section>)}
    {vm.questionsError && <p role="alert">{t("agentTasks.questionsError")}</p>}
    {["attention", "approval"].includes(vm.view) && vm.questions.map(item => <section key={item.id} className="space-y-2 rounded-md border p-4">
      <h3 className="font-medium">{t("agentTasks.questionTitle")} #{item.number} · {item.agent_name}</h3>
      <p className="whitespace-pre-wrap text-sm">{item.question}</p>
      {item.context && <p className="whitespace-pre-wrap text-sm text-muted-foreground">{item.context}</p>}
      <Button size="sm" onClick={() => { setQuestion({ id: item.id, text: item.question }); setAnswer(""); vm.answerQuestion.reset(); }}>{t("agentTasks.answer")}</Button>
    </section>)}
    <ConfirmDialog open={Boolean(vm.confirmation)} title={action ? t(`agentTasks.actions.${action}`) : ""}
      description={vm.confirmation ? `#${vm.confirmation.item.number} · ${vm.confirmation.item.subject}` : undefined}
      confirmLabel={action ? t(`agentTasks.actions.${action}`) : undefined} variant={action === "delete" ? "destructive" : "default"}
      loading={vm.mutation.isPending} error={vm.mutationError} onConfirm={vm.confirm} onCancel={vm.cancel}
      confirmDisabled={(reasonRequired && !vm.reason.trim()) || (evidenceRequired && !vm.evidence.trim()) || (action === "confirm_inactive" && vm.confirmation !== null && vm.runConfirmation.trim() !== vm.runIdentifier(vm.confirmation.item)) || (action === "postpone" && (!vm.postponeAt || new Date(vm.postponeAt).getTime() <= Date.now()))}>
      {action === "approve" && <p className="text-sm">{t("agentTasks.approveHint")}</p>}
      {action === "archive" && <p className="text-sm">{t("agentTasks.archiveHint")}</p>}
      {action === "restore" && <p className="text-sm">{t("agentTasks.restoreHint")}</p>}
      {action === "authorize_retry" && <p className="text-sm">{t("agentTasks.authorizeRetryHint")}</p>}
      {action === "record_investigation" && <p className="text-sm">{t("agentTasks.investigationHint")}</p>}
      {action === "confirm_inactive" && vm.confirmation && <><p className="text-sm">{t("agentTasks.confirmInactiveHint")}</p>
        <label className="block space-y-1 text-sm">{t("agentTasks.typeRun")} <code className="break-all font-mono text-xs">{vm.runIdentifier(vm.confirmation.item)}</code>
          <Input autoComplete="off" value={vm.runConfirmation} onChange={e => vm.setRunConfirmation(e.target.value)} className="font-mono max-md:text-base" /></label></>}
      {evidenceRequired && <label className="block space-y-1 text-sm">{t("agentTasks.evidence")}<Input value={vm.evidence} onChange={e => vm.setEvidence(e.target.value)} /></label>}
      {reasonRequired && <label className="block space-y-1 text-sm">{t("agentTasks.reason")}<Textarea className="resize-none" value={vm.reason} onChange={e => vm.setReason(e.target.value)} /></label>}
      {action === "postpone" && <label className="mt-3 block space-y-1 text-sm">{t("agentTasks.newDeadline")}<Input type="datetime-local" value={vm.postponeAt} onChange={e => vm.setPostponeAt(e.target.value)} /></label>}
    </ConfirmDialog>
    <ConfirmDialog open={Boolean(vm.bulkConfirmation)} title={t(vm.bulkConfirmation?.action === "restore" ? "agentTasks.bulkRestore" : "agentTasks.bulkArchive")}
      confirmLabel={t(vm.bulkConfirmation?.action === "restore" ? "agentTasks.bulkRestore" : "agentTasks.bulkArchive")} variant="default" loading={vm.bulk.isPending} error={vm.bulkError} onConfirm={vm.confirmBulk} onCancel={vm.cancelBulk}>
      <p className="text-sm">{t("agentTasks.bulkHint")}</p><ul className="mt-2 max-h-64 overflow-auto text-sm">{vm.bulkConfirmation?.items.map(item => <li key={item.id}>#{item.number} · {item.subject}</li>)}</ul>
    </ConfirmDialog>
    <ConfirmDialog open={Boolean(governed)} title={t("agentTasks.governedTitle")} variant="default"
      confirmLabel={t(governed?.decision === "approved" ? "agentTasks.actions.approve" : "agentTasks.actions.reject")}
      loading={vm.decideApproval.isPending} error={vm.decideApproval.error?.message} confirmDisabled={governed?.decision === "rejected" && !comments.trim()}
      onCancel={() => { if (!vm.decideApproval.isPending) setGoverned(null); }}
      onConfirm={() => { if (governed) vm.decideApproval.mutate({ requestId: governed.id, decision: governed.decision, comments }, { onSuccess: () => setGoverned(null) }); }}>
      <label className="block space-y-1 text-sm">{t("agentTasks.reason")}<Textarea className="resize-none" value={comments} onChange={e => setComments(e.target.value)} /></label>
    </ConfirmDialog>
    <ConfirmDialog open={Boolean(question)} title={t("agentTasks.questionTitle")} description={question?.text} variant="default"
      confirmLabel={t("agentTasks.answer")} loading={vm.answerQuestion.isPending} error={vm.answerQuestion.error?.message} confirmDisabled={!answer.trim()}
      onCancel={() => { if (!vm.answerQuestion.isPending) setQuestion(null); }}
      onConfirm={() => { if (question) vm.answerQuestion.mutate({ id: question.id, answer }, { onSuccess: () => setQuestion(null) }); }}>
      <label className="block space-y-1 text-sm">{t("agentTasks.answer")}<Textarea className="resize-none" value={answer} onChange={e => setAnswer(e.target.value)} /></label>
    </ConfirmDialog>
  </div>;
}
