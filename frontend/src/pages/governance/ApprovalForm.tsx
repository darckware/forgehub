import { useForm, useWatch, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import {
  APPROVAL_ENTITY_TYPES,
  approvalCreateSchema,
  type ApprovalCreateInput,
  usePolicies,
} from "@/hooks/useGovernance";
import { useTasks } from "@/hooks/useTask";
import { useArtifacts } from "@/hooks/useArtifact";
import { useAllProductVersions } from "@/hooks/useProduct";
import { useAllGates } from "@/hooks/usePipeline";

interface ApprovalFormProps {
  defaultValues?: Partial<ApprovalCreateInput>;
  onSubmit: (values: ApprovalCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
}

function EntitySelect({
  entityType,
  value,
  onChange,
}: {
  entityType: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation("governance");
  const tasks = useTasks();
  const artifacts = useArtifacts();
  const versions = useAllProductVersions();
  const gates = useAllGates();

  const makeSelect = (options: { id: string; label: string }[]) => (
    <Select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("form.selectPlaceholder")}</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </Select>
  );

  if (entityType === "project_task") {
    const opts = (tasks.data ?? []).map((t) => ({ id: t.id, label: t.title }));
    return makeSelect(opts);
  }
  if (entityType === "artifact") {
    const opts = (artifacts.data ?? []).map((a) => ({ id: a.id, label: a.name }));
    return makeSelect(opts);
  }
  if (entityType === "release") {
    const opts = (versions.data ?? []).map((v) => ({ id: v.id, label: v.version }));
    return makeSelect(opts);
  }
  if (entityType === "pipeline_stage_gate") {
    const opts = (gates.data ?? []).map((g) => ({ id: g.id, label: g.name }));
    return makeSelect(opts);
  }

  // Fallback for types without a list endpoint (skill, change_request, etc.)
  return (
    <Input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={t("form.entityUuidPlaceholder")}
    />
  );
}

export function ApprovalForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel,
}: ApprovalFormProps) {
  const { t } = useTranslation("governance");
  const effectiveSubmitLabel = submitLabel ?? t("form.createApproval");
  const { data: policies } = usePolicies();

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<ApprovalCreateInput>({
    resolver: zodResolver(approvalCreateSchema),
    defaultValues: {
      entity_type: "pipeline_stage_gate",
      entity_id: "",
      approval_type: "",
      requested_by: "",
      comments: "",
      policy_id: "",
      ...defaultValues,
    },
  });

  const entityType = useWatch({ control, name: "entity_type" });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="entity_type">{t("form.entityType")}</Label>
          <Select id="entity_type" {...register("entity_type")}>
            {APPROVAL_ENTITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
          {errors.entity_type && (
            <p className="text-sm text-destructive">{errors.entity_type.message}</p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="entity_id">{t("form.entity")}</Label>
          <Controller
            control={control}
            name="entity_id"
            render={({ field }) => (
              <EntitySelect
                entityType={entityType}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          {errors.entity_id && (
            <p className="text-sm text-destructive">{errors.entity_id.message}</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="approval_type">{t("form.approvalType")}</Label>
          <Input
            id="approval_type"
            placeholder={t("form.approvalTypePlaceholder")}
            {...register("approval_type")}
          />
          {errors.approval_type && (
            <p className="text-sm text-destructive">{errors.approval_type.message}</p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="requested_by">{t("form.requestedBy")}</Label>
          <Input id="requested_by" placeholder={t("form.requestedByPlaceholder")} {...register("requested_by")} />
          {errors.requested_by && (
            <p className="text-sm text-destructive">{errors.requested_by.message}</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="policy_id">{t("form.policy")}</Label>
        <Select id="policy_id" {...register("policy_id")}>
          <option value="">{t("form.noPolicyLinked")}</option>
          {(policies ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        {errors.policy_id && (
          <p className="text-sm text-destructive">{errors.policy_id.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="comments">{t("form.comments")}</Label>
        <Textarea
          id="comments"
          placeholder={t("form.commentsPlaceholder")}
          {...register("comments")}
        />
        {errors.comments && (
          <p className="text-sm text-destructive">{errors.comments.message}</p>
        )}
      </div>

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {t("form.cancel")}
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {effectiveSubmitLabel}
        </Button>
      </div>
    </form>
  );
}
