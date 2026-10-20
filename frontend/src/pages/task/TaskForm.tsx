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

interface TaskFormProps {
  defaultValues?: Partial<TaskCreateInput>;
  onSubmit: (values: TaskCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
  projectId?: string;
}

export function TaskForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel,
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

  const { data: allTasks, isLoading: isLoadingTasks } = useTasks();

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
                {t(`enums.taskStatuses.${status}`, {
                  defaultValue: t(`enums.taskStatus.${status}`, {
                    defaultValue: status === "in_progress" ? "Em andamento" : status === "planned" ? "Planejada" : status === "blocked" ? "Bloqueada" : status === "done" ? "Concluída" : status === "deployed" ? "Implantada" : status === "cancelled" ? "Cancelada" : status === "assigned" ? "Atribuída" : status,
                  }),
                })}
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
