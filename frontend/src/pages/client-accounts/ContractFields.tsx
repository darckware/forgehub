import { useFormContext, type FieldErrors, type FieldValues } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

/**
 * Contract fields, shared by the contract dialog and the conversion dialog.
 * `prefix` is "" for a bare contract form and "contract." when nested.
 * Which fields show follows the type: monthly quota/price for hourly support,
 * total value/scope for development -- the same split Darckware validates.
 */
export function ContractFields({ prefix = "", lockType = false }: { prefix?: "" | "contract."; lockType?: boolean }) {
  const { t } = useTranslation("clientOps");
  const { register, watch, formState } = useFormContext<FieldValues>();
  const type = watch(`${prefix}contract_type`);
  const errors = (prefix ? (formState.errors.contract as FieldErrors | undefined) : formState.errors) ?? {};
  const field = (name: string) => `${prefix}${name}`;
  const error = (name: string) => {
    const message = errors[name]?.message;
    return message ? (
      <span className="text-xs text-destructive">{t(`contract.errors.${String(message)}`, t("contract.errors.invalid"))}</span>
    ) : null;
  };
  const numberInput = (name: string, step = "0.01") => (
    <div className="space-y-1">
      <Label htmlFor={`ct-${name}`}>{t(`contract.fields.${name}`)}</Label>
      <Input
        id={`ct-${name}`}
        type="number"
        step={step}
        inputMode="decimal"
        className="max-md:text-base"
        {...register(field(name), { valueAsNumber: true })}
      />
      {error(name)}
    </div>
  );

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="ct-contract_type">{t("contract.fields.contract_type")}</Label>
          <Select
            id="ct-contract_type"
            // Read-only rather than `disabled`: RHF drops a disabled field's value,
            // which would fail validation on edit (the type is fixed once created).
            className={lockType ? "pointer-events-none opacity-70 max-md:text-base" : "max-md:text-base"}
            aria-readonly={lockType || undefined}
            tabIndex={lockType ? -1 : undefined}
            {...register(field("contract_type"))}
          >
            <option value="suporte_horas">{t("contract.type.suporte_horas")}</option>
            <option value="desenvolvimento">{t("contract.type.desenvolvimento")}</option>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="ct-plan_name">{t("contract.fields.plan_name")}</Label>
          <Input id="ct-plan_name" className="max-md:text-base" {...register(field("plan_name"))} />
          {error("plan_name")}
        </div>
      </div>

      {type === "suporte_horas" ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {numberInput("monthly_hours_quota", "0.5")}
          {numberInput("monthly_price")}
          {numberInput("extra_hour_rate")}
          {numberInput("billing_cycle_day", "1")}
        </div>
      ) : (
        <div className="space-y-3">
          {numberInput("total_value")}
          <div className="space-y-1">
            <Label htmlFor="ct-scope_summary">{t("contract.fields.scope_summary")}</Label>
            <Textarea id="ct-scope_summary" rows={3} className="max-md:text-base" {...register(field("scope_summary"))} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="ct-start_date">{t("contract.fields.start_date")}</Label>
          <Input id="ct-start_date" type="date" className="max-md:text-base" {...register(field("start_date"))} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="ct-end_date">{t("contract.fields.end_date")}</Label>
          <Input id="ct-end_date" type="date" className="max-md:text-base" {...register(field("end_date"))} />
          {error("end_date")}
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="ct-document_url">{t("contract.fields.document_url")}</Label>
        <Input id="ct-document_url" className="max-md:text-base" {...register(field("document_url"))} />
      </div>
    </div>
  );
}

/** The phone-safe overlay every dialog on these screens uses (MOBILE plan, "modals taller than a phone"). */
export function DialogShell({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4">
      <div className="fixed inset-0 bg-black/60" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        className={`relative my-auto w-full space-y-4 rounded-lg border bg-background p-5 shadow-xl ${wide ? "max-w-2xl" : "max-w-lg"}`}
      >
        <h2 className="text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}
