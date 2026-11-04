import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/store/authStore";
import { useServiceLineViewModel } from "@/hooks/useServiceLineViewModel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export function ServiceLinesCard() {
  const { t } = useTranslation("product");
  const admin = useAuthStore((s) => s.user?.is_admin);
  const vm = useServiceLineViewModel();
  const { register, handleSubmit, formState: { errors } } = vm.form;
  const fields = ["description", "stages", "required_documents", "evidence_types", "default_agents"] as const;
  return <Card><CardHeader><CardTitle>{t("serviceLines.title")}</CardTitle></CardHeader>
    <CardContent className="space-y-4">
      {vm.lines.isError && <p role="alert">{t("serviceLines.loadError")}</p>}
      <div className="space-y-2">{vm.lines.data?.map((line) => <div key={line.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3">
        <span className="min-w-0 break-words">{line.name} {!line.is_active && `(${t("serviceLines.inactive")})`}</span>
        {admin && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => vm.edit(line)}>{t("serviceLines.edit")}</Button>
          {line.is_active && <Button size="sm" variant="outline" onClick={() => { vm.deactivate.reset(); vm.setPending(line); }}>{t("serviceLines.deactivate")}</Button>}</div>}
      </div>)}</div>
      {admin && !vm.showForm && <Button onClick={() => vm.edit(null)}>{t("serviceLines.add")}</Button>}
      {admin && vm.showForm && <form onSubmit={handleSubmit((values) => vm.save.mutate(values))} className="space-y-3">
        {(["slug", "name"] as const).map((field) => <div key={field} className="space-y-1"><Label htmlFor={`service-${field}`}>{t(`serviceLines.${field}`)}</Label>
          <Input id={`service-${field}`} {...register(field)} />{errors[field] && <p role="alert">{t("serviceLines.invalid")}</p>}</div>)}
        {fields.map((field) => <div key={field} className="space-y-1"><Label htmlFor={`service-${field}`}>{t(`serviceLines.${field}`)}</Label>
          <Textarea id={`service-${field}`} {...register(field)} />{field !== "description" && <p className="text-xs text-muted-foreground">{t("serviceLines.onePerLine")}</p>}</div>)}
        {(["sla_hours", "darckware_contract_type"] as const).map((field) => <div key={field} className="space-y-1"><Label htmlFor={`service-${field}`}>{t(`serviceLines.${field}`)}</Label>
          <Input id={`service-${field}`} {...register(field)} />{errors[field] && <p role="alert">{t("serviceLines.invalid")}</p>}</div>)}
        <label className="flex items-center gap-2"><input type="checkbox" {...register("client_visible")} />{t("serviceLines.client_visible")}</label>
        {vm.save.isError && <p role="alert">{t("serviceLines.saveError")}</p>}
        <div className="flex gap-2"><Button type="submit" disabled={vm.save.isPending}>{t("serviceLines.save")}</Button>
          <Button type="button" variant="outline" onClick={() => vm.setShowForm(false)}>{t("serviceLines.cancel")}</Button></div>
      </form>}
      <ConfirmDialog open={Boolean(vm.pending)} title={t("serviceLines.confirmTitle")} description={t("serviceLines.confirmDescription", { name: vm.pending?.name })}
        confirmLabel={t("serviceLines.deactivate")} loading={vm.deactivate.isPending} error={vm.deactivate.isError ? t("serviceLines.deactivateError") : null}
        onCancel={() => vm.setPending(null)} onConfirm={() => vm.pending && vm.deactivate.mutate(vm.pending.id)} />
    </CardContent></Card>;
}
