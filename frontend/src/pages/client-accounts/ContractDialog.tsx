import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { contractSchema, type ContractInput } from "@/hooks/useClientOps";
import { contractDefaults, type ClientAccountViewModel } from "@/hooks/useClientAccountViewModel";
import { ContractFields, DialogShell } from "./ContractFields";

export function ContractDialog({ vm }: { vm: ClientAccountViewModel }) {
  const { t } = useTranslation("clientOps");
  const dialog = vm.contractDialog!;
  const form = useForm<ContractInput>({
    resolver: zodResolver(contractSchema),
    defaultValues: contractDefaults(dialog.mode === "edit" ? dialog.contract : undefined),
  });
  const submitting = vm.status === "submitting";

  return (
    <DialogShell
      title={t(dialog.mode === "edit" ? "accounts.editContract" : "accounts.newContract")}
      onClose={vm.closeContract}
    >
      <FormProvider {...form}>
        <form onSubmit={form.handleSubmit((input) => vm.submitContract(input))} className="space-y-4">
          <ContractFields lockType={dialog.mode === "edit"} />
          {vm.errorMessage && <p className="break-words text-sm text-destructive">{vm.errorMessage}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" onClick={vm.closeContract} disabled={submitting}>
              {t("contract.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("contract.save")}
            </Button>
          </div>
        </form>
      </FormProvider>
    </DialogShell>
  );
}
