import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
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
}

export function PipelineForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel = "Create pipeline",
}: PipelineFormProps) {
  const { data: projects, isLoading: isLoadingProjects } = useProjects();
  const { data: templates, isLoading: isLoadingTemplates } = usePipelineTemplates();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PipelineCreateInput>({
    resolver: zodResolver(pipelineCreateSchema),
    defaultValues: {
      name: "",
      project_id: "",
      pipeline_template_id: "",
      status: "draft",
      is_active: true,
      ...defaultValues,
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="name">Name</Label>
        <Input id="name" placeholder="Foundation MVP delivery pipeline" {...register("name")} />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="project_id">Project</Label>
        <Select id="project_id" disabled={isLoadingProjects} {...register("project_id")}>
          <option value="">
            {isLoadingProjects ? "Loading projects…" : "Select a project"}
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
        <div className="space-y-2">
          <Label htmlFor="pipeline_template_id">Template (optional)</Label>
          <Select id="pipeline_template_id" disabled={isLoadingTemplates} {...register("pipeline_template_id")}>
            <option value="">
              {isLoadingTemplates ? "Loading templates…" : "No template"}
            </option>
            {templates?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
          {errors.pipeline_template_id && (
            <p className="text-sm text-destructive">{errors.pipeline_template_id.message}</p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="status">Status</Label>
          <Select id="status" {...register("status")}>
            {PIPELINE_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status.replace("_", " ")}
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
          Active pipeline for this project
        </Label>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
