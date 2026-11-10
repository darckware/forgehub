import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { MESSAGE_LABEL_GROUPS } from "@/lib/messageLabels";

export function MessageLabelsLegend({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation("demands");
  return <ConfirmDialog open={open} placement="right" readOnly variant="default" title={t("messageLabels.legendTitle")} description={t("messageLabels.legendDescription")} cancelLabel={t("messageLabels.close")} closeLabel={t("messageLabels.close")} onConfirm={() => undefined} onCancel={onClose}>
    <div className="space-y-5">
      <p className="rounded-md border p-3 text-sm">{t("messageLabels.authority")}</p>
      {Object.entries(MESSAGE_LABEL_GROUPS).map(([group, labels]) => <section key={group} className="space-y-2">
        <h3 className="font-semibold">{t(`messageLabels.groups.${group}.title`)}</h3>
        <p className="text-sm text-muted-foreground">{t(`messageLabels.groups.${group}.description`)}</p>
        <dl className="space-y-3">{labels.map(label => <div key={label}>
          <dt><Badge variant="outline" className="max-w-full whitespace-normal text-xs">{t(`messageLabels.items.${label}.label`)}</Badge></dt>
          <dd className="mt-1 break-words text-sm text-muted-foreground">{t(`messageLabels.items.${label}.description`)}</dd>
        </div>)}</dl>
      </section>)}
    </div>
  </ConfirmDialog>;
}
