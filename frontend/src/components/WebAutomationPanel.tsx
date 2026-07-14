import { useEffect, useState } from "react";
import { Loader2, Pencil, Play, Plus, Save, Trash2, Workflow, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  type WebAutomationAction,
  type WebAutomationRoutine,
  type WebAutomationStep,
  useCreateWebAutomationRoutine,
  useDeleteWebAutomationRoutine,
  useRunWebAutomationRoutine,
  useUpdateWebAutomationRoutine,
  useWebAutomationRoutines,
} from "@/hooks/useWorkspaceBrowser";

const ACTIONS: WebAutomationAction[] = ["navigate", "click", "type", "select", "press", "scroll", "wait", "assert_text"];
const DEFAULT_STEP: WebAutomationStep = { action: "click", selector: "" };

function StepFields({ step, onChange }: { step: WebAutomationStep; onChange: (step: WebAutomationStep) => void }) {
  const needsSelector = ["click", "type", "select", "assert_text"].includes(step.action);
  const needsValue = ["type", "select", "press", "assert_text"].includes(step.action);
  return (
    <>
      {step.action === "navigate" && <Input className="h-8 text-xs" placeholder="https://app.example/path" value={step.url ?? ""} onChange={(e) => onChange({ ...step, url: e.target.value })} />}
      {needsSelector && <Input className="h-8 text-xs" placeholder={step.action === "assert_text" ? "CSS selector (optional)" : "CSS selector, e.g. #username"} value={step.selector ?? ""} onChange={(e) => onChange({ ...step, selector: e.target.value })} />}
      {needsValue && <Input className="h-8 text-xs" placeholder={step.action === "press" ? "Enter, Tab, Escape…" : "Value / expected text"} value={step.value ?? ""} onChange={(e) => onChange({ ...step, value: e.target.value })} />}
      {step.action === "scroll" && <Input className="h-8 text-xs" type="number" placeholder="Pixels (e.g. 600)" value={step.delta_y ?? 500} onChange={(e) => onChange({ ...step, delta_y: Number(e.target.value) })} />}
      {step.action === "wait" && <Input className="h-8 text-xs" type="number" placeholder="Milliseconds" value={step.wait_ms ?? 500} onChange={(e) => onChange({ ...step, wait_ms: Number(e.target.value) })} />}
    </>
  );
}

export function WebAutomationPanel({ productId, productName, onClose }: { productId: string; productName: string; onClose: () => void }) {
  const routines = useWebAutomationRoutines(productId);
  const create = useCreateWebAutomationRoutine();
  const update = useUpdateWebAutomationRoutine();
  const remove = useDeleteWebAutomationRoutine();
  const run = useRunWebAutomationRoutine();
  const [editing, setEditing] = useState<WebAutomationRoutine | "new" | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<WebAutomationStep[]>([{ ...DEFAULT_STEP }]);

  useEffect(() => {
    if (!editing) return;
    setName(editing === "new" ? "" : editing.name);
    setDescription(editing === "new" ? "" : editing.description ?? "");
    setSteps(editing === "new" ? [{ ...DEFAULT_STEP }] : editing.steps.map((step) => ({ ...step })));
  }, [editing]);

  function save() {
    if (!name.trim() || steps.length === 0) return;
    const payload = { product_id: productId, name: name.trim(), description: description.trim() || undefined, steps };
    if (editing === "new") create.mutate(payload, { onSuccess: () => setEditing(null) });
    else if (editing) update.mutate({ id: editing.id, ...payload }, { onSuccess: () => setEditing(null) });
  }

  const saving = create.isPending || update.isPending;
  const mutationError = create.error ?? update.error ?? remove.error ?? run.error;

  return (
    <div className="absolute inset-y-2 right-2 z-20 flex w-[min(620px,calc(100%-1rem))] flex-col rounded-lg border border-border bg-background shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div><p className="flex items-center gap-2 font-semibold"><Workflow className="h-4 w-4" /> Web automations</p><p className="text-xs text-muted-foreground">{productName}</p></div>
        <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {editing ? (
          <div className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2"><Input placeholder="Routine name" value={name} onChange={(e) => setName(e.target.value)} /><Input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} /></div>
            <div className="space-y-2">
              {steps.map((step, index) => (
                <div key={index} className="grid gap-2 rounded-md border p-2 sm:grid-cols-[32px_120px_1fr_32px]">
                  <span className="pt-2 text-center text-xs text-muted-foreground">{index + 1}</span>
                  <Select className="h-8 py-1 text-xs" value={step.action} onChange={(e) => setSteps((current) => current.map((item, i) => i === index ? { action: e.target.value as WebAutomationAction } : item))}>{ACTIONS.map((action) => <option key={action} value={action}>{action}</option>)}</Select>
                  <div className="grid gap-2"><StepFields step={step} onChange={(next) => setSteps((current) => current.map((item, i) => i === index ? next : item))} /></div>
                  <Button variant="ghost" size="icon" className="h-8 w-8" disabled={steps.length === 1} onClick={() => setSteps((current) => current.filter((_, i) => i !== index))}><Trash2 className="h-3.5 w-3.5" /></Button>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() => setSteps((current) => [...current, { ...DEFAULT_STEP }])}><Plus className="mr-1 h-3.5 w-3.5" /> Add step</Button>
            </div>
            <div className="flex gap-2"><Button onClick={save} disabled={!name.trim() || saving}>{saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}Save routine</Button><Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button></div>
          </div>
        ) : (
          <div className="space-y-3">
            <Button size="sm" onClick={() => setEditing("new")}><Plus className="mr-2 h-4 w-4" /> New automation</Button>
            {routines.isLoading && <p className="text-sm text-muted-foreground"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />Loading routines…</p>}
            {!routines.isLoading && (routines.data?.length ?? 0) === 0 && <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">No automation routines for this product.</p>}
            {routines.data?.map((routine) => (
              <div key={routine.id} className="flex items-center gap-3 rounded-md border p-3">
                <div className="min-w-0 flex-1"><p className="font-medium">{routine.name}</p><p className="truncate text-xs text-muted-foreground">{routine.description || `${routine.steps.length} step(s)`}</p></div>
                <Button size="sm" disabled={run.isPending} onClick={() => run.mutate(routine.id)}>{run.isPending && run.variables === routine.id ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Play className="mr-1 h-3.5 w-3.5" />}Run</Button>
                <Button variant="ghost" size="icon" onClick={() => setEditing(routine)}><Pencil className="h-4 w-4" /></Button>
                <Button variant="ghost" size="icon" onClick={() => remove.mutate({ id: routine.id, productId })}><Trash2 className="h-4 w-4 text-destructive" /></Button>
              </div>
            ))}
            {run.data && <div className={`rounded-md border p-3 text-sm ${run.data.status === "passed" ? "border-green-600/40" : "border-destructive/40"}`}><p className="font-medium capitalize">Last run: {run.data.status}</p>{run.data.steps.map((step) => <p key={step.index} className="text-xs text-muted-foreground">{step.index}. {step.action}: {step.outcome}</p>)}</div>}
          </div>
        )}
        {mutationError && <p className="mt-3 text-sm text-destructive">{mutationError.message}</p>}
      </div>
    </div>
  );
}
