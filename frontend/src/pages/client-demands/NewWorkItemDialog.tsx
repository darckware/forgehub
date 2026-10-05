import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateWorkItem,
  useClientOpsText,
  useDarckwareClients,
  workItemCreateSchema,
  type WorkItemCreateInput,
  type WorkItemDetail,
} from "@/hooks/useClientOps";

/** Launches a client demand from ForgeHub; it is stored in Darckware, not here. */
export function NewWorkItemDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (item: WorkItemDetail) => void;
}) {
  const { t } = useTranslation("clientOps");
  const { errorText } = useClientOpsText();
  const clients = useDarckwareClients();
  const create = useCreateWorkItem();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<WorkItemCreateInput>({
    resolver: zodResolver(workItemCreateSchema),
    defaultValues: { kind: "demand", tipo: "servico", priority: "media", client_account_id: "", title: "", description: "" },
  });

  if (!open) return null;

  const submit = handleSubmit(async (values) => {
    const created = await create.mutateAsync(values);
    reset();
    onCreated(created);
  });

  const clientItems = clients.data?.items ?? [];
  const required = <span className="text-xs text-destructive">{t("demands.form.required")}</span>;

  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4">
      <div className="fixed inset-0 bg-black/60" onClick={onClose} aria-hidden />
      <form
        onSubmit={(e) => void submit(e)}
        className="relative my-auto w-full max-w-lg space-y-4 rounded-lg border bg-background p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold">{t("demands.form.title")}</h2>

        <div className="space-y-1">
          <Label htmlFor="wi-kind">{t("demands.form.kind")}</Label>
          <Select id="wi-kind" className="max-md:text-base" {...register("kind")}>
            <option value="demand">{t("kind.demand")}</option>
            <option value="ticket">{t("kind.ticket")}</option>
          </Select>
          <p className="text-xs text-muted-foreground">{t("demands.form.kindHelp")}</p>
        </div>

        <div className="space-y-1">
          <Label htmlFor="wi-client">{t("demands.form.client")}</Label>
          <Select id="wi-client" className="max-md:text-base" {...register("client_account_id")}>
            <option value="">{t("demands.form.chooseClient")}</option>
            {clientItems.map((c) => (
              <option key={c.id} value={c.id}>
                {c.company_name}
              </option>
            ))}
          </Select>
          {clients.isSuccess && clientItems.length === 0 && (
            <p className="text-xs text-muted-foreground">{t("demands.form.noClients")}</p>
          )}
          {errors.client_account_id && required}
        </div>

        <div className="space-y-1">
          <Label htmlFor="wi-title">{t("demands.form.subject")}</Label>
          <Input id="wi-title" className="max-md:text-base" {...register("title")} />
          {errors.title && required}
        </div>

        <div className="space-y-1">
          <Label htmlFor="wi-description">{t("demands.form.description")}</Label>
          <Textarea id="wi-description" rows={5} className="max-md:text-base" {...register("description")} />
          {errors.description && required}
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="wi-tipo">{t("demands.form.tipo")}</Label>
            <Select id="wi-tipo" className="max-md:text-base" {...register("tipo")}>
              <option value="servico">{t("tipo.servico")}</option>
              <option value="desenvolvimento">{t("tipo.desenvolvimento")}</option>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="wi-priority">{t("demands.form.priority")}</Label>
            <Select id="wi-priority" className="max-md:text-base" {...register("priority")}>
              {(["baixa", "media", "alta", "urgente"] as const).map((p) => (
                <option key={p} value={p}>
                  {t(`priority.${p}`)}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {create.isError && <p className="text-sm text-destructive">{errorText(create.error)}</p>}

        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t("demands.dialog.cancel")}
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("demands.form.save")}
          </Button>
        </div>
      </form>
    </div>
  );
}
