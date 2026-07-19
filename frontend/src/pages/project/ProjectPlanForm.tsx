import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { projectPlanCreateSchema, type ProjectPlanCreateInput } from "@/hooks/useProject";

interface ProjectPlanFormProps {
  onSubmit: (values: ProjectPlanCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
}

export function ProjectPlanForm({
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel: submitLabelProp,
}: ProjectPlanFormProps) {
  const { t } = useTranslation("project");
  const submitLabel = submitLabelProp ?? t("projectPlanForm.submitLabelDefault");
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ProjectPlanCreateInput>({
    resolver: zodResolver(projectPlanCreateSchema),
    defaultValues: {
      name: "",
      scope_summary: "",
      estimated_start_date: "",
      estimated_end_date: "",
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="plan_name">{t("projectPlanForm.nameLabel")}</Label>
        <Input id="plan_name" placeholder={t("projectPlanForm.namePlaceholder")} {...register("name")} />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="scope_summary">{t("projectPlanForm.scopeSummaryLabel")}</Label>
        <Textarea
          id="scope_summary"
          placeholder={t("projectPlanForm.scopeSummaryPlaceholder")}
          {...register("scope_summary")}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="estimated_start_date">{t("projectPlanForm.estimatedStartLabel")}</Label>
          <Input id="estimated_start_date" type="date" {...register("estimated_start_date")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="estimated_end_date">{t("projectPlanForm.estimatedEndLabel")}</Label>
          <Input id="estimated_end_date" type="date" {...register("estimated_end_date")} />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="estimated_cost">{t("projectPlanForm.estimatedCostLabel")}</Label>
        <Input
          id="estimated_cost"
          type="number"
          step="0.01"
          placeholder={t("projectPlanForm.estimatedCostPlaceholder")}
          {...register("estimated_cost")}
        />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {t("shared.cancel")}
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
