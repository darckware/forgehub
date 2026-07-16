import { useState } from "react";
import {
  AlertCircle,
  Bot,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Loader2,
  Pencil,
  Play,
  PlayCircle,
  Plus,
  Power,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useAuditChecks,
  useAuditRuns,
  useAuditStatus,
  useCreateAuditCheck,
  useDeleteAuditCheck,
  useRunAllAuditChecks,
  useRunAuditCheck,
  useUpdateAuditCheck,
  type AuditCheck,
  type AuditCheckInput,
} from "@/hooks/useAudit";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { useAssistantStore } from "@/store/assistantStore";

const RUN_STATUS_BADGE: Record<string, { variant: "success" | "destructive" | "warning" | "outline"; label: string }> = {
  ok: { variant: "success", label: "✅ OK" },
  fail: { variant: "destructive", label: "❌ Failed" },
  error: { variant: "destructive", label: "⚠️ Error" },
  timeout: { variant: "warning", label: "⏱ Timeout" },
};

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

/** Context attached invisibly to the assistant chat (assistantStore's
 * pendingHiddenContext), mirroring Crons'/Agent Tools' maintenance
 * message: check metadata first, then the command and last result. */
function buildAuditCheckChatMessage(check: AuditCheck): string {
  const lines: string[] = [
    "I need help with this Auditor checkpoint. Please review it and suggest fixes.",
    "",
    `Check: ${check.name}`,
    `Category: ${check.category ?? "—"}`,
    `Responsible agent: ${check.agent_profile}`,
    `Enabled: ${check.enabled ? "yes" : "no"}`,
    `Timeout: ${check.timeout_seconds}s`,
  ];
  if (check.workdir) lines.push(`Directory: ${check.workdir}`);
  if (check.description) lines.push(`Description: ${check.description}`);
  lines.push("", "Command:", "```", check.command, "```");
  if (check.last_run) {
    lines.push(
      "",
      `Last run: ${check.last_run.status} at ${formatTimestamp(check.last_run.created_at)}`,
    );
    if (check.last_run.output) lines.push("```", check.last_run.output, "```");
  }
  return lines.join("\n");
}

