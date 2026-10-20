import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { clientAccountSchema, type ClientAccountInput } from "@/hooks/useClientOps";
import { clientFormDefaults, registrationDefaults, type ClientProfileViewModel } from "@/hooks/useClientProfileViewModel";
import { DialogShell } from "./ContractFields";

/** Create or edit a client's data (company registry, address, primary contact). */
export function ClientDialog({ vm }: { vm: ClientProfileViewModel }) {
  const { t } = useTranslation("clientOps");
  const dialog = vm.dialog!;
  const { register, handleSubmit, formState } = useForm<ClientAccountInput>({
    resolver: zodResolver(clientAccountSchema),
    defaultValues:
      dialog.mode === "approve"
        ? registrationDefaults(dialog.registration)
        : clientFormDefaults(dialog.mode === "edit" ? dialog.client : undefined),
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
    <DialogShell title={t(`client.${dialog.mode === "create" ? "new" : dialog.mode}Title`)} onClose={vm.closeDialog}>
      <p className="text-sm text-muted-foreground">
        {dialog.mode === "approve"
          ? t("registrations.approveExplain", { who: dialog.registration.proposed_by })
          : t(`client.${dialog.mode === "create" ? "new" : dialog.mode}Explain`)}
      </p>
      {dialog.mode === "approve" && dialog.registration.payload.note && (
        <p className="whitespace-pre-wrap rounded-md border bg-muted/40 p-2 text-sm">{dialog.registration.payload.note}</p>
      )}
      <form onSubmit={handleSubmit((input) => vm.submit(input))} className="space-y-4">
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">{t("client.sections.company")}</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {field("company_name", t("client.fields.company_name"))}
            {field("trade_name", t("client.fields.trade_name"))}
            {field("cnpj", t("client.fields.cnpj"))}
            {field("company_phone", t("client.fields.company_phone"), "tel")}
          </div>
        </fieldset>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">{t("client.sections.address")}</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-6">
            <div className="sm:col-span-2">{field("address_zip", t("client.fields.address_zip"))}</div>
            <div className="sm:col-span-4">{field("address_street", t("client.fields.address_street"))}</div>
            <div className="sm:col-span-2">{field("address_number", t("client.fields.address_number"))}</div>
            <div className="sm:col-span-4">{field("address_complement", t("client.fields.address_complement"))}</div>
            <div className="sm:col-span-2">{field("address_district", t("client.fields.address_district"))}</div>
            <div className="sm:col-span-3">{field("address_city", t("client.fields.address_city"))}</div>
            <div className="sm:col-span-1">{field("address_state", t("client.fields.address_state"))}</div>
          </div>
        </fieldset>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">{t("client.sections.contact")}</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {field("contact_name", t("conversions.contact"))}
            {field("email", t("conversions.email"), "email")}
            {field("phone", t("conversions.phone"), "tel")}
            {field("department", t("conversions.department"))}
          </div>
        </fieldset>
        {vm.errorMessage && <p className="break-words text-sm text-destructive">{vm.errorMessage}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" onClick={vm.closeDialog} disabled={submitting}>
            {t("contract.cancel")}
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t(dialog.mode === "edit" ? "contract.save" : dialog.mode === "approve" ? "registrations.approve" : "client.create")}
          </Button>
        </div>
      </form>
    </DialogShell>
  );
}
