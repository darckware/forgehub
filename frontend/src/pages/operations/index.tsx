import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { z } from "zod";
import { Bot, Loader2, Play, Plus, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/store/authStore";
import {
  type Charter,
  type OperationsChange,
  type OperationsTab,
  type Routine,
  type RoutineInput,
  useOperationsViewModel,
} from "@/hooks/useOperationsViewModel";

const TABS: OperationsTab[] = ["agents", "schedule", "runs", "improvements", "questions", "instructions", "evolution"];
const routineSchema = z.object({
  agent_id: z.string().min(1),
  title: z.string().trim().min(1).max(200),
  instructions: z.string().trim().min(1),
  schedule: z.string().trim().min(9),
  timezone: z.string().trim().min(1),
  kind: z.enum(["monitoring", "maintenance", "improvement", "report", "coordination"]),
  expected_evidence: z.string(),
  linked_audit_checks: z.string(),
  enabled: z.boolean(),
  priority: z.number().min(-10).max(10),
  deadline_minutes: z.number().min(5).max(1440),
});
type RoutineForm = z.infer<typeof routineSchema>;
const charterSchema = z.object({
  mission: z.string().trim().min(1),
  responsibilities: z.string(),
  monitored_domains: z.string(),
  coordinates_with: z.string(),
  never_does: z.string(),
  daily_run_budget: z.number().min(0).max(500),
  daily_cost_budget: z.number().min(0).max(1000),
  escalation: z.enum(["telegram_direct", "via_athos"]),
});
type CharterForm = z.infer<typeof charterSchema>;
const lines = (value: string) => value.split("\n").map((v) => v.trim()).filter(Boolean);

function StatusBlock({ loading, error, retry, children }: {
  loading: boolean; error: boolean; retry: () => void; children: React.ReactNode;
}) {
  const { t } = useTranslation("operations");
  if (loading) return <p role="status" className="flex items-center gap-2 rounded-md border p-5 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 motion-safe:animate-spin" />{t("loading")}</p>;
  if (error) return <div role="alert" className="rounded-md border border-destructive/40 p-5"><p>{t("loadError")}</p><Button className="mt-3" variant="outline" onClick={retry}>{t("retry")}</Button></div>;
  return <>{children}</>;
}

function CharterEditor({ agentId, charter, save, pending, onClose }: {
  agentId: string; charter?: Charter; save: (data: CharterForm) => void; pending: boolean; onClose: () => void;
}) {
  const { t } = useTranslation("operations");
  const { register, handleSubmit, formState: { errors } } = useForm<CharterForm>({
    resolver: zodResolver(charterSchema),
    defaultValues: {
      mission: charter?.mission ?? "",
      responsibilities: charter?.responsibilities.join("\n") ?? "",
      monitored_domains: charter?.monitored_domains.join("\n") ?? "",
      coordinates_with: charter?.coordinates_with.map((v) => `${v.agent}: ${v.purpose}`).join("\n") ?? "",
      never_does: charter?.never_does.join("\n") ?? "",
      daily_run_budget: charter?.daily_run_budget ?? 24,
      daily_cost_budget: Number(charter?.daily_cost_budget ?? 2),
      escalation: charter?.escalation ?? "via_athos",
    },
  });
  return <form noValidate aria-label={t("charterEditor")} onSubmit={handleSubmit(save)} className="space-y-4 rounded-md border border-primary/30 bg-muted/20 p-4">
    <input type="hidden" value={agentId} readOnly />
    <div><label className="mb-1 block text-sm font-medium" htmlFor="charter-mission">{t("mission")}</label><Input id="charter-mission" {...register("mission")} aria-invalid={!!errors.mission} />{errors.mission && <p className="text-xs text-destructive">{t("required")}</p>}</div>
    <div className="grid gap-3 md:grid-cols-2">
      {(["responsibilities", "monitored_domains", "coordinates_with", "never_does"] as const).map((field) => <div key={field}>
        <label className="mb-1 block text-sm font-medium" htmlFor={`charter-${field}`}>{t(field)}</label>
        <Textarea id={`charter-${field}`} rows={4} className="resize-none" {...register(field)} />
        <p className="mt-1 text-xs text-muted-foreground">{t(field === "coordinates_with" ? "coordinationHint" : "onePerLine")}</p>
      </div>)}
    </div>
    <div className="grid gap-3 sm:grid-cols-3">
      <div><label className="mb-1 block text-sm" htmlFor="run-budget">{t("dailyRunBudget")}</label><Input id="run-budget" type="number" min={0} max={500} {...register("daily_run_budget", { valueAsNumber: true })} aria-invalid={!!errors.daily_run_budget} /></div>
      <div><label className="mb-1 block text-sm" htmlFor="cost-budget">{t("dailyCostBudget")}</label><Input id="cost-budget" type="number" min={0} max={1000} step="0.01" {...register("daily_cost_budget", { valueAsNumber: true })} aria-invalid={!!errors.daily_cost_budget} /></div>
      <div><label className="mb-1 block text-sm" htmlFor="escalation">{t("escalation")}</label><Select id="escalation" {...register("escalation")}><option value="via_athos">{t("viaAthos")}</option><option value="telegram_direct">{t("telegramDirect")}</option></Select></div>
    </div>
    <div className="flex gap-2"><Button type="submit" disabled={pending}>{pending ? t("saving") : t("saveCharter")}</Button><Button type="button" variant="outline" onClick={onClose}>{t("cancel")}</Button></div>
  </form>;
}

function RoutineEditor({ routine, agents, save, pending, onClose }: {
  routine?: Routine; agents: Array<{ agent_id: string; agent_name: string }>;
  save: (data: RoutineInput) => void; pending: boolean; onClose: () => void;
}) {
  const { t } = useTranslation("operations");
  const { register, handleSubmit, formState: { errors } } = useForm<RoutineForm>({
    resolver: zodResolver(routineSchema),
    defaultValues: {
      agent_id: routine?.agent_id ?? agents[0]?.agent_id ?? "",
      title: routine?.title ?? "", instructions: routine?.instructions ?? "",
      schedule: routine?.schedule ?? "0 9 * * *", timezone: routine?.timezone ?? "America/Sao_Paulo",
      kind: routine?.kind ?? "monitoring", expected_evidence: routine?.expected_evidence ?? "",
      linked_audit_checks: routine?.linked_audit_checks.join(", ") ?? "",
      enabled: routine?.enabled ?? true, priority: routine?.priority ?? 0,
      deadline_minutes: routine?.deadline_minutes ?? 60,
    },
  });
  const submit = (value: RoutineForm) => save({ ...value,
    expected_evidence: value.expected_evidence.trim() || null,
    linked_audit_checks: value.linked_audit_checks.split(",").map((v) => v.trim()).filter(Boolean),
  });
  return <form noValidate aria-label={t("routineEditor")} onSubmit={handleSubmit(submit)} className="space-y-4 rounded-md border border-primary/30 bg-muted/20 p-4">
    <div className="grid gap-3 md:grid-cols-2">
      <div><label className="mb-1 block text-sm" htmlFor="routine-agent">{t("agent")}</label><Select id="routine-agent" {...register("agent_id")} disabled={!!routine}>{agents.map((a) => <option key={a.agent_id} value={a.agent_id}>{a.agent_name}</option>)}</Select></div>
      <div><label className="mb-1 block text-sm" htmlFor="routine-kind">{t("kind")}</label><Select id="routine-kind" {...register("kind")}>{(["monitoring", "maintenance", "improvement", "report", "coordination"] as const).map((kind) => <option key={kind} value={kind}>{t(`kinds.${kind}`)}</option>)}</Select></div>
      <div><label className="mb-1 block text-sm" htmlFor="routine-title">{t("routineTitle")}</label><Input id="routine-title" {...register("title")} aria-invalid={!!errors.title} /></div>
      <div><label className="mb-1 block text-sm" htmlFor="routine-schedule">{t("cronSchedule")}</label><Input id="routine-schedule" className="font-mono" {...register("schedule")} aria-invalid={!!errors.schedule} /><p className="mt-1 text-xs text-muted-foreground">{t("cronHint")}</p></div>
      <div><label className="mb-1 block text-sm" htmlFor="routine-timezone">{t("timezone")}</label><Input id="routine-timezone" {...register("timezone")} aria-invalid={!!errors.timezone} /></div>
      <div><label className="mb-1 block text-sm" htmlFor="routine-deadline">{t("deadlineMinutes")}</label><Input id="routine-deadline" type="number" min={5} max={1440} {...register("deadline_minutes", { valueAsNumber: true })} aria-invalid={!!errors.deadline_minutes} /></div>
    </div>
    <div><label className="mb-1 block text-sm" htmlFor="routine-instructions">{t("instructions")}</label><Textarea id="routine-instructions" rows={5} className="resize-none" {...register("instructions")} aria-invalid={!!errors.instructions} /></div>
    <div><label className="mb-1 block text-sm" htmlFor="routine-evidence">{t("expectedEvidence")}</label><Textarea id="routine-evidence" rows={3} className="resize-none" {...register("expected_evidence")} /></div>
    <div><label className="mb-1 block text-sm" htmlFor="routine-checks">{t("linkedChecks")}</label><Input id="routine-checks" {...register("linked_audit_checks")} /></div>
    <div className="flex gap-4"><label className="flex items-center gap-2 text-sm"><input type="checkbox" {...register("enabled")} />{t("enabled")}</label><div><label className="mr-2 text-sm" htmlFor="routine-priority">{t("priority")}</label><Input id="routine-priority" type="number" min={-10} max={10} className="inline-block w-20" {...register("priority", { valueAsNumber: true })} /></div></div>
    {Object.keys(errors).length > 0 && <p role="alert" className="text-sm text-destructive">{t("formError")}</p>}
    <div className="flex gap-2"><Button type="submit" disabled={pending}>{pending ? t("saving") : t("saveRoutine")}</Button><Button type="button" variant="outline" onClick={onClose}>{t("cancel")}</Button></div>
  </form>;
}

export default function OperationsPage() {
  const { t, i18n } = useTranslation("operations");
  const isAdmin = useAuthStore((s) => s.user?.is_admin ?? false);
  const [tab, setTab] = useState<OperationsTab>("agents");
  const vm = useOperationsViewModel(tab);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [editingRoutine, setEditingRoutine] = useState<Routine | "new" | null>(null);
  const [confirmRun, setConfirmRun] = useState<Routine | null>(null);
  const [questionAnswer, setQuestionAnswer] = useState<Record<string, string>>({});
  const [confirmQuestion, setConfirmQuestion] = useState<string | null>(null);
  const [confirmCancelQuestion, setConfirmCancelQuestion] = useState<string | null>(null);
  const [policyText, setPolicyText] = useState<string | null>(null);
  const [policyReason, setPolicyReason] = useState("");
  const [confirmPolicy, setConfirmPolicy] = useState(false);
  const [confirmUndo, setConfirmUndo] = useState<OperationsChange | null>(null);
  const [agentFilter, setAgentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => { document.title = `${t("title")} · ForgeHub`; }, [t]);
  const date = (value: string | null | undefined) => value ? new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "—";
  const trendDate = (value: string) => new Intl.DateTimeFormat(i18n.language, { day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`));
  const cost = (value: number) => new Intl.NumberFormat(i18n.language, { style: "currency", currency: "USD" }).format(value);
  const metric = (value: number | string | null) => value === null ? "—" : String(value);
  const agents = vm.overview.data?.agents ?? [];
  const charters = vm.charters.data ?? [];
  const routines = vm.routines.data ?? [];
  const selectedCharter = charters.find((c) => c.agent_id === agentId);
  const sortedRoutines = useMemo(() => [...routines].sort((a, b) => (a.next_occurrences[0] ?? "z").localeCompare(b.next_occurrences[0] ?? "z")), [routines]);
  const previewDays = useMemo(() => Array.from({ length: 7 }, (_, index) => {
    const value = new Date(Date.now() + index * 86_400_000);
    return {
      key: new Intl.DateTimeFormat("sv-SE", { timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit" }).format(value),
      label: new Intl.DateTimeFormat(i18n.language, { timeZone: "America/Sao_Paulo", weekday: "short", day: "2-digit", month: "2-digit" }).format(value),
    };
  }), [i18n.language]);
  const filteredRuns = (vm.runs.data ?? []).filter((run) => (!agentFilter || run.agent_id === agentFilter) && (!statusFilter || run.status === statusFilter));
  const error = vm.saveCharter.error ?? vm.saveRoutine.error ?? vm.runNow.error ?? vm.answerQuestion.error ?? vm.cancelQuestion.error ?? vm.publishPolicy.error ?? vm.undoChange.error;

  return <div className="space-y-5 max-md:break-words">
    <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div><div className="flex items-center gap-2"><Bot className="h-7 w-7 text-primary" aria-hidden="true" /><h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1></div><p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p></div>
      <Button variant="outline" onClick={() => vm.refresh()} className="self-start gap-2"><RefreshCw className="h-4 w-4" />{t("refresh")}</Button>
    </header>
    {notice && <p role="status" className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">{notice}</p>}
    {error && <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">{error.message}</p>}
    <Tabs value={tab} onValueChange={(value) => { setTab(value as OperationsTab); setNotice(""); }}>
      <TabsList className="w-full justify-start">{TABS.map((value) => <TabsTrigger key={value} value={value}>{t(`tabs.${value}`)}</TabsTrigger>)}</TabsList>
      <TabsContent value="agents" className="mt-5 space-y-4">
        <StatusBlock loading={vm.overview.isLoading || vm.charters.isLoading} error={vm.overview.isError || vm.charters.isError} retry={() => { void vm.overview.refetch(); void vm.charters.refetch(); }}>
          <p className="text-sm text-muted-foreground">{t("agentsHint")}</p>
          {agents.length === 0 ? <p className="rounded-md border p-5 text-sm text-muted-foreground">{t("noAgents")}</p> : <div className="overflow-x-auto rounded-md border"><Table><TableHeader><TableRow><TableHead>{t("agent")}</TableHead><TableHead>{t("today")}</TableHead><TableHead>{t("routines")}</TableHead><TableHead>{t("budget")}</TableHead><TableHead>{t("charter")}</TableHead></TableRow></TableHeader><TableBody>{agents.map((agent) => <TableRow key={agent.agent_id}>
            <TableCell><button type="button" className="text-left font-medium hover:underline" onClick={() => setAgentId(agentId === agent.agent_id ? null : agent.agent_id)} aria-expanded={agentId === agent.agent_id}>{agent.agent_name}</button><p className="font-mono text-xs text-muted-foreground">{agent.profile_slug ?? agent.runtime_type ?? "—"}</p></TableCell>
            <TableCell><span className="block whitespace-nowrap text-emerald-500">{agent.today.completed ?? 0} {t("done")}</span><span className="block whitespace-nowrap text-destructive">{agent.today.failed ?? 0} {t("failed")}</span><span className="block whitespace-nowrap text-amber-500">{agent.today.missed ?? 0} {t("missed")}</span></TableCell>
            <TableCell>{agent.routines_enabled}/{agent.routines_total}</TableCell><TableCell>{agent.runs_counted_today}/{agent.daily_run_budget ?? "—"}</TableCell>
            <TableCell><Badge variant={agent.has_charter ? "success" : "warning"}>{agent.has_charter ? t("configured") : t("missing")}</Badge></TableCell>
          </TableRow>)}</TableBody></Table></div>}
          {agentId && <div className="space-y-3 rounded-md border p-4"><div className="flex items-center justify-between"><h2 className="font-semibold">{agents.find((a) => a.agent_id === agentId)?.agent_name}</h2><Button variant="ghost" onClick={() => setAgentId(null)}>{t("close")}</Button></div>
            {selectedCharter && <div className="grid gap-3 text-sm sm:grid-cols-2"><p><strong>{t("mission")}:</strong> {selectedCharter.mission}</p><p><strong>{t("ownedChecks")}:</strong> {selectedCharter.owned_audit_checks.join(", ") || "—"}</p></div>}
            <p className="text-sm text-muted-foreground">{t("agentRoutineCount", { count: routines.filter((r) => r.agent_id === agentId).length })}</p>
            {isAdmin && <CharterEditor key={agentId} agentId={agentId} charter={selectedCharter} pending={vm.saveCharter.isPending} onClose={() => setAgentId(null)} save={(data) => vm.saveCharter.mutate({ agentId, data: { ...data,
              responsibilities: lines(data.responsibilities), monitored_domains: lines(data.monitored_domains), never_does: lines(data.never_does),
              coordinates_with: lines(data.coordinates_with).map((line) => { const [agent, ...purpose] = line.split(":"); return { agent: agent.trim(), purpose: purpose.join(":").trim() }; }).filter((v) => v.agent && v.purpose),
            } }, { onSuccess: () => { setNotice(t("charterSaved")); setAgentId(null); } })} />}</div>}
        </StatusBlock>
      </TabsContent>
      <TabsContent value="schedule" className="mt-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm text-muted-foreground">{t("scheduleHint")}</p>{isAdmin && <Button onClick={() => setEditingRoutine("new")} className="gap-2"><Plus className="h-4 w-4" />{t("newRoutine")}</Button>}</div>
        {editingRoutine && <RoutineEditor key={editingRoutine === "new" ? "new" : editingRoutine.id} routine={editingRoutine === "new" ? undefined : editingRoutine} agents={agents} pending={vm.saveRoutine.isPending} onClose={() => setEditingRoutine(null)} save={(data) => vm.saveRoutine.mutate({ id: editingRoutine === "new" ? undefined : editingRoutine.id, data }, { onSuccess: () => { setEditingRoutine(null); setNotice(t("routineSaved")); } })} />}
        <StatusBlock loading={vm.routines.isLoading || vm.overview.isLoading} error={vm.routines.isError || vm.overview.isError} retry={() => { void vm.routines.refetch(); void vm.overview.refetch(); }}>
          {sortedRoutines.length > 0 && <section className="space-y-2"><h2 className="text-sm font-semibold">{t("weekPreview")}</h2><div className="overflow-x-auto rounded-md border"><Table><TableHeader><TableRow><TableHead className="min-w-32">{t("agent")}</TableHead>{previewDays.map((day) => <TableHead key={day.key} className="min-w-28 whitespace-nowrap">{day.label}</TableHead>)}</TableRow></TableHeader><TableBody>{agents.map((agent) => <TableRow key={agent.agent_id}><TableCell className="font-medium">{agent.agent_name}</TableCell>{previewDays.map((day) => <TableCell key={day.key} className="align-top">{sortedRoutines.filter((routine) => routine.enabled && routine.agent_id === agent.agent_id).flatMap((routine) => routine.next_occurrences.filter((value) => new Intl.DateTimeFormat("sv-SE", { timeZone: routine.timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value)) === day.key).map((value) => <div key={`${routine.id}-${value}`} className="mb-1 rounded bg-muted px-2 py-1 text-xs" title={routine.title}><span className="font-mono">{new Intl.DateTimeFormat(i18n.language, { timeZone: routine.timezone, hour: "2-digit", minute: "2-digit" }).format(new Date(value))}</span><span className="ml-1 line-clamp-2">{routine.title}</span></div>))}</TableCell>)}</TableRow>)}</TableBody></Table></div></section>}
          {sortedRoutines.length === 0 ? <p className="rounded-md border p-5 text-sm text-muted-foreground">{t("noRoutines")}</p> : <div className="overflow-x-auto rounded-md border"><Table><TableHeader><TableRow><TableHead>{t("nextRun")}</TableHead><TableHead>{t("agent")}</TableHead><TableHead>{t("routineTitle")}</TableHead><TableHead>{t("cronSchedule")}</TableHead><TableHead>{t("status")}</TableHead><TableHead>{t("actions")}</TableHead></TableRow></TableHeader><TableBody>{sortedRoutines.map((routine) => <TableRow key={routine.id}>
            <TableCell className="whitespace-nowrap">{date(routine.next_occurrences[0])}</TableCell><TableCell>{routine.agent_name ?? agents.find((a) => a.agent_id === routine.agent_id)?.agent_name ?? "—"}</TableCell><TableCell><p className="font-medium">{routine.title}</p><p className="max-w-xs truncate text-xs text-muted-foreground" title={routine.expected_evidence ?? ""}>{routine.expected_evidence}</p></TableCell><TableCell className="font-mono text-xs">{routine.schedule}</TableCell><TableCell><Badge variant={routine.enabled ? "success" : "outline"}>{routine.enabled ? t("enabled") : t("paused")}</Badge></TableCell>
            <TableCell><div className="flex flex-wrap gap-1">{isAdmin && <><Button size="sm" variant="outline" aria-label={`${t("runNow")} ${routine.title}`} onClick={() => setConfirmRun(routine)}><Play className="h-3.5 w-3.5" /></Button><Button size="sm" variant="outline" onClick={() => setEditingRoutine(routine)}>{t("edit")}</Button><Button size="sm" variant="outline" onClick={() => vm.saveRoutine.mutate({ id: routine.id, data: { ...routine, enabled: !routine.enabled } }, { onSuccess: () => setNotice(t("routineSaved")) })}>{routine.enabled ? t("pause") : t("resume")}</Button><Button size="sm" variant="outline" onClick={() => setEditingRoutine({ ...routine, id: "" })}>{t("duplicate")}</Button></>}</div></TableCell>
          </TableRow>)}</TableBody></Table></div>}
        </StatusBlock>
      </TabsContent>
      <TabsContent value="runs" className="mt-5 space-y-4">
        <div className="grid gap-3 sm:grid-cols-2"><div><label className="mb-1 block text-sm" htmlFor="run-agent-filter">{t("agent")}</label><Select id="run-agent-filter" value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}><option value="">{t("allAgents")}</option>{agents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.agent_name}</option>)}</Select></div><div><label className="mb-1 block text-sm" htmlFor="run-status-filter">{t("status")}</label><Select id="run-status-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">{t("allStatuses")}</option>{["scheduled", "completed", "failed", "missed", "skipped_budget"].map((status) => <option key={status} value={status}>{t(`runStatus.${status}`)}</option>)}</Select></div></div>
        <StatusBlock loading={vm.runs.isLoading} error={vm.runs.isError} retry={() => void vm.runs.refetch()}>{filteredRuns.length === 0 ? <p className="rounded-md border p-5 text-sm text-muted-foreground">{t("noRuns")}</p> : <div className="overflow-x-auto rounded-md border"><Table><TableHeader><TableRow><TableHead>{t("when")}</TableHead><TableHead>{t("agent")}</TableHead><TableHead>{t("routineTitle")}</TableHead><TableHead>{t("status")}</TableHead><TableHead>{t("evidence")}</TableHead></TableRow></TableHeader><TableBody>{filteredRuns.map((run) => <TableRow key={run.id}><TableCell className="whitespace-nowrap">{date(run.occurrence_at)}</TableCell><TableCell>{run.agent_name ?? "—"}</TableCell><TableCell>{run.routine_title ?? "—"}</TableCell><TableCell><Badge variant={run.status === "completed" ? "success" : run.status === "failed" || run.overdue ? "destructive" : "outline"}>{t(`runStatus.${run.status}`, { defaultValue: run.status })}</Badge></TableCell><TableCell><p className="max-w-sm whitespace-pre-wrap text-xs">{run.detail ?? "—"}</p>{run.demand_number && <Link className="text-xs text-primary underline" to="/demands">{t("messageNumber", { number: run.demand_number })}</Link>}</TableCell></TableRow>)}</TableBody></Table></div>}</StatusBlock>
      </TabsContent>
      <TabsContent value="improvements" className="mt-5 space-y-4"><p className="text-sm text-muted-foreground">{t("improvementsHint")}</p><StatusBlock loading={vm.improvements.isLoading} error={vm.improvements.isError} retry={() => void vm.improvements.refetch()}>{(vm.improvements.data ?? []).length === 0 ? <p className="rounded-md border p-5 text-sm text-muted-foreground">{t("noImprovements")}</p> : <div className="overflow-x-auto rounded-md border"><Table><TableHeader><TableRow><TableHead>#</TableHead><TableHead>{t("improvement")}</TableHead><TableHead>{t("status")}</TableHead><TableHead>{t("maturesAt")}</TableHead></TableRow></TableHeader><TableBody>{vm.improvements.data?.map((item) => <TableRow key={item.id}><TableCell>{item.number}</TableCell><TableCell><Link to="/demands" className="font-medium text-primary underline">{item.subject}</Link><p className="max-w-lg truncate text-xs text-muted-foreground">{item.body}</p></TableCell><TableCell><Badge variant="outline">{item.incubation_state ?? "—"}</Badge></TableCell><TableCell>{date(item.matures_at)}</TableCell></TableRow>)}</TableBody></Table></div>}</StatusBlock></TabsContent>
      <TabsContent value="questions" className="mt-5 space-y-4"><p className="text-sm text-muted-foreground">{t("questionsHint")}</p><StatusBlock loading={vm.questions.isLoading} error={vm.questions.isError} retry={() => void vm.questions.refetch()}>{(vm.questions.data ?? []).length === 0 ? <p className="rounded-md border p-5 text-sm text-muted-foreground">{t("noQuestions")}</p> : <div className="space-y-3">{vm.questions.data?.map((question) => <section key={question.id} className="rounded-md border p-4"><div className="flex flex-wrap items-center gap-2"><h2 className="font-medium">#{question.number} · {question.agent_name ?? "—"}</h2><Badge variant={question.status === "pending" ? "warning" : "outline"}>{t(`questionStatus.${question.status}`, { defaultValue: question.status })}</Badge>{question.blocking && <Badge variant="destructive">{t("blocking")}</Badge>}</div><p className="mt-2 whitespace-pre-wrap text-sm">{question.question}</p>{question.context && <p className="mt-2 whitespace-pre-wrap text-xs text-muted-foreground">{question.context}</p>}{question.recommendation && <p className="mt-2 text-xs"><strong>{t("recommendation")}:</strong> {question.recommendation}</p>}{question.answer && <p className="mt-3 rounded-md bg-muted p-3 text-sm"><strong>{t("answer")}:</strong> {question.answer}</p>}{question.status === "pending" && isAdmin && <div className="mt-3 space-y-2"><label className="text-sm" htmlFor={`answer-${question.id}`}>{t("answer")}</label><Textarea id={`answer-${question.id}`} rows={3} className="resize-none" value={questionAnswer[question.id] ?? ""} onChange={(e) => setQuestionAnswer((old) => ({ ...old, [question.id]: e.target.value }))} /><div className="flex gap-2"><Button disabled={!questionAnswer[question.id]?.trim()} onClick={() => setConfirmQuestion(question.id)}>{t("sendAnswer")}</Button><Button variant="outline" onClick={() => setConfirmCancelQuestion(question.id)}>{t("cancelQuestion")}</Button></div></div>}</section>)}</div>}</StatusBlock></TabsContent>
      <TabsContent value="instructions" className="mt-5 space-y-4"><StatusBlock loading={vm.policy.isLoading} error={vm.policy.isError} retry={() => void vm.policy.refetch()}><p className="text-sm text-muted-foreground">{t("policyHint")}</p><p className="text-xs text-muted-foreground">{t("policyVersion", { version: vm.policy.data?.version ?? "—" })}</p>{isAdmin ? <div className="space-y-3"><label className="block text-sm" htmlFor="policy-content">{t("policyContent")}</label><Textarea id="policy-content" rows={14} className="resize-none font-mono text-xs" value={policyText ?? vm.policy.data?.content ?? ""} onChange={(e) => setPolicyText(e.target.value)} /><label className="block text-sm" htmlFor="policy-reason">{t("changeReason")}</label><Input id="policy-reason" value={policyReason} onChange={(e) => setPolicyReason(e.target.value)} /><Button disabled={!(policyText ?? "").trim() || policyText === vm.policy.data?.content} onClick={() => setConfirmPolicy(true)}>{t("publishPolicy")}</Button></div> : <pre className="whitespace-pre-wrap rounded-md border p-4 text-sm">{vm.policy.data?.content ?? t("noPolicy")}</pre>}
        <h2 className="pt-3 font-semibold">{t("history")}</h2>{(vm.policyVersions.data ?? []).map((version) => <div key={version.id} className="flex flex-wrap items-center gap-2 rounded-md border p-3 text-sm"><span>v{version.version}</span><span className="text-muted-foreground">{date(version.created_at)} · {version.author}</span><span>{version.change_reason}</span>{isAdmin && version.id !== vm.policy.data?.id && <Button size="sm" variant="outline" onClick={() => { setPolicyText(version.content); setPolicyReason(t("restoreReason", { version: version.version })); }}>{t("restore")}</Button>}</div>)}</StatusBlock></TabsContent>
      <TabsContent value="evolution" className="mt-5 space-y-6">
        <StatusBlock loading={vm.evolution.isLoading} error={vm.evolution.isError} retry={() => void vm.evolution.refetch()}>
          <section className="space-y-3" aria-label={t("evolutionChanges")}>
            <div><h2 className="text-lg font-semibold">{t("evolutionChanges")}</h2><p className="text-sm text-muted-foreground">{t("evolutionHint")}</p></div>
            {(vm.evolution.data?.changes ?? []).length === 0 ? <p className="rounded-md border p-5 text-sm text-muted-foreground">{t("noChanges")}</p> :
              <div className="grid gap-3">{vm.evolution.data?.changes.map((change) => <article key={change.id} className="rounded-md border bg-card p-4">
                <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0 flex-1"><h3 className="font-medium">{change.summary}</h3><p className="mt-1 text-sm text-muted-foreground">{change.rationale}</p></div><div className="flex gap-2"><Badge variant="outline">{change.autonomy_level}</Badge><Badge variant={change.status === "reverted" ? "destructive" : change.status === "kept" ? "success" : "outline"}>{t(`changeStatus.${change.status}`)}</Badge></div></div>
                <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-t pt-3 text-xs text-muted-foreground"><span>{t("changeTarget")}: {change.target_type} · {change.target_id}</span><span>{t("when")}: {date(change.created_at)}</span>{change.evaluation_ends_at && <span>{t("evaluationEnds")}: {date(change.evaluation_ends_at)}</span>}</div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-sm"><span className="text-muted-foreground">{change.metric_name ?? t("metric")}:</span> <span className="font-medium tabular-nums">{metric(change.before_value)} → {metric(change.after_value)}</span></p>{isAdmin && (change.status === "evaluating" || change.status === "kept") && <Button size="sm" variant="outline" onClick={() => setConfirmUndo(change)}>{t("undoChange")} <span className="sr-only">{change.summary}</span></Button>}</div>
              </article>)}</div>}
          </section>
          <section className="space-y-3" aria-label={t("weeklyTrend")}><h2 className="text-lg font-semibold">{t("weeklyTrend")}</h2>
            {(vm.evolution.data?.trend ?? []).length === 0 ? <p className="rounded-md border p-5 text-sm text-muted-foreground">{t("noTrend")}</p> : <div className="overflow-x-auto rounded-md border"><Table><TableHeader><TableRow><TableHead>{t("day")}</TableHead><TableHead>{t("trendCompleted")}</TableHead><TableHead>{t("trendAuditOk")}</TableHead><TableHead>{t("trendFailures")}</TableHead><TableHead>{t("trendCost")}</TableHead><TableHead>{t("trendImprovements")}</TableHead></TableRow></TableHeader><TableBody>{vm.evolution.data?.trend.map((day) => <TableRow key={day.date}><TableCell className="whitespace-nowrap font-medium">{trendDate(day.date)}</TableCell><TableCell>{day.routines_completed}</TableCell><TableCell>{day.audit_ok}</TableCell><TableCell><span className="text-destructive">{day.routines_failed + day.audit_failed}</span><span className="block text-xs text-muted-foreground">{t("trendFailureDetail", { routines: day.routines_failed, checks: day.audit_failed })}</span></TableCell><TableCell className="whitespace-nowrap tabular-nums">{cost(day.cost_usd)}</TableCell><TableCell>{day.improvements_delivered}</TableCell></TableRow>)}</TableBody></Table></div>}
          </section>
        </StatusBlock>
      </TabsContent>
    </Tabs>
    <ConfirmDialog open={!!confirmRun} title={t("confirmRunTitle")} description={t("confirmRunDescription", { title: confirmRun?.title })} confirmLabel={t("confirmRun")} variant="default" loading={vm.runNow.isPending} onCancel={() => setConfirmRun(null)} onConfirm={() => confirmRun && vm.runNow.mutate(confirmRun.id, { onSuccess: () => { setConfirmRun(null); setNotice(t("runQueued")); } })} />
    <ConfirmDialog open={!!confirmQuestion} title={t("confirmAnswerTitle")} description={t("confirmAnswerDescription")} confirmLabel={t("confirmAnswer")} variant="default" loading={vm.answerQuestion.isPending} onCancel={() => setConfirmQuestion(null)} onConfirm={() => confirmQuestion && vm.answerQuestion.mutate({ id: confirmQuestion, answer: questionAnswer[confirmQuestion].trim() }, { onSuccess: () => { setConfirmQuestion(null); setNotice(t("answerSent")); } })} />
    <ConfirmDialog open={!!confirmCancelQuestion} title={t("confirmCancelQuestionTitle")} description={t("confirmCancelQuestionDescription")} confirmLabel={t("cancelQuestion")} loading={vm.cancelQuestion.isPending} onCancel={() => setConfirmCancelQuestion(null)} onConfirm={() => confirmCancelQuestion && vm.cancelQuestion.mutate(confirmCancelQuestion, { onSuccess: () => { setConfirmCancelQuestion(null); setNotice(t("questionCancelled")); } })} />
    <ConfirmDialog open={confirmPolicy} title={t("confirmPolicyTitle")} description={t("confirmPolicyDescription")} confirmLabel={t("publishPolicy")} variant="default" loading={vm.publishPolicy.isPending} onCancel={() => setConfirmPolicy(false)} onConfirm={() => vm.publishPolicy.mutate({ content: (policyText ?? "").trim(), change_reason: policyReason.trim() || null }, { onSuccess: () => { setConfirmPolicy(false); setPolicyText(null); setPolicyReason(""); setNotice(t("policyPublished")); } })} />
    <ConfirmDialog open={!!confirmUndo} title={t("confirmUndoTitle")} description={t("confirmUndoDescription", { summary: confirmUndo?.summary })} confirmLabel={t("confirmUndo")} loading={vm.undoChange.isPending} onCancel={() => setConfirmUndo(null)} onConfirm={() => confirmUndo && vm.undoChange.mutate(confirmUndo.id, { onSuccess: () => { setConfirmUndo(null); setNotice(t("changeUndone")); } })} />
  </div>;
}
