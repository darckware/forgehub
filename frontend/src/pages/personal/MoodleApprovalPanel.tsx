import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useAgents, useStreamTelegramImprovePrompt } from "@/hooks/useAgent";
import { ImprovePromptDialog } from "@/components/chat/ImprovePromptDialog";
import { Sparkles } from "lucide-react";
import { ApiError, apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Link } from "react-router-dom";

type BatchCandidate = { id: number; username: string };
type BatchRow = { row: number; action: "create" | "existing"; full_name: string | null; firstname: string | null; lastname: string | null; username: string | null; email: string | null; userid: number | null; course: string | null; group: string | null; account_only: boolean; corrected_fields: string[]; possible_duplicate_of: BatchCandidate[] };
type StudentBatch = { total: number; new_accounts: number; existing: number; account_only: number; units: string[]; courses: string[]; groups: string[]; rows: BatchRow[]; held_rows: { row: number; full_name: string; candidates: BatchCandidate[] }[]; rejected_rows: { row: number; label: string; code: string; reason: string }[] };
type Approval = { request_id: string; message_id: string; number: number; summary: string; operation: string; environment: string; host: string; params: unknown; batch?: StudentBatch | null; destructive: boolean; params_hash: string; message_updated_at: string; expires_at: string };
const endpoint = "/api/v1/personal/moodle-approvals";
const key = ["personal", "moodle-approvals"];

type Decision = { action: "approve" | "reject"; items: Approval[] };
type Activity = { number: number; message_id: string; state: string; outcome: string | null; dispatch_status: string | null };

function BatchDetails({ batch }: { batch: StudentBatch }) {
  const { t } = useTranslation("personal");
  return <div className="mt-2 space-y-1 text-sm">
    <p className="font-medium">{t("moodleApproval.batch.title")}: {t("moodleApproval.batch.total", { count: batch.total })}</p>
    <p>{t("moodleApproval.batch.newAccounts", { count: batch.new_accounts })} · {t("moodleApproval.batch.existing", { count: batch.existing })}</p>
    {batch.account_only > 0 && <p>{t("moodleApproval.batch.accountOnly", { count: batch.account_only })}</p>}
    {batch.units.length > 0 && <p className="break-words">{t("moodleApproval.batch.unit")}: {batch.units.join(", ")}</p>}
    {batch.courses.length > 0 && <p className="break-words">{t("moodleApproval.batch.course")}: {batch.courses.join(", ")}</p>}
    {batch.groups.length > 0 && <p className="break-words">{t("moodleApproval.batch.group")}: {batch.groups.join(", ")}</p>}
    {batch.held_rows.length > 0 && <div role="alert"><p className="font-medium">{t("moodleApproval.batch.held", { count: batch.held_rows.length })}</p><ul>{batch.held_rows.map(row => <li key={row.row} className="break-words">{row.full_name} · {row.candidates.map(c => t("moodleApproval.batch.candidate", { id: c.id, username: c.username })).join("; ")}</li>)}</ul></div>}
    {batch.rejected_rows.length > 0 && <div><p className="font-medium">{t("moodleApproval.batch.rejected", { count: batch.rejected_rows.length })}</p><ul>{batch.rejected_rows.map(row => <li key={row.row} className="break-words">{row.label}: {row.reason}</li>)}</ul></div>}
    <details><summary className="cursor-pointer underline">{t("moodleApproval.batch.open")}</summary>
      <ul className="mt-1 space-y-2">{batch.rows.map(row => <li key={row.row} className="break-words rounded border p-2">
        <strong>{row.full_name}</strong> · {t(row.action === "create" ? "moodleApproval.batch.newAccount" : "moodleApproval.batch.existingAccount")}
        {row.action === "create" && <span className="block">{row.firstname} / {row.lastname}</span>}
        <span className="block break-all">{row.username}{row.email ? ` · ${row.email}` : ""}</span>
        <span className="block">{row.account_only ? t("moodleApproval.batch.noTarget") : `${row.course} · ${row.group}`}</span>
        {row.corrected_fields.length > 0 && <span className="block">{t("moodleApproval.batch.corrected", { fields: row.corrected_fields.join(", ") })}</span>}
        {row.possible_duplicate_of.length > 0 && <span className="block" role="alert">{t("moodleApproval.batch.keptDuplicate")}: {row.possible_duplicate_of.map(c => t("moodleApproval.batch.candidate", { id: c.id, username: c.username })).join("; ")}</span>}
      </li>)}</ul>
    </details>
  </div>;
}

