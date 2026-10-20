/** Script library: classified, versioned scripts per platform. System
 * scripts (ForgeHub's own: Tailscale/RustDesk install, RustDesk password)
 * are listed but locked. State: useScriptLibraryViewModel. */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Archive, ArchiveRestore, History, Loader2, Lock, Pencil, Plus, Search, Tags, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useScriptLibraryViewModel } from "@/hooks/useScriptLibraryViewModel";
import { ScriptCategoriesDialog } from "./ScriptCategoriesDialog";

export function ScriptLibrary() {
  const { t, i18n } = useTranslation("remoteAccess");
  const vm = useScriptLibraryViewModel();
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const d = vm.draft;
  const [managingCategories, setManagingCategories] = useState(false);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">{t("library.title")}</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setManagingCategories(true)} className="cursor-pointer gap-1.5">
              <Tags className="h-3.5 w-3.5" aria-hidden="true" /> {t("categories.title")}
            </Button>
            <Button type="button" size="sm" onClick={vm.startNew} className="cursor-pointer gap-1.5">
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> {t("library.new")}
            </Button>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_180px_160px_auto] sm:items-center">
          <label className="relative">
            <span className="sr-only">{t("library.search")}</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input value={vm.query} onChange={(e) => vm.setQuery(e.target.value)} placeholder={t("library.search")} className="pl-8 max-md:text-base" />
          </label>
          <Select aria-label={t("library.category")} value={vm.categoryFilter} onChange={(e) => vm.setCategoryFilter(e.target.value)} className="max-md:text-base">
            <option value="">{t("library.allCategories")}</option>
            {vm.categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </Select>
          <Select aria-label={t("library.platform")} value={vm.platformFilter} onChange={(e) => vm.setPlatformFilter(e.target.value)} className="max-md:text-base">
            <option value="">{t("composer.allOs")}</option>
            <option value="windows">Windows</option>
            <option value="linux">Linux</option>
            <option value="macos">macOS</option>
          </Select>
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={vm.showArchived} onChange={(e) => vm.setShowArchived(e.target.checked)} /> {t("library.showArchived")}
          </label>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {d && (
          <section aria-label={t(vm.editingId === "new" ? "library.new" : "library.edit")} className="space-y-3 rounded-md border border-primary/40 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">{t(vm.editingId === "new" ? "library.new" : "library.edit")}</h3>
              <button type="button" onClick={vm.cancelEdit} aria-label={t("cancel")} className="cursor-pointer text-muted-foreground hover:text-foreground"><X className="h-4 w-4" aria-hidden="true" /></button>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="lib-name">{t("library.name")}</Label>
                <Input id="lib-name" value={d.name} onChange={(e) => vm.setDraft({ name: e.target.value })} className="max-md:text-base" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="lib-category">{t("library.category")}</Label>
                <Select id="lib-category" value={d.category_id} onChange={(e) => vm.setDraft({ category_id: e.target.value })} className="max-md:text-base">
                  {vm.categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </Select>
                <div className="flex gap-2">
                  <Input aria-label={t("library.newCategory")} value={vm.newCategory} onChange={(e) => vm.setNewCategory(e.target.value)} placeholder={t("library.newCategory")} className="h-8 text-xs max-md:text-base" />
                  <Button type="button" size="sm" variant="outline" onClick={vm.addCategory} disabled={vm.newCategory.trim().length < 2} className="h-8 cursor-pointer">{t("library.addCategory")}</Button>
                </div>
                {vm.categoryError && <p className="text-xs text-destructive">{vm.categoryError}</p>}
              </div>
              <div className="space-y-1">
                <Label htmlFor="lib-platform">{t("library.platform")}</Label>
                <Select id="lib-platform" value={d.platform} onChange={(e) => vm.setDraft({ platform: e.target.value as "windows" | "linux" | "macos" })} disabled={vm.editingId !== "new"} className="max-md:text-base">
                  <option value="windows">{t("library.platforms.windows")}</option>
                  <option value="linux">{t("library.platforms.linux")}</option>
                  <option value="macos">{t("library.platforms.macos")}</option>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="lib-risk">{t("library.risk")}</Label>
                  <Select id="lib-risk" value={d.risk} onChange={(e) => vm.setDraft({ risk: e.target.value as "read" | "change" | "destructive" })} className="max-md:text-base">
                    <option value="read">{t("library.risks.read")}</option>
                    <option value="change">{t("library.risks.change")}</option>
                    <option value="destructive">{t("library.risks.destructive")}</option>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="lib-timeout">{t("run.timeout")}</Label>
                  <Input id="lib-timeout" type="number" min={5} max={1800} value={d.timeout_seconds} onChange={(e) => vm.setDraft({ timeout_seconds: Number(e.target.value) || 300 })} className="max-md:text-base" />
                </div>
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="lib-description">{t("library.description")}</Label>
              <Textarea id="lib-description" value={d.description} onChange={(e) => vm.setDraft({ description: e.target.value })} className="min-h-[60px] max-md:text-base" />
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">{t("library.parameters")}</legend>
              <p className="text-xs text-muted-foreground">{t("library.parametersHelp")}</p>
              {d.parameters.map((p, i) => (
                <div key={i} className="grid grid-cols-1 gap-2 rounded-md border border-border p-2 sm:grid-cols-[140px_minmax(0,1fr)_minmax(0,1fr)_auto_auto_auto] sm:items-center">
                  <Input aria-label={t("library.paramName")} value={p.name} onChange={(e) => vm.updateParameter(i, { name: e.target.value.toUpperCase() })} placeholder="SERVICO" className="font-mono text-xs max-md:text-base" />
                  <Input aria-label={t("library.paramLabel")} value={p.label ?? ""} onChange={(e) => vm.updateParameter(i, { label: e.target.value })} placeholder={t("library.paramLabel")} className="text-xs max-md:text-base" />
                  <Input aria-label={t("library.paramDefault")} value={p.default ?? ""} onChange={(e) => vm.updateParameter(i, { default: e.target.value })} placeholder={t("library.paramDefault")} className="text-xs max-md:text-base" />
                  <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={p.required} onChange={(e) => vm.updateParameter(i, { required: e.target.checked })} /> {t("library.required")}</label>
                  <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={p.secret} onChange={(e) => vm.updateParameter(i, { secret: e.target.checked })} /> {t("library.secret")}</label>
                  <button type="button" onClick={() => vm.removeParameter(i)} aria-label={t("library.removeParam")} className="cursor-pointer text-muted-foreground hover:text-destructive"><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
                </div>
              ))}
              <Button type="button" size="sm" variant="outline" onClick={vm.addParameter} className="cursor-pointer gap-1.5"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> {t("library.addParam")}</Button>
            </fieldset>
            <div className="space-y-1">
              <Label htmlFor="lib-content">{t("library.content")}</Label>
              <Textarea id="lib-content" value={d.content} onChange={(e) => vm.setDraft({ content: e.target.value })} className="min-h-[200px] font-mono text-xs max-md:text-base" spellCheck={false} />
            </div>
            {vm.editingId !== "new" && (
              <div className="space-y-1">
                <Label htmlFor="lib-note">{t("library.note")}</Label>
                <Input id="lib-note" value={d.note} onChange={(e) => vm.setDraft({ note: e.target.value })} className="max-md:text-base" />
              </div>
            )}
            {vm.saveError && <p role="alert" className="text-xs text-destructive">{vm.saveError}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={vm.cancelEdit} disabled={vm.saving} className="cursor-pointer">{t("cancel")}</Button>
              <Button type="button" size="sm" onClick={vm.save} disabled={vm.saving || d.name.trim().length < 2 || !d.content.trim() || !d.category_id} className="cursor-pointer gap-1.5">
                {vm.saving && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}{t("library.save")}
              </Button>
            </div>
          </section>
        )}

        {vm.status === "loading" ? (
          <p className="text-sm text-muted-foreground" role="status">{t("loading")}</p>
        ) : vm.status === "error" ? (
          <p className="text-sm text-destructive" role="alert">{t("library.loadFailed")}</p>
        ) : vm.grouped.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("library.empty")}</p>
        ) : (
          vm.grouped.map((group) => (
            <section key={group.categoryId} aria-label={group.label}>
              <h3 className="mb-2 text-sm font-semibold">{group.label}</h3>
              <ul className="divide-y divide-border rounded-md border border-border">
                {group.scripts.map((s) => (
                  <li key={s.id} className="space-y-1 px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{s.name}</span>
                      <Badge variant="outline">{t(`os.${s.platform}`)}</Badge>
                      <Badge variant={s.risk === "destructive" ? "destructive" : s.risk === "change" ? "warning" : "secondary"}>{t(`library.risks.${s.risk}`)}</Badge>
                      {s.is_system && <Badge variant="outline" className="gap-1"><Lock className="h-3 w-3" aria-hidden="true" />{t("library.system")}</Badge>}
                      {s.archived && <Badge variant="outline">{t("library.archived")}</Badge>}
                      <span className="text-xs text-muted-foreground">v{s.current_version}</span>
                      <span className="ml-auto flex gap-1">
                        <Button type="button" size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => vm.showVersions(vm.versionsOf === s.id ? null : s.id)} aria-label={t("library.versionsFor", { name: s.name })} title={t("library.versions")}>
                          <History className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        {!s.is_system && (
                          <>
                            <Button type="button" size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => vm.startEdit(s)} aria-label={t("library.editFor", { name: s.name })} title={t("library.edit")}>
                              <Pencil className="h-4 w-4" aria-hidden="true" />
                            </Button>
                            <Button type="button" size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => vm.toggleArchive(s)} aria-label={t(s.archived ? "library.restoreFor" : "library.archiveFor", { name: s.name })} title={t(s.archived ? "library.restore" : "library.archive")}>
                              {s.archived ? <ArchiveRestore className="h-4 w-4" aria-hidden="true" /> : <Archive className="h-4 w-4" aria-hidden="true" />}
                            </Button>
                          </>
                        )}
                      </span>
                    </div>
                    {s.description && <p className="text-xs text-muted-foreground">{s.description}</p>}
                    {vm.versionsOf === s.id && (
                      <ul className="mt-2 space-y-2">
                        {vm.versions.map((v) => (
                          <li key={v.version} className="rounded-md border border-border p-2">
                            <p className="text-xs text-muted-foreground">
                              v{v.version} · {v.changed_by} · {fmt.format(new Date(v.created_at))}{v.note ? ` · ${v.note}` : ""}
                            </p>
                            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre rounded bg-muted/40 p-2 font-mono text-[11px]">{v.content}</pre>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </CardContent>
      {managingCategories && <ScriptCategoriesDialog onClose={() => setManagingCategories(false)} />}
    </Card>
  );
}
