import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { clientAccountSchema, type ClientAccountInput } from "@/hooks/useClientOps";
import { clientFormDefaults, type ClientProfileViewModel } from "@/hooks/useClientProfileViewModel";
import { DialogShell } from "./ContractFields";

/** Create or edit a client's data (company, primary contact). */
export function ClientDialog({ vm }: { vm: ClientProfileViewModel }) {
  const { t } = useTranslation("clientOps");
  const dialog = vm.dialog!;
  const { register, handleSubmit, formState } = useForm<ClientAccountInput>({
    resolver: zodResolver(clientAccountSchema),
    defaultValues: clientFormDefaults(dialog.mode === "edit" ? dialog.client : undefined),
  });
  const submitting = vm.status === "submitting";
  const field = (name: keyof ClientAccountInput, label: string, type = "text") => {
    const message = formState.errors[name]?.message;
    return (
      <div className="space-y-1">
        <Label htmlFor={`cl-${name}`}>{label}</Label>
        <Input id={`cl-${name}`} type={type} className="max-md:text-base" {...register(name)} />
        {message && (
          <span className="text-xs text-destructive">{t(`contract.errors.${String(message)}`, t("contract.errors.invalid"))}</span>
        )}
      </div>
    );
  };

  return (
    <DialogShell title={t(dialog.mode === "edit" ? "client.editTitle" : "client.newTitle")} onClose={vm.closeDialog}>
      <p className="text-sm text-muted-foreground">{t(dialog.mode === "edit" ? "client.editExplain" : "client.newExplain")}</p>
      <form onSubmit={handleSubmit((input) => vm.submit(input))} className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {field("company_name", t("conversions.company"))}
          {field("contact_name", t("conversions.contact"))}
          {field("email", t("conversions.email"), "email")}
          {field("phone", t("conversions.phone"), "tel")}
          {field("department", t("conversions.department"))}
        </div>
        {vm.errorMessage && <p className="break-words text-sm text-destructive">{vm.errorMessage}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" onClick={vm.closeDialog} disabled={submitting}>
            {t("contract.cancel")}
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t(dialog.mode === "edit" ? "contract.save" : "client.create")}
          </Button>
        </div>
      </form>
    </DialogShell>
  );
}
