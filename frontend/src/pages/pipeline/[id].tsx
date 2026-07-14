import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  CircleDashed,
  Loader2,
  Lock,
  Pencil,
  Plus,
  Save,
  ShieldCheck,
  RotateCcw,
  Waypoints,
  Trash2,
  X,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  STAGE_STATUSES,
  STAGE_TYPES,
  stageCreateSchema,
  type PipelineStage,
  type StageCreateInput,
  usePipeline,
  useCreateStage,
  useDeleteStage,
  useUpdateStage,
  useProjectProgress,
  useProgressTimeline,
  useEvaluateStageCompletion,
  useCompleteStage,
  type StageProgress,
} from "@/hooks/usePipeline";
import { useProjects } from "@/hooks/useProject";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { useActionPermission } from "@/hooks/usePermission";

const STAGE_STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  pending: "outline",
  in_progress: "warning",
  blocked: "destructive",
  completed: "success",
  skipped: "secondary",
};

const PIPELINE_STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  draft: "outline",
  active: "success",
  paused: "warning",
  completed: "secondary",
  archived: "destructive",
};

function StageCard({
  stage,
  index,
  pipelineId,
  projectId,
  progress,
}: {
  stage: PipelineStage;
  index: number;
  pipelineId: string;
  projectId: string;
  progress?: StageProgress;
}) {
  const [editStatus, setEditStatus] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(stage.name);
  const [editType, setEditType] = useState<typeof STAGE_TYPES[number]>(
    (stage.stage_type as typeof STAGE_TYPES[number]) ?? "implementation",
  );
  const [editApproval, setEditApproval] = useState(stage.requires_approval);
  const [editVerif, setEditVerif] = useState(stage.requires_verification);
  const artifacts = stage.required_artifacts ?? [];
  const gates = stage.gates ?? [];
  const isBlocked = stage.status === "blocked";

  const updateStage = useUpdateStage(pipelineId, stage.id);
  const deleteStage = useDeleteStage(pipelineId);
  const evaluateCompletion = useEvaluateStageCompletion(projectId, stage.id);
  const completeStage = useCompleteStage(projectId, pipelineId, stage.id);
  const canViewProgress = useActionPermission("planning.progress.view");
  const canComplete = useActionPermission("planning.stage.complete");

  const saveEdit = () => {
    updateStage.mutate(
      { name: editName, stage_type: editType, requires_approval: editApproval, requires_verification: editVerif },
      { onSuccess: () => setEditing(false) },
    );
  };

  const openEdit = () => {
    setEditName(stage.name);
    setEditType((stage.stage_type as typeof STAGE_TYPES[number]) ?? "implementation");
    setEditApproval(stage.requires_approval);
    setEditVerif(stage.requires_verification);
    setEditing(true);
  };

  return (
    <Card className={cn(isBlocked && "border-destructive/50")}>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
              {stage.order_index ?? index + 1}
            </span>
            {editing ? (
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} className="h-7 text-sm font-medium" />
            ) : (
              <CardTitle className="text-base leading-tight truncate">{stage.name}</CardTitle>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {editStatus ? (
              <Select
                className="h-7 text-xs"
                defaultValue={stage.status}
                onChange={(e) => {
                  updateStage.mutate({ status: e.target.value as typeof STAGE_STATUSES[number] });
                  setEditStatus(false);
                }}
                onBlur={() => setEditStatus(false)}
                autoFocus
              >
                {STAGE_STATUSES.filter((s) => s !== "completed").map((s) => (
                  <option key={s} value={s}>
                    {s.replace("_", " ")}
                  </option>
                ))}
              </Select>
            ) : (
              <Badge
                variant={STAGE_STATUS_VARIANT[stage.status] ?? "outline"}
                className="cursor-pointer"
                onClick={() => setEditStatus(true)}
                title="Click to change status"
              >
                {stage.status.replace("_", " ")}
              </Badge>
            )}
            {editing ? (
              <>
                <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={saveEdit} disabled={updateStage.isPending}>
                  {updateStage.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5 text-primary" />}
                </Button>
                <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setEditing(false)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </>
            ) : (
              <>
                <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={openEdit} aria-label={`Edit stage ${stage.name}`}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  disabled={deleteStage.isPending}
                  onClick={() => deleteStage.mutate(stage.id)}
                  aria-label={`Delete stage ${stage.name}`}
                >
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </>
            )}
          </div>
        </div>
        {editing ? (
          <div className="mt-2 flex flex-col gap-2">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">Type</span>
              <select
                value={editType}
                onChange={(e) => setEditType(e.target.value as typeof STAGE_TYPES[number])}
                className="h-8 rounded-md border border-input bg-background px-2 text-xs"
              >
                {STAGE_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div className="flex gap-4">
              <label className="flex items-center gap-1.5 text-xs">
                <input type="checkbox" checked={editApproval} onChange={(e) => setEditApproval(e.target.checked)} className="h-3.5 w-3.5" />
                Requires approval
              </label>
              <label className="flex items-center gap-1.5 text-xs">
                <input type="checkbox" checked={editVerif} onChange={(e) => setEditVerif(e.target.checked)} className="h-3.5 w-3.5" />
                Requires verification
              </label>
            </div>
          </div>
        ) : (
          stage.stage_type && (
            <CardDescription className="capitalize">
              {stage.stage_type.replace(/_/g, " ")}
            </CardDescription>
          )
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {!editing && (stage.requires_approval || stage.requires_verification) && (
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {stage.requires_approval && (
              <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
                <Lock className="h-3 w-3" />
                Requires approval
              </span>
            )}
            {stage.requires_verification && (
              <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5">
                <ShieldCheck className="h-3 w-3" />
                Requires verification
              </span>
            )}
          </div>
        )}

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Required artifacts
          </p>
          {artifacts.length === 0 ? (
            <p className="text-sm italic text-muted-foreground">None defined</p>
          ) : (
            <ul className="space-y-1.5">
              {artifacts.map((artifact) => (
                <li key={artifact.id} className="flex items-center gap-2 text-sm">
                  {artifact.is_fulfilled ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                  ) : (
                    <CircleDashed className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className={cn(!artifact.is_fulfilled && "text-muted-foreground")}>
                    {artifact.artifact_type}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Gates
          </p>
          {gates.length === 0 ? (
            <p className="text-sm italic text-muted-foreground">None defined</p>
          ) : (
            <ul className="space-y-1.5">
              {gates.map((gate) => (
                <li key={gate.id} className="flex items-center gap-2 text-sm">
                  {gate.status === "approved" ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                  ) : (
                    <CircleDashed className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className={cn(gate.status !== "approved" && "text-muted-foreground")}>
                    {gate.name}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {stage.depends_on_stage_ids && stage.depends_on_stage_ids.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Depends on {stage.depends_on_stage_ids.length} stage
            {stage.depends_on_stage_ids.length > 1 ? "s" : ""}
          </p>
        )}

        {canViewProgress && (
          <div className="space-y-2 rounded-md border bg-muted/30 p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">Completion control</span>
              <span>{progress?.requirement_completed ?? 0}/{progress?.requirement_total ?? 0} confirmed</span>
            </div>
            {progress?.last_checkpoint ? (
              <div className="space-y-1 text-muted-foreground">
                <p>Last checkpoint: {progress.last_checkpoint.step_label}</p>
                <p>{new Date(progress.last_checkpoint.last_confirmed_at).toLocaleString()} · {progress.last_checkpoint.actor_name}</p>
                {progress.stopped_reason && <p className="text-destructive">Stopped: {progress.stopped_reason}</p>}
                {progress.resume_from && <p>Resume from: {progress.resume_from}</p>}
              </div>
            ) : <p className="text-muted-foreground">No checkpoint recorded.</p>}
            {progress?.missing_requirements?.length ? (
              <ul className="space-y-1 text-muted-foreground">
                {progress.missing_requirements.slice(0, 3).map((item) => <li key={item.key}>Pending: {item.label}</li>)}
              </ul>
            ) : null}
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" variant="outline" disabled={evaluateCompletion.isPending} onClick={() => evaluateCompletion.mutate()}>
                {evaluateCompletion.isPending ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <RotateCcw className="mr-1 h-3 w-3" />}
                Evaluate
              </Button>
              {canComplete && progress?.completion_assessment?.result === "ready" && stage.status !== "completed" && (
                <Button size="sm" disabled={completeStage.isPending} onClick={() => completeStage.mutate(progress.completion_assessment!.id)}>
                  <CheckCircle2 className="mr-1 h-3 w-3" /> Complete stage
                </Button>
              )}
            </div>
            {(evaluateCompletion.isError || completeStage.isError) && <p className="text-destructive">{String((evaluateCompletion.error ?? completeStage.error) as Error)}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AddStageForm({
  pipelineId,
  nextOrder,
  onClose,
}: {
  pipelineId: string;
  nextOrder: number;
  onClose: () => void;
}) {
  const createStage = useCreateStage(pipelineId);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<StageCreateInput>({
    resolver: zodResolver(stageCreateSchema),
    defaultValues: {
      name: "",
      stage_type: "implementation",
      order_index: nextOrder,
      status: "pending",
      requires_approval: false,
      requires_verification: false,
    },
  });

  function onSubmit(values: StageCreateInput) {
    createStage.mutate(values, { onSuccess: onClose });
  }

  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle className="text-base">Add stage</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="stage_name">Name</Label>
              <Input id="stage_name" placeholder="Implementation" {...register("name")} />
              {errors.name && (
                <p className="text-sm text-destructive">{errors.name.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="order_index">Order</Label>
              <Input id="order_index" type="number" min={0} {...register("order_index")} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="stage_type">Type</Label>
              <Select id="stage_type" {...register("stage_type")}>
                {STAGE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="stage_status">Status</Label>
              <Select id="stage_status" {...register("status")}>
                {STAGE_STATUSES.filter((s) => s !== "completed").map((s) => (
                  <option key={s} value={s}>
                    {s.replace("_", " ")}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 rounded border-input" {...register("requires_approval")} />
              Requires approval
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4 rounded border-input" {...register("requires_verification")} />
              Requires verification
            </label>
          </div>
          {createStage.isError && (
            <p className="text-sm text-destructive">
              {(createStage.error as Error)?.message}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={createStage.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={createStage.isPending}>
              {createStage.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Add stage
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function PipelineDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: pipeline, isLoading, isError, error } = usePipeline(id);
  const { data: projects } = useProjects();
  const canViewProgress = useActionPermission("planning.progress.view");
  const { data: progress } = useProjectProgress(canViewProgress ? pipeline?.project_id : undefined);
  const { data: timeline } = useProgressTimeline(canViewProgress ? pipeline?.project_id : undefined);
  const [showAddStage, setShowAddStage] = useState(false);

  const projectName = (pid: string): string =>
    projects?.find((p) => p.id === pid)?.name ?? pid.slice(0, 8) + "…";

  const sortedStages = pipeline?.stages
    ? [...pipeline.stages].sort((a, b) => a.order_index - b.order_index)
    : [];

  const nextOrder = sortedStages.length > 0
    ? Math.max(...sortedStages.map((s) => s.order_index)) + 1
    : 0;

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Pipelines", href: "/pipeline" },
          { label: pipeline?.name ?? "…" },
        ]}
      />

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading pipeline…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load pipeline: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && pipeline && (
        <>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{pipeline.name}</h1>
              <p className="mt-1 text-muted-foreground">
                Project: {projectName(pipeline.project_id)}
              </p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <Badge
                variant={PIPELINE_STATUS_VARIANT[pipeline.status] ?? "outline"}
                className="text-sm capitalize"
              >
                {pipeline.status.replace("_", " ")}
              </Badge>
              {pipeline.is_active && <Badge variant="success">Active pipeline</Badge>}
            </div>
          </div>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2"><Waypoints className="h-5 w-5" /><CardTitle className="text-xl">Project progress</CardTitle></div>
              <CardDescription>Authoritative checkpoints and the exact safe resume point.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-3">
              <div><p className="text-xs text-muted-foreground">Macroflow</p><p className="font-medium capitalize">{progress?.macroflow ?? "—"}</p></div>
              <div><p className="text-xs text-muted-foreground">Last confirmation</p><p className="font-medium">{progress?.last_confirmed_at ? new Date(progress.last_confirmed_at).toLocaleString() : "No checkpoint"}</p></div>
              <div><p className="text-xs text-muted-foreground">Next safe action</p><p className="font-medium">{progress?.first_safe_action ?? "Evaluate the current stage"}</p></div>
              {progress?.stopped_at && <div className="md:col-span-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"><strong>Stopped at {progress.stopped_at.step_label}:</strong> {progress.stopped_at.reason ?? progress.stopped_at.type}</div>}
              {timeline?.length ? <div className="md:col-span-3 space-y-2"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Timeline · {timeline.length} checkpoint(s)</p><div className="space-y-1">{timeline.slice(-5).reverse().map((checkpoint) => <div key={checkpoint.id} className="flex flex-wrap items-center justify-between gap-2 rounded border px-2 py-1.5 text-xs"><span><Badge variant={checkpoint.checkpoint_type === "completed" || checkpoint.checkpoint_type === "resumed" ? "success" : checkpoint.checkpoint_type === "blocked" || checkpoint.checkpoint_type === "failed" ? "destructive" : "outline"}>{checkpoint.checkpoint_type.replace(/_/g, " ")}</Badge> <span className="ml-2">{checkpoint.step_label}</span></span><span className="text-muted-foreground">{new Date(checkpoint.last_confirmed_at).toLocaleString()}</span></div>)}</div></div> : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xl">Stages</CardTitle>
                <CardDescription>
                  Stages execute in order. A stage cannot complete until its required artifacts
                  exist, its gates pass, and a current completion assessment confirms readiness.
                </CardDescription>
              </div>
              <Button size="sm" onClick={() => setShowAddStage((v) => !v)}>
                <Plus className="mr-2 h-4 w-4" />
                Add stage
              </Button>
            </CardHeader>
            <CardContent>
              {sortedStages.length === 0 && !showAddStage && (
                <p className="text-sm text-muted-foreground">
                  No stages defined for this pipeline yet.
                </p>
              )}
              {(sortedStages.length > 0 || showAddStage) && (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {sortedStages.map((stage, index) => (
                    <StageCard
                      key={stage.id}
                      stage={stage}
                      index={index}
                      pipelineId={pipeline.id}
                      projectId={pipeline.project_id}
                      progress={progress?.stages.find((item) => item.stage_id === stage.id)}
                    />
                  ))}
                  {showAddStage && (
                    <AddStageForm
                      pipelineId={pipeline.id}
                      nextOrder={nextOrder}
                      onClose={() => setShowAddStage(false)}
                    />
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <div>
            <Link to="/pipeline" className={buttonVariants({ variant: "outline" })}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to list
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
