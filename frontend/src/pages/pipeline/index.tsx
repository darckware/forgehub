import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, GitBranch, Loader2, Plus, Trash2, Pencil, X } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  useCreatePipeline,
  useDeletePipeline,
  usePipelines,
  useUpdatePipeline,
  type PipelineCreateInput,
  type PipelineUpdateInput,
} from "@/hooks/usePipeline";
import { useProjects } from "@/hooks/useProject";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PipelineForm } from "./PipelineForm";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  draft: "outline",
  active: "success",
  paused: "warning",
  completed: "secondary",
  archived: "destructive",
};

export default function PipelinePage() {
  const { data: pipelines, isLoading, isError, error } = usePipelines();
  const { data: projects } = useProjects();
  const createPipeline = useCreatePipeline();
  const deletePipeline = useDeletePipeline();
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const projectName = (id: string): string =>
    projects?.find((p) => p.id === id)?.name ?? id.slice(0, 8) + "…";

  function handleCreate(values: PipelineCreateInput) {
    createPipeline.mutate(
      { ...values, pipeline_template_id: values.pipeline_template_id || undefined },
      { onSuccess: () => setShowForm(false) }
    );
  }

  function EditInline({ id }: { id: string }) {
    const updatePipeline = useUpdatePipeline(id);
    const pipeline = pipelines?.find((p) => p.id === id);
    if (!pipeline) return null;

    function handleUpdate(values: PipelineUpdateInput) {
      updatePipeline.mutate(
        { ...values, pipeline_template_id: values.pipeline_template_id || undefined },
        { onSuccess: () => setEditingId(null) }
      );
    }

    return (
      <CardContent className="border-t border-border pt-4">
        <PipelineForm
          defaultValues={{
            name: pipeline.name,
            project_id: pipeline.project_id,
            status: pipeline.status,
            is_active: pipeline.is_active,
          }}
          onSubmit={handleUpdate}
          onCancel={() => setEditingId(null)}
          isSubmitting={updatePipeline.isPending}
          submitLabel="Save changes"
        />
        {updatePipeline.isError && (
          <p className="mt-2 text-sm text-destructive">
            {(updatePipeline.error as Error)?.message}
          </p>
        )}
      </CardContent>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Pipelines</h1>
          <p className="text-muted-foreground">
            Delivery flow for each project: ordered stages, required artifacts, and approval
            gates that must pass before release.
          </p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          New pipeline
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Create pipeline</CardTitle>
            <CardDescription>
              Register a project pipeline, optionally seeded from a pipeline template. Stages can
              be added afterwards.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PipelineForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createPipeline.isPending}
            />
            {createPipeline.isError && (
              <p className="mt-3 text-sm text-destructive">
                Failed to create pipeline: {(createPipeline.error as Error)?.message}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading pipelines…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load pipelines: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && pipelines && pipelines.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <GitBranch className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No pipelines yet</p>
              <p className="text-sm text-muted-foreground">
                Every project must have an active pipeline. Create one to start defining stages.
              </p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New pipeline
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && pipelines && pipelines.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {pipelines.map((pipeline) => {
            const stageCount = pipeline.stages?.length ?? 0;
            const completedCount =
              pipeline.stages?.filter((s) => s.status === "completed").length ?? 0;
            return (
              <Card key={pipeline.id} className="flex flex-col">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-lg leading-tight">{pipeline.name}</CardTitle>
                    <Badge variant={STATUS_VARIANT[pipeline.status] ?? "outline"}>
                      {pipeline.status.replace("_", " ")}
                    </Badge>
                  </div>
                  <CardDescription>
                    {pipeline.is_active ? "Active pipeline for this project" : "Inactive"}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex-1 text-sm text-muted-foreground">
                  <p>Project: {projectName(pipeline.project_id)}</p>
                  <p className="mt-1">
                    {stageCount > 0
                      ? `${completedCount}/${stageCount} stages completed`
                      : "No stages defined yet"}
                  </p>
                </CardContent>
                <CardFooter className="flex justify-between gap-2">
                  <Link
                    to={`/pipeline/${pipeline.id}`}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    View details
                  </Link>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditingId(editingId === pipeline.id ? null : pipeline.id)}
                      aria-label={`Edit ${pipeline.name}`}
                    >
                      {editingId === pipeline.id
                        ? <X className="h-4 w-4" />
                        : <Pencil className="h-4 w-4" />}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setPendingDeleteId(pipeline.id)}
                      disabled={deletePipeline.isPending}
                      aria-label={`Delete ${pipeline.name}`}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </CardFooter>
                {editingId === pipeline.id && <EditInline id={pipeline.id} />}
              </Card>
            );
          })}
        </div>
      )}
      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete pipeline?"
        description="This will permanently delete the pipeline and all its stages. This cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDeleteId) deletePipeline.mutate(pendingDeleteId);
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}
