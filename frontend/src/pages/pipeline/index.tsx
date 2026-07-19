import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("pipeline");
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
      { ...values, template_id: values.template_id || undefined },
      { onSuccess: () => setShowForm(false) }
    );
  }

  function EditInline({ id }: { id: string }) {
    const updatePipeline = useUpdatePipeline(id);
    const pipeline = pipelines?.find((p) => p.id === id);
    if (!pipeline) return null;

    function handleUpdate(values: PipelineUpdateInput) {
      // template_id never applies on update (see PipelineForm's
      // showTemplate) -- strip it so the PATCH carries only real changes.
      const { template_id: _ignored, ...rest } = values;
      updatePipeline.mutate(rest, { onSuccess: () => setEditingId(null) });
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
          submitLabel={t("list.saveChanges")}
          showTemplate={false}
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
          <h1 className="text-3xl font-bold tracking-tight">{t("list.title")}</h1>
          <p className="text-muted-foreground">{t("list.description")}</p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          {t("list.newPipeline")}
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>{t("list.createTitle")}</CardTitle>
            <CardDescription>{t("list.createDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <PipelineForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createPipeline.isPending}
            />
            {createPipeline.isError && (
              <p className="mt-3 text-sm text-destructive">
                {t("list.createError", { message: (createPipeline.error as Error)?.message })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("list.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("list.loadError", { message: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && pipelines && pipelines.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <GitBranch className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">{t("list.emptyTitle")}</p>
              <p className="text-sm text-muted-foreground">{t("list.emptyDescription")}</p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t("list.newPipeline")}
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
                      {t(`pipelineStatus.${pipeline.status}`)}
                    </Badge>
                  </div>
                  <CardDescription>
                    {pipeline.is_active
                      ? t("list.activeDescription")
                      : t("list.inactiveDescription")}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex-1 text-sm text-muted-foreground">
                  <p>{t("list.projectLabel", { name: projectName(pipeline.project_id) })}</p>
                  <p className="mt-1">
                    {stageCount > 0
                      ? t("list.stagesCompleted", { completed: completedCount, total: stageCount })
                      : t("list.noStagesYet")}
                  </p>
                </CardContent>
                <CardFooter className="flex justify-between gap-2">
                  <Link
                    to={`/pipeline/${pipeline.id}`}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    {t("list.viewDetails")}
                  </Link>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditingId(editingId === pipeline.id ? null : pipeline.id)}
                      aria-label={t("list.editAria", { name: pipeline.name })}
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
                      aria-label={t("list.deleteAria", { name: pipeline.name })}
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
        title={t("list.deleteTitle")}
        description={t("list.deleteDescription")}
        confirmLabel={t("list.deleteConfirm")}
        onConfirm={() => {
          if (pendingDeleteId) deletePipeline.mutate(pendingDeleteId);
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}
