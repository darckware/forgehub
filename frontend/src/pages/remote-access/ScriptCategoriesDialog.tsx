/** Script library › "Classificações": the classifications scripts are filed
 * under (Tailscale, RustDesk, Contas de usuário, ...). Rename and describe any;
 * delete only an unused one ForgeHub doesn't ship. State:
 * useScriptCategoriesViewModel. */
import { useTranslation } from "react-i18next";
import { Check, Loader2, Lock, Pencil, Plus, Tags, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { useScriptCategoriesViewModel } from "@/hooks/useScriptCategoriesViewModel";

export function ScriptCategoriesDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("remoteAccess");
  const vm = useScriptCategoriesViewModel();
  const busy = vm.status === "submitting";

  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true" aria-labelledby="categories-title">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 my-auto w-full max-w-2xl rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id="categories-title" className="flex items-center gap-2 text-base font-semibold">
            <Tags className="h-4 w-4" aria-hidden="true" /> {t("categories.title")}
          </h2>
          <button type="button" onClick={onClose} aria-label={t("cancel")} className="cursor-pointer text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="space-y-4 px-6 py-4">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto]">
            <Input aria-label={t("categories.newLabel")} placeholder={t("categories.newLabel")} value={vm.newLabel} onChange={(e) => vm.setNewLabel(e.target.value)} className="max-md:text-base" />
            <Input aria-label={t("categories.description")} placeholder={t("categories.description")} value={vm.newDescription} onChange={(e) => vm.setNewDescription(e.target.value)} className="max-md:text-base" />
            <Button type="button" size="sm" onClick={vm.create} disabled={busy || vm.newLabel.trim().length < 2} className="cursor-pointer gap-1.5">
              {busy && !vm.editingId ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />} {t("categories.add")}
            </Button>
          </div>
          {vm.error && !vm.deleting && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
          {vm.status === "loading" && <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-label={t("maintenance.loading")} />}
          <ul className="divide-y divide-border rounded-md border border-border">
            {vm.categories.map((c) => (
              <li key={c.id} className="px-3 py-2 text-sm">
                {vm.editingId === c.id ? (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto]">
                    <Input aria-label={t("categories.label")} value={vm.draftLabel} onChange={(e) => vm.setDraftLabel(e.target.value)} className="max-md:text-base" />
                    <Input aria-label={t("categories.description")} value={vm.draftDescription} onChange={(e) => vm.setDraftDescription(e.target.value)} className="max-md:text-base" />
                    <div className="flex gap-1">
                      <Button type="button" size="icon" onClick={vm.saveEdit} disabled={busy || vm.draftLabel.trim().length < 2} aria-label={t("categories.save")} className="h-9 w-9 cursor-pointer">
                        {busy ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : <Check className="h-4 w-4" aria-hidden="true" />}
                      </Button>
                      <Button type="button" size="icon" variant="ghost" onClick={vm.cancelEdit} aria-label={t("cancel")} className="h-9 w-9 cursor-pointer">
                        <X className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{c.label}</span>
                    {c.is_system && <Badge variant="outline" className="gap-1"><Lock className="h-3 w-3" aria-hidden="true" />{t("library.system")}</Badge>}
                    <span className="text-xs text-muted-foreground">{t("categories.count", { count: c.script_count ?? 0 })}</span>
                    {c.description && <span className="w-full text-xs text-muted-foreground">{c.description}</span>}
                    <span className="ml-auto flex gap-1">
                      <Button type="button" size="icon" variant="ghost" onClick={() => vm.startEdit(c)} aria-label={t("categories.editFor", { name: c.label })} className="h-8 w-8 cursor-pointer">
                        <Pencil className="h-4 w-4" aria-hidden="true" />
                      </Button>
                      <Button type="button" size="icon" variant="ghost" onClick={() => vm.askDelete(c)} disabled={!vm.canDelete(c)}
                        aria-label={t("categories.deleteFor", { name: c.label })} title={vm.canDelete(c) ? undefined : t(c.is_system ? "categories.systemLocked" : "categories.inUse")}
                        className="h-8 w-8 cursor-pointer text-destructive hover:text-destructive">
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <ConfirmDialog
        open={vm.deleting !== null}
        title={t("categories.deleteTitle", { name: vm.deleting?.label ?? "" })}
        description={t("categories.deleteText")}
        confirmLabel={t("categories.delete")}
        loading={vm.deletePending}
        error={vm.deleting ? vm.error : undefined}
        onConfirm={vm.confirmDelete}
        onCancel={vm.cancelDelete}
      />
    </div>
  );
}
