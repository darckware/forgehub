import { useState } from "react";
import { AlertCircle, CheckSquare, Loader2, Plus, Pencil, Trash2, ShieldCheck } from "lucide-react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge, Badge as StatusBadge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  usePolicies,
  useCreatePolicy,
  useUpdatePolicy,
  useDeletePolicy,
  type Policy,
  type PolicyInput,
} from "@/hooks/useGovernance";
import { useArtifacts } from "@/hooks/useArtifact";
import { useTasksByPolicy } from "@/hooks/useTask";

function makePolicyFormSchema(t: TFunction) {
  return z.object({
    name: z.string().min(1, t("policies.validation.nameRequired")).max(200),
    description: z.string().max(2000).optional().or(z.literal("")),
    policy_type: z.string().min(1, t("policies.validation.typeRequired")).max(100),
    is_active: z.boolean().default(true),
    entity_id: z.string().min(1, t("policies.validation.artifactRequired")),
  });
}

type PolicyFormValues = z.infer<ReturnType<typeof makePolicyFormSchema>>;

function PolicyForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel,
}: {
  defaultValues?: Partial<PolicyFormValues>;
  onSubmit: (v: PolicyFormValues) => void;
  onCancel: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
}) {
  const { t } = useTranslation("governance");
  const effectiveSubmitLabel = submitLabel ?? t("policies.form.save");
  const { data: artifacts } = useArtifacts();

  const { register, handleSubmit, control, formState: { errors } } = useForm<PolicyFormValues>({
    resolver: zodResolver(makePolicyFormSchema(t)),
    defaultValues: { name: "", description: "", policy_type: "", is_active: true, entity_id: "", ...defaultValues },
  });

  return (
    <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>{t("policies.form.name")}</Label>
          <Input placeholder={t("policies.form.namePlaceholder")} {...register("name")} />
          {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
        </div>
        <div className="space-y-2">
          <Label>{t("policies.form.type")}</Label>
          <Input placeholder={t("policies.form.typePlaceholder")} {...register("policy_type")} />
          {errors.policy_type && <p className="text-xs text-destructive">{errors.policy_type.message}</p>}
        </div>
      </div>

      <div className="space-y-2">
        <Label>{t("policies.form.linkedArtifact")}</Label>
        <Controller
          control={control}
          name="entity_id"
          render={({ field }) => (
            <Select value={field.value} onChange={(e) => field.onChange(e.target.value)}>
              <option value="">{t("policies.form.selectArtifact")}</option>
              {(artifacts ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          )}
        />
        {errors.entity_id && <p className="text-xs text-destructive">{errors.entity_id.message}</p>}
      </div>

      <div className="space-y-2">
        <Label>{t("policies.form.description")}</Label>
        <Textarea className="resize-none"
          placeholder={t("policies.form.descriptionPlaceholder")}
          rows={3}
          {...register("description")}
        />
      </div>

      <div className="flex items-center gap-2">
        <input type="checkbox" id="is_active" {...register("is_active")} className="rounded" />
        <Label htmlFor="is_active" className="cursor-pointer">{t("policies.form.active")}</Label>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
          {t("policies.form.cancel")}
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {effectiveSubmitLabel}
        </Button>
      </div>
    </form>
  );
}

function ArtifactName({ artifactId, artifacts }: { artifactId: string | null | undefined; artifacts: { id: string; name: string }[] }) {
  if (!artifactId) return <>—</>;
  const found = artifacts.find((a) => a.id === artifactId);
  return <>{found?.name ?? artifactId.slice(0, 8) + "…"}</>;
}

export default function PoliciesPage() {
  const { t } = useTranslation("governance");
  const { data: policies, isLoading, isError } = usePolicies();
  const { data: artifacts } = useArtifacts();
  const createPolicy = useCreatePolicy();
  const deletePolicy = useDeletePolicy();
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  function handleCreate(values: PolicyFormValues) {
    const payload: PolicyInput = {
      ...values,
      entity_type: "artifact",
      entity_id: values.entity_id as unknown as undefined,
    };
    createPolicy.mutate(payload, { onSuccess: () => setShowCreate(false) });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("policies.title")}</h1>
          <p className="text-muted-foreground">
            {t("policies.description")}
          </p>
        </div>
        <Button onClick={() => { setShowCreate(true); setEditingId(null); }}>
          <Plus className="mr-2 h-4 w-4" /> {t("policies.newPolicy")}
        </Button>
      </div>

      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle>{t("policies.newPolicy")}</CardTitle>
            <CardDescription>{t("policies.newPolicyCard.description")}</CardDescription>
          </CardHeader>
          <CardContent>
            <PolicyForm
              onSubmit={handleCreate}
              onCancel={() => setShowCreate(false)}
              isSubmitting={createPolicy.isPending}
              submitLabel={t("policies.createPolicy")}
            />
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" /> {t("policies.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" /> {t("policies.loadFailed")}
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && policies?.length === 0 && !showCreate && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldCheck className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">{t("policies.empty.title")}</p>
            <p className="text-sm text-muted-foreground">{t("policies.empty.description")}</p>
            <Button onClick={() => setShowCreate(true)}>
              <Plus className="mr-2 h-4 w-4" /> {t("policies.newPolicy")}
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && policies && policies.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("policies.table.name")}</TableHead>
                  <TableHead>{t("policies.table.type")}</TableHead>
                  <TableHead>{t("policies.table.artifact")}</TableHead>
                  <TableHead>{t("policies.table.status")}</TableHead>
                  <TableHead>{t("policies.table.description")}</TableHead>
                  <TableHead>{t("policies.table.tasks")}</TableHead>
                  <TableHead className="text-right">{t("policies.table.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {policies.map((policy) => (
                  <>
                    <TableRow key={policy.id}>
                      <TableCell className="font-medium">{policy.name}</TableCell>
                      <TableCell>
                        <span className="font-mono text-xs text-muted-foreground">
                          {policy.policy_type}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm">
                        <ArtifactName artifactId={policy.entity_id?.toString()} artifacts={artifacts ?? []} />
                      </TableCell>
                      <TableCell>
                        <Badge variant={policy.is_active ? "success" : "secondary"}>
                          {policy.is_active ? t("policies.table.active") : t("policies.table.inactive")}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground max-w-sm truncate">
                        {policy.description ?? "—"}
                      </TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-xs gap-1"
                          onClick={() => setExpandedId(expandedId === policy.id ? null : policy.id)}
                        >
                          <CheckSquare className="h-3.5 w-3.5" />
                          {expandedId === policy.id ? t("policies.table.hide") : t("policies.table.viewTasks")}
                        </Button>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setEditingId(editingId === policy.id ? null : policy.id)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:text-destructive"
                            onClick={() => {
                              if (confirm(t("policies.deleteConfirm", { name: policy.name })))
                                deletePolicy.mutate(policy.id);
                            }}
                            disabled={deletePolicy.isPending}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {expandedId === policy.id && (
                      <TableRow key={`tasks-${policy.id}`}>
                        <TableCell colSpan={7} className="bg-muted/10 px-6 py-3">
                          <PolicyTasksRow policyId={policy.id} />
                        </TableCell>
                      </TableRow>
                    )}
                    {editingId === policy.id && (
                      <TableRow key={`edit-${policy.id}`}>
                        <TableCell colSpan={7} className="bg-muted/20 p-4">
                          <EditPolicyRow
                            policy={policy}
                            onDone={() => setEditingId(null)}
                          />
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function PolicyTasksRow({ policyId }: { policyId: string }) {
  const { t } = useTranslation("governance");
  const { data: tasks, isLoading } = useTasksByPolicy(policyId);

  if (isLoading) return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
      <Loader2 className="h-3 w-3 animate-spin" /> {t("policies.tasks.loading")}
    </div>
  );
  if (!tasks || tasks.length === 0) return (
    <p className="text-xs text-muted-foreground py-2 italic">{t("policies.tasks.empty")}</p>
  );

  return (
    <div className="space-y-1 py-1">
      <p className="text-xs font-semibold text-muted-foreground mb-2">{t("policies.tasks.heading")}</p>
      <div className="space-y-1">
        {tasks.map((task) => (
          <div key={task.id} className="flex items-center gap-2 text-sm">
            <StatusBadge variant={
              task.status === "done" || task.status === "deployed" ? "success" :
              task.status === "in_progress" ? "default" :
              task.status === "blocked" ? "destructive" : "secondary"
            } className="text-xs shrink-0">
              {task.status.replace("_", " ")}
            </StatusBadge>
            <span className="truncate">
              <span className="text-muted-foreground">#{task.number}</span> {task.title}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function EditPolicyRow({ policy, onDone }: { policy: Policy; onDone: () => void }) {
  const { t } = useTranslation("governance");
  const updatePolicy = useUpdatePolicy(policy.id);
  function handleUpdate(values: PolicyFormValues) {
    const payload: PolicyInput = {
      ...values,
      entity_type: "artifact",
      entity_id: values.entity_id as unknown as undefined,
    };
    updatePolicy.mutate(payload, { onSuccess: onDone });
  }
  return (
    <PolicyForm
      defaultValues={{
        name: policy.name,
        description: policy.description ?? "",
        policy_type: policy.policy_type,
        is_active: policy.is_active,
        entity_id: policy.entity_id?.toString() ?? "",
      }}
      onSubmit={handleUpdate}
      onCancel={onDone}
      isSubmitting={updatePolicy.isPending}
      submitLabel={t("policies.saveChanges")}
    />
  );
}
