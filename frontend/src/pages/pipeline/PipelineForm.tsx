import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  PIPELINE_STATUSES,
  pipelineCreateSchema,
  type PipelineCreateInput,
  usePipelineTemplates,
} from "@/hooks/usePipeline";
import { useProjects } from "@/hooks/useProject";

interface PipelineFormProps {
  defaultValues?: Partial<PipelineCreateInput>;
  onSubmit: (values: PipelineCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
  /** Templates only apply on creation (the backend instantiates the
   * template's stages then; PATCH ignores template_id entirely) -- the
   * edit flow passes false so the select doesn't render as a control
   * that silently does nothing. */
  showTemplate?: boolean;
}

export function PipelineForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel,
  showTemplate = true,
}: PipelineFormProps) {
  const { t } = useTranslation("pipeline");
  const { data: projects, isLoading: isLoadingProjects } = useProjects();
  const { data: templates, isLoading: isLoadingTemplates } = usePipelineTemplates();
  const resolvedSubmitLabel = submitLabel ?? t("form.createPipelineLabel");

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PipelineCreateInput>({
    resolver: zodResolver(pipelineCreateSchema),
    defaultValues: {
      name: "",
      project_id: "",
      template_id: "",
      status: "draft",
      is_active: true,
      ...defaultValues,
    },
  });

  return (
    <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="name">{t("form.nameLabel")}</Label>
        <Input id="name" placeholder={t("form.namePlaceholder")} {...register("name")} />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="project_id">{t("form.projectLabel")}</Label>
        <Select id="project_id" disabled={isLoadingProjects} {...register("project_id")}>
          <option value="">
            {isLoadingProjects ? t("form.loadingProjects") : t("form.selectProject")}
          </option>
          {projects?.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </Select>
        {errors.project_id && (
          <p className="text-sm text-destructive">{errors.project_id.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {showTemplate && (
          <div className="space-y-2">
            <Label htmlFor="template_id">{t("form.templateLabel")}</Label>
            <Select id="template_id" disabled={isLoadingTemplates} {...register("template_id")}>
              <option value="">
                {isLoadingTemplates ? t("form.loadingTemplates") : t("form.noTemplate")}
              </option>
              {templates?.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">{t("form.templateHint")}</p>
            {errors.template_id && (
              <p className="text-sm text-destructive">{errors.template_id.message}</p>
            )}
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="status">{t("form.statusLabel")}</Label>
          <Select id="status" {...register("status")}>
            {PIPELINE_STATUSES.map((status) => (
              <option key={status} value={status}>
                {t(`pipelineStatus.${status}`)}
              </option>
            ))}
          </Select>
          {errors.status && <p className="text-sm text-destructive">{errors.status.message}</p>}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          id="is_active"
          type="checkbox"
          className="h-4 w-4 rounded border border-input"
          {...register("is_active")}
        />
        <Label htmlFor="is_active" className="!mb-0">
          {t("list.activeDescription")}
        </Label>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {t("form.cancel")}
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {resolvedSubmitLabel}
        </Button>
      </div>
    </form>
  );
}
