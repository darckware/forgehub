import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { conversionSchema, useDarckwareClients, type ConversionInput } from "@/hooks/useClientOps";
import { conversionDefaults, type ClientConversionsViewModel } from "@/hooks/useClientConversionsViewModel";
import { ContractFields, DialogShell } from "./ContractFields";

export function ConversionDialog({ vm }: { vm: ClientConversionsViewModel }) {
  const { t } = useTranslation("clientOps");
  const dialog = vm.dialog!;
  const clients = useDarckwareClients();
  const form = useForm<ConversionInput>({
    resolver: zodResolver(conversionSchema),
    defaultValues: conversionDefaults(dialog),
  });
  const { register, formState } = form;
  const submitting = vm.status === "submitting";
  const errorText = (name: keyof ConversionInput) => {
    const message = formState.errors[name]?.message;
    return message ? <span className="text-xs text-destructive">{t(`contract.errors.${String(message)}`)}</span> : null;
  };
  const leadNotes = dialog.mode === "approve" ? dialog.proposal.payload.notes : null;

  const text = (name: "company_name" | "contact_name" | "email" | "phone" | "department", label: string) => (
    <div className="space-y-1">
      <Label htmlFor={`cv-${name}`}>{label}</Label>
      <Input id={`cv-${name}`} className="max-md:text-base" {...register(name)} />
      {errorText(name)}
    </div>
  );

  return (
    <DialogShell
      wide
      title={t(dialog.mode === "approve" ? "conversions.approveTitle" : "conversions.convertTitle")}
      onClose={vm.close}
    >
      <p className="text-sm text-muted-foreground">{t("conversions.explain")}</p>
      {leadNotes && (
        <div className="rounded-md border bg-muted/40 p-3 text-sm">
          <span className="font-medium">{t("conversions.leadNotes")}: </span>
          <span className="whitespace-pre-wrap break-words">{leadNotes}</span>
        </div>
      )}
      <FormProvider {...form}>
        <form onSubmit={form.handleSubmit((input) => vm.submit(input))} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="cv-existing">{t("conversions.linkExisting")}</Label>
            <Select id="cv-existing" className="max-md:text-base" {...register("existing_client_account_id")}>
              <option value="">{t("conversions.newClient")}</option>
              {(clients.data?.items ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.company_name}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {text("company_name", t("conversions.company"))}
            {text("contact_name", t("conversions.contact"))}
            {text("email", t("conversions.email"))}
            {text("phone", t("conversions.phone"))}
          </div>
          <ContractFields prefix="contract." />
          {dialog.mode === "convert" && (
            <div className="space-y-1">
              <Label htmlFor="cv-notes">{t("conversions.notes")}</Label>
              <Textarea
                id="cv-notes"
                rows={2}
                className="max-md:text-base"
                value={vm.notes}
                onChange={(e) => vm.setNotes(e.target.value)}
              />
            </div>
          )}
          {vm.errorMessage && <p className="break-words text-sm text-destructive">{vm.errorMessage}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={vm.close} disabled={submitting}>
              {t("contract.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t(dialog.mode === "approve" ? "conversions.approve" : "conversions.convert")}
            </Button>
          </div>
        </form>
      </FormProvider>
    </DialogShell>
  );
}
