import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import {
  TASK_PRIORITIES,
  TASK_STATUSES,
  taskCreateSchema,
  type TaskCreateInput,
  useTasks,
} from "@/hooks/useTask";
import { usePlanningItems } from "@/hooks/useBacklog";
import { useChangeRequests, useProjects } from "@/hooks/useProject";
import { usePolicies } from "@/hooks/useGovernance";

interface TaskFormProps {
  defaultValues?: Partial<TaskCreateInput>;
  onSubmit: (values: TaskCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
  // Pre-selects the "Project" filter below (e.g. arriving from a planning
  // item's or CR's "New task" button) -- purely local UI state, never part
  // of the submitted payload (a task has no project_id column of its own,
  // see projectTaskSchema's docstring in useTask.ts).
  projectId?: string;
}

export function TaskForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel,
  projectId,
}: TaskFormProps) {
  const { t } = useTranslation("task");
  const resolvedSubmitLabel = submitLabel ?? t("form.submit");
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<TaskCreateInput>({
    resolver: zodResolver(taskCreateSchema),
    defaultValues: {
      title: "",
      description: "",
      plan_brief: "",
      planning_item_id: "",
      change_request_id: "",
      parent_task_id: "",
      policy_id: "",
      status: "planned",
      priority: "medium",
      planned_end_date: "",
      ...defaultValues,
    },
  });

  // "Project" is a filter, not a field: it narrows the Planning item /
  // Change request choices below to the selected project, but a task
  // traces to its project only indirectly (through whichever of those two
  // it's linked to) -- there's nothing to submit here.
  const [projectFilter, setProjectFilter] = useState(projectId ?? "");

  const { data: projects, isLoading: isLoadingProjects } = useProjects();
  const { data: planningItems, isLoading: isLoadingPlanningItems } = usePlanningItems(projectFilter || undefined);
  const { data: changeRequests, isLoading: isLoadingCRs } = useChangeRequests(projectFilter || undefined);
  const { data: allTasks, isLoading: isLoadingTasks } = useTasks();
  const { data: policies } = usePolicies();

  return (
    <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="title">{t("form.titleLabel")}</Label>
        <Input id="title" placeholder={t("form.titlePlaceholder")} {...register("title")} />
        {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">{t("form.descriptionLabel")}</Label>
        <Textarea className="resize-none"
          id="description"
          placeholder={t("form.descriptionPlaceholder")}
          {...register("description")}
        />
        {errors.description && (
          <p className="text-sm text-destructive">{errors.description.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="plan_brief">Plano/abordagem (opcional)</Label>
        <Textarea className="resize-none"
          id="plan_brief"
          placeholder="Como abordar, critérios de aceite, contexto para o agente que for executar..."
          {...register("plan_brief")}
        />
        {errors.plan_brief && (
          <p className="text-sm text-destructive">{errors.plan_brief.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="project_filter">{t("form.projectLabel")}</Label>
          <Select
            id="project_filter"
            disabled={isLoadingProjects}
            value={projectFilter}
            onChange={(e) => setProjectFilter(e.target.value)}
          >
            <option value="">
              {isLoadingProjects ? t("form.loadingProjects") : t("form.allProjects")}
            </option>
            {projects?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">{t("form.projectHint")}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="planning_item_id">{t("form.planningItemLabel")}</Label>
          <Select
            id="planning_item_id"
            disabled={isLoadingPlanningItems}
            {...register("planning_item_id")}
          >
            <option value="">
              {isLoadingPlanningItems ? t("form.loadingGeneric") : t("form.selectPlanningItem")}
            </option>
            {planningItems?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </Select>
          {errors.planning_item_id && (
            <p className="text-sm text-destructive">{errors.planning_item_id.message}</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="change_request_id">{t("form.changeRequestLabel")}</Label>
        <Select
          id="change_request_id"
          disabled={isLoadingCRs}
          {...register("change_request_id")}
        >
          <option value="">
            {isLoadingCRs ? t("form.loadingGeneric") : t("form.selectChangeRequest")}
          </option>
          {changeRequests?.map((cr) => (
            <option key={cr.id} value={cr.id}>
              [{cr.status}] {cr.title}
            </option>
          ))}
        </Select>
        {errors.change_request_id && (
          <p className="text-sm text-destructive">{errors.change_request_id.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="parent_task_id">{t("form.parentTaskLabel")}</Label>
          <Select id="parent_task_id" disabled={isLoadingTasks} {...register("parent_task_id")}>
            <option value="">
              {isLoadingTasks ? t("form.loadingTasks") : t("form.noParentTask")}
            </option>
            {allTasks?.map((task) => (
              <option key={task.id} value={task.id}>
                {task.title}
              </option>
            ))}
          </Select>
          {errors.parent_task_id && (
            <p className="text-sm text-destructive">{errors.parent_task_id.message}</p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="planned_end_date">{t("form.dueDateLabel")}</Label>
          <Input id="planned_end_date" type="date" {...register("planned_end_date")} />
          {errors.planned_end_date && (
            <p className="text-sm text-destructive">{errors.planned_end_date.message}</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="status">{t("form.statusLabel")}</Label>
          <Select id="status" {...register("status")}>
            {TASK_STATUSES.filter((status) => status !== "ready").map((status) => (
              <option key={status} value={status}>
                {t(`enums.taskStatus.${status}`, status.replace("_", " "))}
              </option>
            ))}
          </Select>
          {errors.status && <p className="text-sm text-destructive">{errors.status.message}</p>}
        </div>

        <div className="space-y-2">
          <Label htmlFor="priority">{t("form.priorityLabel")}</Label>
          <Select id="priority" {...register("priority")}>
            {TASK_PRIORITIES.map((priority) => (
              <option key={priority} value={priority}>
                {t(`enums.taskPriority.${priority}`, priority)}
              </option>
            ))}
          </Select>
          {errors.priority && <p className="text-sm text-destructive">{errors.priority.message}</p>}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="policy_id">{t("form.policyLabel")}</Label>
        <Select id="policy_id" {...register("policy_id")}>
          <option value="">{t("form.noPolicy")}</option>
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