export function MoodleApprovalPanel() {
  const { t } = useTranslation("personal");
  const agents = useAgents();
  const athos = agents.data?.find(a => a.profile_slug?.toLowerCase() === "athos" || a.name.trim().toLowerCase() === "athos");
  const improvePrompt = useStreamTelegramImprovePrompt(athos?.id ?? "");
  const [improveOpen, setImproveOpen] = useState(false);
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: key, queryFn: () => apiClient.get<{ items: Approval[]; unavailable_count?: number; activity?: Activity[] }>(endpoint), refetchInterval: 30_000 });
  const [selected, setSelected] = useState<string[]>([]);
  const [executor, setExecutor] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [decision, setDecision] = useState<Decision | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [outcome, setOutcome] = useState<"approved" | "rejected" | "error" | null>(null);
  const agentId = executor ?? agents.data?.find(a => a.profile_slug?.toLowerCase() === "maia" || a.name.toLowerCase() === "maia")?.id ?? "";
  const items = Array.isArray(query.data?.items) ? query.data.items : [];
  const chosen = items.filter(item => selected.includes(item.request_id));
  const ask = (action: Decision["action"], targets: Approval[]) => { setOutcome(null); setReason(""); setDecision({ action, items: targets }); };
  async function decide() {
    if (busyRef.current || !decision) return;
    busyRef.current = true; setBusy(true); setOutcome(null);
    const batch = decision.items.map(({ request_id, message_id, params_hash, message_updated_at }) => ({ request_id, message_id, params_hash, message_updated_at }));
    try {
      if (decision.action === "approve") await apiClient.post(`${endpoint}/authorize`, { executor_agent_id: agentId, instruction, items: batch });
      else await apiClient.post(`${endpoint}/reject`, { reason: reason.trim() || null, items: batch });
      const done = decision.items.map(item => item.request_id);
      setSelected(ids => ids.filter(id => !done.includes(id)));
      if (decision.action === "approve") setInstruction("");
      setOutcome(decision.action === "approve" ? "approved" : "rejected");
      void queryClient.invalidateQueries({ queryKey: key });
      void queryClient.invalidateQueries({ queryKey: ["demands"] });
    } catch { setOutcome("error"); }
    finally { setDecision(null); busyRef.current = false; setBusy(false); }
  }
  if (query.error instanceof ApiError && [404, 503].includes(query.error.status)) return <section aria-label={t("moodleApproval.title")} className="rounded-md border p-4"><p role="status">{t("moodleApproval.unavailable")}</p></section>;
  const rejecting = decision?.action === "reject";
  return <section className="space-y-3 rounded-md border p-4" aria-label={t("moodleApproval.title")}>
    <h3 className="font-semibold">{t("moodleApproval.title")}</h3>
    <p className="text-sm text-muted-foreground">{t("moodleApproval.hint")}</p>
    {query.isLoading && <p role="status">{t("moodleApproval.loading")}</p>}
    {query.isError && <div role="alert"><p>{t("moodleApproval.loadError")}</p><Button variant="outline" onClick={() => void query.refetch()}>{t("moodleApproval.retry")}</Button></div>}
    {!query.isLoading && !query.isError && !items.length && !query.data?.unavailable_count && <p className="text-sm">{t("moodleApproval.empty")}</p>}
    {Boolean(query.data?.unavailable_count) && <p role="alert">{t("moodleApproval.invalidSources", { count: query.data?.unavailable_count })}</p>}
    {items.length > 0 && <>
      <ul className="max-h-96 space-y-2 overflow-auto">{items.map(item => <li key={item.request_id} className="flex flex-col gap-2 rounded-md border p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0"><label className="flex min-w-0 gap-2"><input type="checkbox" aria-label={t("moodleApproval.select", { number: item.number })} checked={selected.includes(item.request_id)} disabled={busy} onChange={e => setSelected(ids => e.target.checked ? [...ids, item.request_id] : ids.filter(id => id !== item.request_id))} /><span className="min-w-0 break-words"><strong>#{item.number} · {item.summary}</strong><span className="block">{t("moodleApproval.operation")}: {item.operation} · {t("moodleApproval.environment")}: {item.environment} · {item.destructive ? t("moodleApproval.destructive") : t("moodleApproval.nonDestructive")}</span></span></label>{item.batch && <BatchDetails batch={item.batch} />}</div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" disabled={busy || !agentId} aria-label={t("moodleApproval.approveOne", { number: item.number })} onClick={() => ask("approve", [item])}>{t("moodleApproval.approve")}</Button>
          <Button size="sm" variant="outline" disabled={busy} aria-label={t("moodleApproval.rejectOne", { number: item.number })} onClick={() => ask("reject", [item])}>{t("moodleApproval.reject")}</Button>
        </div>
      </li>)}</ul>
      {chosen.length > 1 && <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy || !agentId} onClick={() => ask("approve", chosen)}>{t("moodleApproval.approveSelected", { count: chosen.length })}</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => ask("reject", chosen)}>{t("moodleApproval.rejectSelected", { count: chosen.length })}</Button>
      </div>}
      <label className="block space-y-1 text-sm">{t("moodleApproval.executor")}<Select value={agentId} disabled={busy} onChange={e => setExecutor(e.target.value)}><option value="">{t("moodleApproval.chooseAgent")}</option>{(agents.data ?? []).map(agent => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</Select></label>
      <p className="text-xs text-muted-foreground">{t("moodleApproval.executorAccessHint")}</p>
      {agents.isError && <p role="alert">{t("moodleApproval.agentsError")}</p>}
      <label className="block space-y-1 text-sm">{t("moodleApproval.instruction")}<Textarea className="resize-none" rows={3} value={instruction} disabled={busy} onChange={e => setInstruction(e.target.value)} /></label>
      <Button type="button" variant="ghost" size="icon" disabled={!athos || busy} aria-label={t("moodleApproval.improve")} title={t("moodleApproval.improve")} onClick={() => setImproveOpen(true)}><Sparkles className="h-4 w-4" /></Button>
    </>}
    {outcome === "error" && <p role="alert" className="text-sm text-destructive">{t("moodleApproval.error")}</p>}
    {outcome === "approved" && <p role="status" className="text-sm">{t("moodleApproval.success")}</p>}
    {outcome === "rejected" && <p role="status" className="text-sm">{t("moodleApproval.rejected")}</p>}
    {Boolean(query.data?.activity?.length) && <div className="space-y-2 border-t pt-3">
      <h4 className="font-medium">{t("moodleApproval.activity")}</h4>
      <ul className="space-y-2 text-sm">{query.data?.activity?.map(entry => <li key={entry.message_id} className="rounded border p-3">
        <Link className="underline" to={`/demands?message=${entry.message_id}`}>#{entry.number}</Link>
        <span className="ml-2">{t(`agentTasks.moodleStates.${entry.outcome === "completed" ? "completed" : entry.state}`)}</span>
        {entry.state === "finished" && entry.outcome && entry.outcome !== "completed" && <p>{t(`moodleApproval.outcomes.${entry.outcome}`)}</p>}
        {entry.outcome === "completed" && entry.dispatch_status === "failed" && <p className="mt-1 text-muted-foreground">{t("moodleApproval.reportFailed")}</p>}
      </li>)}</ul>
    </div>}
    {improveOpen && athos && <ImprovePromptDialog initialDraft={instruction} subject={athos.name} agents={agents.data ?? []} includeLocalSlashCommands={false} includeHermesSlashCommands={false} improvePrompt={improvePrompt} onApply={text => { setInstruction(text); setImproveOpen(false); }} onClose={() => setImproveOpen(false)} />}
    <ConfirmDialog open={decision !== null} title={t(rejecting ? "moodleApproval.rejectTitle" : "moodleApproval.confirmTitle")} description={t(rejecting ? "moodleApproval.rejectHint" : "moodleApproval.confirmHint")} confirmLabel={t(rejecting ? "moodleApproval.reject" : "moodleApproval.approve")} variant={rejecting || decision?.items.some(item => item.destructive) ? "destructive" : "default"} loading={busy} dismissDisabled={busy} onConfirm={() => void decide()} onCancel={() => { if (!busy) setDecision(null); }}>
      <ul className="max-h-64 space-y-2 overflow-auto text-sm">{(decision?.items ?? []).map(item => <li key={item.request_id}>#{item.number} · {item.summary} · {item.operation} · {item.environment} · {item.destructive ? t("moodleApproval.destructive") : t("moodleApproval.nonDestructive")}<p className="break-all">{t("moodleApproval.host")}: {item.host}</p>{item.batch ? <BatchDetails batch={item.batch} /> : <pre className="whitespace-pre-wrap break-all">{t("moodleApproval.params")}: {JSON.stringify(item.params, null, 2)}</pre>}</li>)}</ul>
      {!rejecting && <p className="mt-2 text-sm">{t("moodleApproval.executor")}: {(agents.data ?? []).find(agent => agent.id === agentId)?.name}</p>}
      {!rejecting && instruction && <p className="mt-2 whitespace-pre-wrap break-words text-sm">{t("moodleApproval.instruction")}: {instruction}</p>}
      {rejecting && <label className="mt-2 block space-y-1 text-sm">{t("moodleApproval.reason")}<Textarea className="resize-none" rows={2} maxLength={1000} value={reason} disabled={busy} onChange={e => setReason(e.target.value)} /></label>}
    </ConfirmDialog>
  </section>;
}
