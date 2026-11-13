import { useEffect, useRef, useState } from "react";
import { MoodleApprovalPanel } from "./MoodleApprovalPanel";
import { MissionDecisionsCard } from "./MissionDecisionsCard";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertCircle, Loader2 } from "lucide-react";
import { WORK_TABS, useAgentTasksViewModel, workState, type WorkTab } from "@/hooks/useAgentTasksViewModel";
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
  const location = useLocation();
  const questionId = new URLSearchParams(location.search).get("questionId");
  const [governed, setGoverned] = useState<{ id: string; decision: "approved" | "rejected" } | null>(null);
  const [comments, setComments] = useState("");
  const [question, setQuestion] = useState<{ id: string; text: string } | null>(null);
  const [answer, setAnswer] = useState("");
  const searchInput = useRef<HTMLInputElement>(null);
  const shown = vm.items;
  const selected = vm.selected;
  const action = vm.confirmation?.action;
  const evidenceRequired = action === "authorize_retry" || action === "record_investigation" || action === "confirm_inactive";
  const reasonRequired = action === "reject" || action === "postpone" || action === "drop" || evidenceRequired;
  const date = (value: string | null) => value ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
  const actionLabel = (name: string) => name === "approve" && (vm.confirmation?.item ?? selected)?.origin_type === "incubation"
    ? t("agentTasks.promote") : t(`agentTasks.actions.${name}`);
  const linkedQuestionId = vm.questions.find(item => item.id === questionId)?.id;
  useEffect(() => {
    if (!linkedQuestionId) return;
    const target = document.getElementById(`operator-question-${linkedQuestionId}`);
    target?.focus({ preventScroll: true });
    target?.scrollIntoView?.({ block: "center" });
  }, [linkedQuestionId]);
  const questionSection = <section aria-label={t("agentTasks.questionsTitle")} className="space-y-3">
    <h3 className="font-semibold">{vm.questionsError || vm.questionsLoading ? t("agentTasks.questionsTitle") : t("agentTasks.questionsHeading", { count: vm.questions.length })}</h3>
    {vm.questionsError && <p role="alert">{t("agentTasks.questionsError")}</p>}
    {vm.questions.map(item => <section id={`operator-question-${item.id}`} tabIndex={-1} key={item.id} className="space-y-2 rounded-md border p-4 focus-visible:outline focus-visible:outline-2">
      <h3 className="font-medium">{t(item.blocking ? "agentTasks.questionTitle" : "agentTasks.questionTitleOpen")} #{item.number} · {item.agent_name} · {item.id}</h3>
      {item.origin_demand_id ? <Link className="text-sm underline" to={`/demands?message=${item.origin_demand_id}`}>{t("agentTasks.questionTask")}</Link> : <p className="text-sm text-muted-foreground">{t("agentTasks.questionUnlinked")}</p>}
      <p className="text-xs text-muted-foreground">{date(item.created_at)}</p>
      <p className="whitespace-pre-wrap text-sm">{item.question}</p>
      {item.context && <p className="whitespace-pre-wrap text-sm text-muted-foreground">{item.context}</p>}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => { setQuestion({ id: item.id, text: item.question }); setAnswer(""); vm.answerQuestion.reset(); }}>{t("agentTasks.answer")}</Button>
        <Button size="sm" variant="outline" disabled={vm.archivingQuestion && vm.archiving?.id === item.id}
          aria-label={t("agentTasks.archiveQuestion.button", { number: item.number })}
          onClick={() => vm.askArchiveQuestion({ id: item.id, number: item.number, question: item.question })}>
          {vm.archivingQuestion && vm.archiving?.id === item.id && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}{t("agentTasks.archiveQuestion.label")}</Button>
      </div>
    </section>)}
    {!vm.questionsLoading && !vm.questionsError && vm.questions.length === 0 && <p className="text-sm text-muted-foreground">{t("agentTasks.answersEmpty")}</p>}
  </section>;
  const questionDialog = (<ConfirmDialog open={Boolean(question)} title={t("agentTasks.questionTitle")} description={question?.text} variant="default"
      confirmLabel={t("agentTasks.answer")} loading={vm.answerQuestion.isPending} error={vm.answerQuestion.error?.message} confirmDisabled={!answer.trim()}
      onCancel={() => { if (!vm.answerQuestion.isPending) setQuestion(null); }}
      onConfirm={() => { if (question) vm.answerQuestion.mutate({ id: question.id, answer }, { onSuccess: () => setQuestion(null) }); }}>
      <label className="block space-y-1 text-sm">{t("agentTasks.answer")}<Textarea className="resize-none" value={answer} onChange={e => setAnswer(e.target.value)} /></label>
    </ConfirmDialog>
  );

  const tabLabel = (tab: WorkTab) => tab === "approvals" ? t("agentTasks.tabs.approvalsCount", { count: vm.approvalsCount })
    : tab === "answers" ? t("agentTasks.tabs.answersCount", { count: vm.answersCount }) : t(`agentTasks.tabs.${tab}`);
  // Same scrolling strip as components/ui/tabs.tsx on a phone; sits beside the button from sm up.
  const tabStrip = <div role="tablist" aria-label={t("agentTasks.tabs.label")}
    className="flex max-w-full gap-1 overflow-x-auto rounded-md bg-muted p-1 max-sm:w-full">
    {WORK_TABS.map(tab => <button key={tab} type="button" role="tab" aria-selected={vm.tab === tab}
      className={`shrink-0 whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 ${vm.tab === tab ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
      onClick={() => vm.setTab(tab)}>{tabLabel(tab)}</button>)}
  </div>;
  const analysisButton = <Button aria-busy={vm.analysis.busy} disabled={vm.analysis.busy || vm.analysis.loading || vm.analysis.unavailable} onClick={() => vm.analysis.start.mutate()}>{t("agentTasks.analysis.start")}</Button>;
  const listTab = vm.tab === "tasks" || vm.tab === "incubation";
  const approvalsEmpty = vm.tab === "approvals" && !vm.query.isLoading && !vm.query.isError && vm.approvalsCount === 0;

  return <div className="space-y-4 pt-4">
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">{analysisButton}{tabStrip}</div>
      <p className="text-xs text-muted-foreground">{t("agentTasks.analysis.scope")}</p>
      <div className="min-h-12 text-sm" aria-live="polite" aria-atomic="true">
        {vm.analysis.loading ? <p role="status">{t("agentTasks.analysis.loading")}</p>
          : vm.analysis.error ? <div role="alert"><p>{t("agentTasks.analysis.unavailable")}</p><Button size="sm" variant="outline" onClick={vm.analysis.refresh}>{t("agentTasks.retryLoad")}</Button></div>
          : vm.analysis.run?.status === "failed" ? <div role="alert"><p>{t("agentTasks.analysis.failed")}</p>{vm.analysis.run.error && <p className="break-words">{vm.analysis.run.error}</p>}</div>
          : vm.analysis.run ? <p role="status">{t(`agentTasks.analysis.${vm.analysis.run.status}`, { processed: vm.analysis.run.processed, total: vm.analysis.run.total, applied: vm.analysis.run.applied })}</p>
          : <p role="status" className="text-muted-foreground">{t("agentTasks.analysis.ready")}</p>}
      </div>
    </div>
    {vm.notice && <p role="status" className="text-sm">{t("agentTasks.saved")}</p>}
    {vm.promotedTask && <Link className="text-sm underline" to={`/demands?message=${vm.promotedTask.id}`}>{t("agentTasks.viewPromotedTask", { number: vm.promotedTask.number })}</Link>}
    <p className="text-sm text-muted-foreground">{t(`agentTasks.tabDescriptions.${vm.tab}`)}</p>
    {vm.tab === "answers" && questionSection}
    {vm.tab === "approvals" && !approvalsEmpty && vm.queueCount > 0 && <h3 className="font-semibold">{t("agentTasks.approvalSections.queue", { count: vm.queueCount })}</h3>}
    {approvalsEmpty && <p className="text-sm text-muted-foreground">{t("agentTasks.approvalSections.empty")}</p>}
    {listTab && <div className="flex flex-wrap gap-2">
      <Select aria-label={t("agentTasks.view")} value={vm.view} onChange={e => vm.setView(e.target.value)} className="w-full sm:w-56">
        {vm.views.map(view => <option key={view} value={view}>{t(`agentTasks.views.${view}`)}{vm.counts[view] !== undefined ? ` (${vm.counts[view]})` : ""}</option>)}
      </Select>
      <Select aria-label={t("agentTasks.context")} value={vm.context} onChange={e => vm.setContext(e.target.value)} className="w-full sm:w-56">
        <option value="all">{t("agentTasks.allContexts")}</option>
        {vm.contexts.map(context => <option key={context.key} value={context.key}>{context.label ?? t("agentTasks.unclassified")}</option>)}
      </Select>
      <Select aria-label={t("agentTasks.agentFilter")} value={vm.agent} onChange={e => vm.setAgent(e.target.value)} className="w-full sm:w-52">
        <option value="all">{t("agentTasks.allAgents")}</option>{vm.agents.map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
      </Select>
      <Input ref={searchInput} aria-label={t("agentTasks.search")} placeholder={t("agentTasks.search")} value={vm.search} onChange={e => vm.setSearch(e.target.value)} onCompositionStart={() => vm.setComposing(true)} onCompositionEnd={() => vm.setComposing(false)} className="min-w-0 sm:max-w-xs" />
      {vm.search && <Button variant="outline" onClick={() => { vm.setSearch(""); searchInput.current?.focus(); }}>{t("agentTasks.clearSearch")}</Button>}
      <label className="space-y-1 text-sm">{t("agentTasks.createdFrom")}<Input type="date" value={vm.from} onChange={e => vm.setFrom(e.target.value)} /></label>
      <label className="space-y-1 text-sm">{t("agentTasks.createdTo")}<Input type="date" value={vm.to} min={vm.from || undefined} onChange={e => vm.setTo(e.target.value)} /></label>
    </div>}
    {vm.tab === "tasks" && vm.view === "decision" && (vm.moodlePending ?? 0) > 0 && <p className="text-sm">
      {t("agentTasks.tabs.moodleInDecision", { count: vm.moodlePending ?? 0 })}{" "}
      <button type="button" className="cursor-pointer text-primary underline" onClick={() => vm.setTab("approvals")}>{t("agentTasks.tabs.openApprovals")}</button></p>}
    {vm.selectedIds.length > 0 && <div className="flex flex-wrap items-center gap-2" role="region" aria-label={t("agentTasks.bulkSelection")}>
      <span className="text-sm">{t("agentTasks.selectedCount", { count: vm.selectedIds.length })}</span>
      <Button variant="outline" size="sm" onClick={() => vm.askBulk(vm.view === "archived" ? "restore" : "archive")}>{t(vm.view === "archived" ? "agentTasks.bulkRestore" : "agentTasks.bulkArchive")}</Button>
    </div>}
    {vm.bulkResults.length > 0 && <ul role="status" className="space-y-1 text-sm">{vm.bulkResults.map(result => <li key={result.id}>
      {result.number ? `#${result.number} · ${result.subject}` : result.subject ?? result.id}: {t(`agentTasks.bulkStatus.${result.status}`)}{result.detail ? ` — ${result.detail}` : ""}
    </li>)}</ul>}
    {(listTab || (vm.tab === "approvals" && (vm.query.isLoading || vm.query.isError || vm.total > 0))) && (vm.query.isLoading ? <p role="status" className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />{t("agentTasks.loading")}</p>
      : vm.query.isError ? <div role="alert"><p>{t("agentTasks.loadError")}</p><Button variant="outline" onClick={() => void vm.query.refetch()}>{t("agentTasks.retryLoad")}</Button></div>
      : <>
        <div className="overflow-x-auto rounded-md border">
          <Table><TableHeader><TableRow>
            <TableHead><input ref={element => { if (element) element.indeterminate = vm.selectedIds.length > 0 && vm.selectedIds.length < shown.length; }} type="checkbox" aria-label={t("agentTasks.selectPage")} checked={shown.length > 0 && vm.selectedIds.length === shown.length} disabled={!shown.length} onChange={vm.togglePage} /></TableHead>
            <TableHead>{t("agentTasks.task")}</TableHead><TableHead>{t("agentTasks.owner")}</TableHead>
            <TableHead>{t("agentTasks.context")}</TableHead><TableHead>{t("agentTasks.state")}</TableHead><TableHead>{t(vm.group === "incubation" ? "agentTasks.deadline" : "agentTasks.nextCheck")}</TableHead><TableHead>{t("agentTasks.rowActions")}</TableHead>
          </TableRow></TableHeader><TableBody>
            {!shown.length && <TableRow><TableCell colSpan={7} className="py-8 text-center text-muted-foreground">{t("agentTasks.empty")}</TableCell></TableRow>}
            {shown.map(item => <TableRow key={item.id} data-state={selected?.id === item.id ? "selected" : undefined}>
              <TableCell><input type="checkbox" aria-label={t("agentTasks.selectItem", { number: item.number })} checked={vm.selectedIds.includes(item.id)} onChange={() => vm.toggle(item.id)} /></TableCell>
              <TableCell className="min-w-56 max-w-lg"><button type="button" className="cursor-pointer text-left font-medium hover:underline focus-visible:outline focus-visible:outline-2" onClick={() => vm.setSelectedId(item.id)}>
                <span className="mr-2 font-mono text-muted-foreground">#{item.number}</span>{item.subject}
              </button>{item.analysis && <div className="mt-1 space-y-1 text-xs">
                <p>{item.analysis.summary}</p><p className="text-muted-foreground">{item.analysis.reason}</p>
                <p><span className="font-medium">{t("agentTasks.recommendation")}: </span>{item.analysis.recommendation}</p>
              </div>}<button type="button" className="mt-1 block cursor-pointer text-xs text-primary underline hover:text-primary/80 focus-visible:outline" onClick={() => vm.setSelectedId(item.id)}>{t("agentTasks.viewDetails")}</button></TableCell>
              <TableCell>{vm.agentName(item)}</TableCell><TableCell>{vm.contextName(item) ?? t("agentTasks.unclassified")}</TableCell>
              <TableCell><Badge variant={["uncertain", "failed", "overdue"].includes(vm.state(item)) ? "warning" : "outline"}>{t(`agentTasks.states.${vm.state(item)}`)}</Badge></TableCell>
              <TableCell className="whitespace-nowrap">{date(vm.group === "incubation" ? item.matures_at : vm.state(item) === "waiting" ? item.scheduled_at : null)}</TableCell>
              <TableCell><Button size="sm" variant="outline" disabled={!vm.allowed(item, item.status === "archived" ? "restore" : "archive")}
                aria-label={t(item.status === "archived" ? "agentTasks.restoreItem" : "agentTasks.archiveItem", { number: item.number })}
                title={item.blocked_actions?.archive ? t(`agentTasks.blocked.${item.blocked_actions.archive}`) : undefined}
                onClick={() => vm.ask(item, item.status === "archived" ? "restore" : "archive")}>{t(item.status === "archived" ? "agentTasks.actions.restore" : "agentTasks.actions.archive")}</Button></TableCell>
            </TableRow>)}
          </TableBody></Table>
        </div>
        <div className="flex items-center justify-between gap-2 text-sm" role="status">
          <span>{t("agentTasks.pageTotal", { page: vm.page, count: vm.total })}</span>
          <div className="flex gap-2"><Button variant="outline" size="sm" disabled={vm.page <= 1} onClick={() => vm.setPage(vm.page - 1)}>{t("agentTasks.previous")}</Button>
            <Button variant="outline" size="sm" disabled={vm.page * 25 >= vm.total} onClick={() => vm.setPage(vm.page + 1)}>{t("agentTasks.next")}</Button></div>
        </div>
      </>)}
    {vm.tab !== "answers" && selected && <section aria-label={t("agentTasks.detail")} className="space-y-3 rounded-md border p-4">
      <h3 className="font-semibold">#{selected.number} · {selected.subject}</h3>
      <p className="text-sm text-muted-foreground">{vm.agentName(selected)} · {t("agentTasks.attempts", { count: selected.dispatch_attempts })}</p>
      {selected.analysis && <div className="space-y-1 border-l-2 pl-3 text-sm">
        <p>{selected.analysis.summary}</p><p className="text-muted-foreground">{selected.analysis.reason}</p>
        <p>{t("agentTasks.recommendation")}: {selected.analysis.recommendation}</p>
        {selected.analysis.related_message_id && <Link className="underline" to={`/demands?message=${selected.analysis.related_message_id}`}>{t("agentTasks.relatedMessage")}</Link>}
        <p className="text-xs text-muted-foreground">{t("agentTasks.analyzedAt")}: {date(selected.analysis.analyzed_at)}</p>
      </div>}
      {selected.dispatch_error && <p className="break-words text-sm text-destructive"><AlertCircle className="mr-1 inline h-4 w-4" />{selected.dispatch_error}</p>}
      {workState(selected) === "uncertain" && <p className="text-sm">{t("agentTasks.uncertainHint")}</p>}
      {selected.moodle_approval && <p className="text-sm rounded border p-3">{t("agentTasks.moodleRelated")} · {t(`agentTasks.moodleStates.${selected.moodle_approval.outcome === "completed" ? "completed" : selected.moodle_approval.state}`)}
        <Link className="ml-2 underline" to="/personal?tab=agent-work&workTab=approvals">{t("agentTasks.groups.moodle")}</Link></p>}
      {selected.requires_approval && <p className="text-sm">{t("agentTasks.approvalHint")}</p>}
      {selected.decision_reason && <p className="whitespace-pre-wrap text-sm">{t("agentTasks.reason")}: {selected.decision_reason}</p>}
      <div className="flex flex-wrap gap-2">
        {(["approve", "reject", "postpone", "drop", "restore", "reconcile", "record_investigation", "confirm_inactive", "retry", "authorize_retry", "archive", "delete"] as const).filter(action => vm.allowed(selected, action)).map(action => <Button key={action} size="sm" variant={action === "delete" ? "destructive" : action === "approve" ? "default" : "outline"} onClick={() => vm.ask(selected, action)}>{actionLabel(action)}</Button>)}
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
    {vm.tab === "approvals" && (vm.moodlePending ?? 0) > 0 && <div className="space-y-2">
      <h3 className="font-semibold">{t("agentTasks.approvalSections.moodleCount", { count: vm.moodlePending ?? 0 })}</h3>
      <MoodleApprovalPanel />
    </div>}
    {vm.tab === "approvals" && <MissionDecisionsCard />}
    {vm.tab === "approvals" && (vm.taskApprovals.length > 0 || vm.approvals.isError) && <section aria-label={t("agentTasks.reviewsTitle")} className="space-y-2">
      <h3 className="font-semibold">{vm.approvals.isError ? t("agentTasks.reviewsTitle") : t("agentTasks.reviewsHeading", { count: vm.taskApprovals.length })}</h3>
      {vm.approvals.isError && <p role="alert">{t("agentTasks.governedError")}</p>}
      {vm.taskApprovals.map(request => <section key={request.id} className="space-y-2 rounded-md border p-4">
        <h3 className="font-medium">{t("agentTasks.governedTitle")}: {vm.taskName(request.target_id)}</h3>
        <p className="text-sm text-muted-foreground">{request.requested_by_name} · {date(request.created_at)}</p>
        <div className="flex flex-wrap gap-2"><Button size="sm" onClick={() => { setGoverned({ id: request.id, decision: "approved" }); setComments(""); vm.decideApproval.reset(); }}>{t("agentTasks.approveCompletion")}</Button>
          <Button size="sm" variant="outline" onClick={() => { setGoverned({ id: request.id, decision: "rejected" }); setComments(""); vm.decideApproval.reset(); }}>{t("agentTasks.requestRevision")}</Button></div>
      </section>)}
    </section>}
    <ConfirmDialog open={Boolean(vm.confirmation)} title={action ? actionLabel(action) : ""}
      description={vm.confirmation ? `#${vm.confirmation.item.number} · ${vm.confirmation.item.subject}` : undefined}
      confirmLabel={action ? actionLabel(action) : undefined} variant={action === "delete" ? "destructive" : "default"}
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
      confirmLabel={t(governed?.decision === "approved" ? "agentTasks.approveCompletion" : "agentTasks.requestRevision")}
      loading={vm.decideApproval.isPending} error={vm.decideApproval.error?.message} confirmDisabled={governed?.decision === "rejected" && !comments.trim()}
      onCancel={() => { if (!vm.decideApproval.isPending) setGoverned(null); }}
      onConfirm={() => { if (governed) vm.decideApproval.mutate({ requestId: governed.id, decision: governed.decision, comments }, { onSuccess: () => setGoverned(null) }); }}>
      <label className="block space-y-1 text-sm">{t("agentTasks.reason")}<Textarea className="resize-none" value={comments} onChange={e => setComments(e.target.value)} /></label>
    </ConfirmDialog>
    {questionDialog}
    <ConfirmDialog open={Boolean(vm.archiving)} variant="destructive" icon="trash"
      title={t("agentTasks.archiveQuestion.title", { number: vm.archiving?.number ?? "" })}
      description={vm.archiving?.question}
      confirmLabel={t("agentTasks.archiveQuestion.label")} loading={vm.archivingQuestion} error={vm.archiveQuestionError ?? undefined}
      confirmDisabled={!vm.archiveReasonValid} onCancel={vm.cancelArchiveQuestion} onConfirm={vm.confirmArchiveQuestion}>
      <p className="text-sm">{t("agentTasks.archiveQuestion.hint")}</p>
      <label className="mt-3 block space-y-1 text-sm">{t("agentTasks.archiveQuestion.reason")}
        <Textarea className="resize-none max-md:text-base" maxLength={4000} value={vm.archiveReason} onChange={e => vm.setArchiveReason(e.target.value)} /></label>
    </ConfirmDialog>
  </div>;
}
