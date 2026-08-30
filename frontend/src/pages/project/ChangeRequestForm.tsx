import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  CHANGE_REQUEST_IMPACT_FLAGS,
  changeRequestCreateSchema,
  type ChangeRequestCreateInput,
  type PlanBaseline,
} from "@/hooks/useProject";

interface ChangeRequestFormProps {
  baselines: PlanBaseline[];
  onSubmit: (values: ChangeRequestCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
  initialValues?: Partial<ChangeRequestCreateInput>;
}

export function ChangeRequestForm({
  baselines,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel: submitLabelProp,
  initialValues,
}: ChangeRequestFormProps) {
  const { t } = useTranslation("project");
  const submitLabel = submitLabelProp ?? t("changeRequestForm.submitLabelDefault");
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ChangeRequestCreateInput>({
    resolver: zodResolver(changeRequestCreateSchema),
    defaultValues: {
      title: initialValues?.title ?? "",
      justification: initialValues?.justification ?? "",
      plan_baseline_id: initialValues?.plan_baseline_id ?? "",
      requested_by: initialValues?.requested_by ?? "",
      affects_scope: initialValues?.affects_scope ?? false,
      affects_schedule: initialValues?.affects_schedule ?? false,
      affects_cost: initialValues?.affects_cost ?? false,
      adds_features: initialValues?.adds_features ?? false,
      removes_features: initialValues?.removes_features ?? false,
      introduces_critical_bug_fix: initialValues?.introduces_critical_bug_fix ?? false,
      changes_agents: initialValues?.changes_agents ?? false,
      changes_skills: initialValues?.changes_skills ?? false,
      changes_architecture: initialValues?.changes_architecture ?? false,
      changes_security: initialValues?.changes_security ?? false,
    },
  });

  return (
    <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="cr_title">{t("changeRequestForm.titleLabel")}</Label>
        <Input id="cr_title" placeholder={t("changeRequestForm.titlePlaceholder")} {...register("title")} />
        {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="justification">{t("changeRequestForm.justificationLabel")}</Label>
        <Textarea className="resize-none"
          id="justification"
          placeholder={t("changeRequestForm.justificationPlaceholder")}
          {...register("justification")}
        />
      </div>

      <div className="space-y-2">
        <Label>{t("changeRequestForm.impactLabel")}</Label>
        <div className="grid grid-cols-2 gap-2 rounded-md border border-border p-3">
          {CHANGE_REQUEST_IMPACT_FLAGS.map((flag) => (
            <div key={flag.key} className="flex items-center gap-2">
              <input
                id={flag.key}
                type="checkbox"
                className="h-4 w-4 rounded border-input"
                {...register(flag.key as keyof ChangeRequestCreateInput)}
              />
              <Label htmlFor={flag.key} className="cursor-pointer text-sm font-normal">
                {flag.label}
              </Label>
            </div>
          ))}
        </div>
        {errors.affects_scope && (
          <p className="text-sm text-destructive">{errors.affects_scope.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="schedule_delta_days">{t("changeRequestForm.scheduleDeltaLabel")}</Label>
          <Input
            id="schedule_delta_days"
            type="number"
            placeholder={t("changeRequestForm.scheduleDeltaPlaceholder")}
            {...register("schedule_delta_days")}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="cost_delta">{t("changeRequestForm.costDeltaLabel")}</Label>
          <Input
            id="cost_delta"
            type="number"
            step="0.01"
            placeholder={t("changeRequestForm.costDeltaPlaceholder")}
            {...register("cost_delta")}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="requested_by">{t("changeRequestForm.requestedByLabel")}</Label>
          <Input id="requested_by" placeholder={t("changeRequestForm.requestedByPlaceholder")} {...register("requested_by")} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="plan_baseline_id">{t("changeRequestForm.baselineLabel")}</Label>
          <Select id="plan_baseline_id" {...register("plan_baseline_id")}>
            <option value="">{t("changeRequestForm.noneOption")}</option>
            {baselines.map((baseline) => (
              <option key={baseline.id} value={baseline.id}>
                {baseline.name}
              </option>
            ))}
          </Select>
        </div>
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
