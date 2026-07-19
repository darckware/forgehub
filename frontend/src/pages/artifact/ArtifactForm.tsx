import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  ARTIFACT_STATUSES,
  ARTIFACT_TYPES,
  artifactCreateSchema,
  type ArtifactCreateInput,
} from "@/hooks/useArtifact";
import { useProjects } from "@/hooks/useProject";

interface ArtifactFormProps {
  defaultValues?: Partial<ArtifactCreateInput>;
  onSubmit: (values: ArtifactCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
}

export function ArtifactForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel,
}: ArtifactFormProps) {
  const { t } = useTranslation("artifact");
  const { data: projects, isLoading: isLoadingProjects } = useProjects();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ArtifactCreateInput>({
    resolver: zodResolver(artifactCreateSchema),
    defaultValues: {
      name: "",
      artifact_type: "other",
      status: "draft",
      description: "",
      project_id: "",
      pipeline_stage_id: "",
      task_execution_id: "",
      is_locked: false,
      ...defaultValues,
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="name">{t("form.nameLabel")}</Label>
        <Input id="name" placeholder={t("form.namePlaceholder")} {...register("name")} />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">{t("form.descriptionLabel")}</Label>
        <Textarea
          id="description"
          placeholder={t("form.descriptionPlaceholder")}
          {...register("description")}
        />
        {errors.description && (
          <p className="text-sm text-destructive">{errors.description.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="artifact_type">{t("form.typeLabel")}</Label>
          <Select id="artifact_type" {...register("artifact_type")}>
            {ARTIFACT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
          {errors.artifact_type && (
            <p className="text-sm text-destructive">{errors.artifact_type.message}</p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="status">{t("form.statusLabel")}</Label>
          <Select id="status" {...register("status")}>
            {ARTIFACT_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status.replace("_", " ")}
              </option>
            ))}
          </Select>
          {errors.status && <p className="text-sm text-destructive">{errors.status.message}</p>}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="project_id">{t("form.projectLabel")}</Label>
        <Select id="project_id" disabled={isLoadingProjects} {...register("project_id")}>
          <option value="">
            {isLoadingProjects ? t("form.projectLoading") : t("form.projectSelect")}
          </option>
          {projects?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        {errors.project_id && (
          <p className="text-sm text-destructive">{errors.project_id.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="pipeline_stage_id">{t("form.pipelineStageIdLabel")}</Label>
          <Input
            id="pipeline_stage_id"
            placeholder={t("form.pipelineStageIdPlaceholder")}
            {...register("pipeline_stage_id")}
          />
          {errors.pipeline_stage_id && (
            <p className="text-sm text-destructive">{errors.pipeline_stage_id.message}</p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="task_execution_id">{t("form.taskExecutionIdLabel")}</Label>
          <Input
            id="task_execution_id"
            placeholder={t("form.taskExecutionIdPlaceholder")}
            {...register("task_execution_id")}
          />
          {errors.task_execution_id && (
            <p className="text-sm text-destructive">{errors.task_execution_id.message}</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          id="is_locked"
          type="checkbox"
          className="h-4 w-4 rounded border-input"
          {...register("is_locked")}
        />
        <Label htmlFor="is_locked" className="cursor-pointer">
          {t("form.lockedLabel")}
        </Label>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {t("cancel")}
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {submitLabel ?? t("form.submitLabel")}
        </Button>
      </div>
    </form>
  );
}
