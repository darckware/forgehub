/** Rotation on demand (decision 2): the darckware password or the SSH key of
 * one or more Ready machines, run as one execution. Opens as a right-hand
 * panel (2026-11-11). State: useRotationViewModel. */
import { useTranslation } from "react-i18next";
import { KeyRound, Loader2, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SidePanel } from "@/components/ui/side-panel";
import type { RotationKind } from "@/hooks/useHostInventory";
import { useRotationViewModel } from "@/hooks/useRotationViewModel";

export function RotationDialog({ kind, onClose, onExecution }: { kind: RotationKind; onClose: () => void; onExecution: (id: string) => void }) {
  const { t } = useTranslation("remoteAccess");
  const vm = useRotationViewModel(kind, onExecution);
  const busy = vm.status === "submitting";
  const Icon = kind === "ssh_key" ? KeyRound : RotateCw;

  return (
    <SidePanel
      onClose={onClose}
      busy={busy}
      titleId="rotation-title"
      icon={<Icon className="h-4 w-4" aria-hidden="true" />}
      title={t(`rotation.${kind}.title`)}
      closeLabel={t("cancel")}
      bodyClassName="space-y-3"
      footer={vm.status === "idle" ? (
        <>
          <Button type="button" variant="outline" size="sm" onClick={onClose} className="cursor-pointer">{t("cancel")}</Button>
          <Button type="button" size="sm" onClick={vm.review} disabled={vm.selected.size === 0} className="cursor-pointer">{t("run.review")}</Button>
        </>
      ) : (
        <>
          <Button type="button" variant="outline" size="sm" onClick={vm.back} disabled={busy} className="cursor-pointer">{t("run.back")}</Button>
          <Button type="button" size="sm" onClick={vm.submit} disabled={busy} className="cursor-pointer gap-1.5">
            {busy && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
            {t("rotation.run", { count: vm.selected.size })}
          </Button>
        </>
      )}
    >
      <p className="text-sm text-muted-foreground">{t(`rotation.${kind}.help`)}</p>
      {vm.status === "idle" ? (
        <>
          <div className="flex items-center justify-between text-xs">
            <span>{t("rotation.selected", { count: vm.selected.size })}</span>
            <button type="button" onClick={vm.selectAll} className="cursor-pointer text-primary hover:underline">{t("rotation.selectAll")}</button>
          </div>
          <ul className="divide-y divide-border rounded-md border border-border">
            {vm.candidates.length === 0 && <li className="p-3 text-sm text-muted-foreground">{t("rotation.none")}</li>}
            {vm.candidates.map((m) => (
              <li key={m.id}>
                <label className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm">
                  <input type="checkbox" checked={vm.selected.has(m.id)} onChange={() => vm.toggle(m.id)} />
                  <span className="font-medium">{m.name}</span>
                  <span className="text-xs text-muted-foreground">{[m.os_family ? t(`os.${m.os_family}`) : null, m.darckware_client_name].filter(Boolean).join(" · ")}</span>
                </label>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="text-sm">{t("rotation.confirm", { count: vm.selected.size })}</p>
      )}
      {vm.error && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
    </SidePanel>
  );
}