/** Create/edit form for one checkpoint. */
function CheckFormModal({ initial, onClose }: { initial: AuditCheck | null; onClose: () => void }) {
  const createCheck = useCreateAuditCheck();
  const updateCheck = useUpdateAuditCheck();
  const pending = createCheck.isPending || updateCheck.isPending;
  const error = (createCheck.error ?? updateCheck.error) as Error | null;
  const [form, setForm] = useState<AuditCheckInput>({
    name: initial?.name ?? "",
    description: initial?.description ?? "",
    category: initial?.category ?? "",
    command: initial?.command ?? "",
    workdir: initial?.workdir ?? "",
    agent_profile: initial?.agent_profile ?? "athos",
    enabled: initial?.enabled ?? true,
    timeout_seconds: initial?.timeout_seconds ?? 55,
  });

  function handleSave() {
    const payload: AuditCheckInput = {
      ...form,
      description: form.description || null,
      category: form.category || null,
      workdir: form.workdir || null,
    };
    if (initial) {
      updateCheck.mutate({ checkId: initial.id, updates: payload }, { onSuccess: onClose });
    } else {
      createCheck.mutate(payload, { onSuccess: onClose });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-xl rounded-lg border border-border bg-card" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="font-semibold">{initial ? `Edit check: ${initial.name}` : "New check"}</h3>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="space-y-4 p-4">
          {error && <p className="text-sm text-destructive">{error.message}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Name</label>
              <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Category</label>
              <Input
                value={form.category ?? ""}
                placeholder="infra, cron, kanboard…"
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Responsible agent</label>
              <Input
                value={form.agent_profile}
                onChange={(e) => setForm((f) => ({ ...f, agent_profile: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Timeout (s, max 55)</label>
              <Input
                type="number"
                min={1}
                max={55}
                value={form.timeout_seconds}
                onChange={(e) => setForm((f) => ({ ...f, timeout_seconds: Number(e.target.value) || 55 }))}
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              Command (bash on the host — exit 0 = OK)
            </label>
            <Textarea
              value={form.command}
              rows={3}
              className="font-mono text-xs"
              onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Directory (optional)</label>
              <Input
                value={form.workdir ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, workdir: e.target.value }))}
              />
            </div>
            <div className="flex items-center gap-2 pt-5">
              <input
                id="check-enabled"
                type="checkbox"
                className="h-4 w-4"
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
              <label htmlFor="check-enabled" className="text-sm">
                Enabled
              </label>
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Description</label>
            <Textarea
              value={form.description ?? ""}
              rows={2}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={pending || !form.name || !form.command}>
              {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Expanded row: latest output + recent history for one check. */
function CheckHistory({ check }: { check: AuditCheck }) {
  const { data: runs, isLoading } = useAuditRuns(check.id);
  return (
    <div className="space-y-2 border-t border-border/60 bg-muted/20 px-4 py-3">
      {check.last_run?.output && (
        <div>
          <p className="mb-1 text-[10px] uppercase text-muted-foreground">Latest output</p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted/50 p-2 text-xs">
            {check.last_run.output}
          </pre>
        </div>
      )}
      <p className="text-[10px] uppercase text-muted-foreground">Recent history</p>
      {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      {runs && runs.length === 0 && <p className="text-xs text-muted-foreground">Never run.</p>}
      {runs?.map((run) => (
        <p key={run.id} className="flex items-center gap-2 text-xs text-muted-foreground">
          <Badge variant={RUN_STATUS_BADGE[run.status]?.variant ?? "outline"} className="text-[10px]">
            {RUN_STATUS_BADGE[run.status]?.label ?? run.status}
          </Badge>
          {formatTimestamp(run.created_at)}
          {run.duration_ms != null && <span>· {(run.duration_ms / 1000).toFixed(1)}s</span>}
          <span>· {run.requested_by === "cron" ? "⏰ cron" : "👤 manual"}</span>
        </p>
      ))}
    </div>
  );
}

export default function AuditorPage() {
  const { data: checks, isLoading, isError, error } = useAuditChecks();
  const { data: status } = useAuditStatus();
  const runAll = useRunAllAuditChecks();
  const runOne = useRunAuditCheck();
  const updateCheck = useUpdateAuditCheck();
  const deleteCheck = useDeleteAuditCheck();
  const [formCheck, setFormCheck] = useState<AuditCheck | "new" | null>(null);
  const [deleting, setDeleting] = useState<AuditCheck | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const setPendingHiddenContext = useAssistantStore((s) => s.setPendingHiddenContext);

  function handleSendToAssistant(check: AuditCheck) {
    setPendingHiddenContext(buildAuditCheckChatMessage(check));
    setAssistantOpen(true);
  }

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col gap-4 p-6">
      {formCheck !== null && (
        <CheckFormModal initial={formCheck === "new" ? null : formCheck} onClose={() => setFormCheck(null)} />
      )}
      <ConfirmDialog
        open={deleting !== null}
        title={`Delete check "${deleting?.name ?? ""}"`}
        description="Removes the checkpoint and its entire run history."
        loading={deleteCheck.isPending}
        onConfirm={() => {
          if (deleting) deleteCheck.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
        onCancel={() => setDeleting(null)}
      />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <ClipboardCheck className="h-5 w-5" /> Auditor
          {status && (
            <span className="flex items-center gap-2 text-sm font-normal">
              <Badge variant="success">✅ {status.ok}</Badge>
              <Badge variant={status.fail > 0 ? "destructive" : "outline"}>❌ {status.fail}</Badge>
              {status.never_ran > 0 && <Badge variant="outline">🕐 {status.never_ran} never run</Badge>}
              <span className="text-xs text-muted-foreground">
                last check: {formatTimestamp(status.last_run_at)}
              </span>
            </span>
          )}
        </h1>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            size="sm"
            className="gap-1.5"
            disabled={runAll.isPending}
            title="Trigger all enabled checks now"
            onClick={() => runAll.mutate()}
          >
            {runAll.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
            Run checklist
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setFormCheck("new")}>
            <Plus className="h-4 w-4" /> New check
          </Button>
          <AssistantToggleButton size="sm" />
        </div>
      </div>

      {runAll.isError && (
        <p className="text-sm text-destructive">Failed to run the checklist: {(runAll.error as Error)?.message}</p>
      )}

      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load checks: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && (checks ?? []).length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
            No checkpoints registered yet. Use "New check" to create the first one.
          </CardContent>
        </Card>
      )}

      {(checks ?? []).length > 0 && (
        <Card className="min-h-0 flex-1 overflow-hidden">
          <CardContent className="h-full overflow-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Check</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last run</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(checks ?? []).map((check) => {
                  const isOpen = expanded.has(check.id);
                  const badge = check.last_run ? RUN_STATUS_BADGE[check.last_run.status] : null;
                  return (
                    <>
                      <TableRow key={check.id} className={!check.enabled ? "opacity-60" : undefined}>
                        <TableCell>
                          <button
                            type="button"
                            className="flex items-start gap-1.5 text-left"
                            onClick={() => toggleExpand(check.id)}
                          >
                            {isOpen ? (
                              <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                            )}
                            <span>
                              <span className="font-medium">{check.name}</span>
                              {check.description && (
                                <p className="max-w-md truncate text-xs text-muted-foreground" title={check.description}>
                                  {check.description}
                                </p>
                              )}
                              <code className="block max-w-md truncate text-[11px] text-muted-foreground" title={check.command}>
                                {check.command}
                              </code>
                            </span>
                          </button>
                        </TableCell>
                        <TableCell>
                          {check.category ? <Badge variant="outline">{check.category}</Badge> : "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">{check.agent_profile}</TableCell>
                        <TableCell>
                          {!check.enabled ? (
                            <Badge variant="outline">Disabled</Badge>
                          ) : badge ? (
                            <Badge variant={badge.variant}>{badge.label}</Badge>
                          ) : (
                            <Badge variant="outline">🕐 Never run</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {formatTimestamp(check.last_run?.created_at)}
                          {check.last_run?.duration_ms != null && (
                            <span className="block text-xs">{(check.last_run.duration_ms / 1000).toFixed(1)}s</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-0.5">
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Run ${check.name}`}
                              title="Run now"
                              disabled={runOne.isPending && runOne.variables === check.id}
                              onClick={() => runOne.mutate(check.id)}
                            >
                              {runOne.isPending && runOne.variables === check.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Play className="h-4 w-4" />
                              )}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Send ${check.name} to the assistant`}
                              title="Open the assistant with this check's data and command as context"
                              onClick={() => handleSendToAssistant(check)}
                            >
                              <Bot className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`${check.enabled ? "Disable" : "Enable"} ${check.name}`}
                              title={check.enabled ? "Disable" : "Enable"}
                              onClick={() =>
                                updateCheck.mutate({ checkId: check.id, updates: { enabled: !check.enabled } })
                              }
                            >
                              <Power className={check.enabled ? "h-4 w-4 text-emerald-600" : "h-4 w-4 text-muted-foreground"} />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Edit ${check.name}`}
                              title="Edit"
                              onClick={() => setFormCheck(check)}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Delete ${check.name}`}
                              title="Delete"
                              className="text-destructive"
                              onClick={() => setDeleting(check)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                      {isOpen && (
                        <TableRow key={`${check.id}-history`}>
                          <TableCell colSpan={6} className="p-0">
                            <CheckHistory check={check} />
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
