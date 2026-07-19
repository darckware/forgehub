import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Loader2, Plus, Pencil, Trash2, X, Save, ChevronDown, ChevronRight,
  Download, GitBranch,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  usePipelineTemplates, useCreateTemplate, useUpdateTemplate, useDeleteTemplate,
  useTemplateStages, useCreateTemplateStage, useUpdateTemplateStage, useDeleteTemplateStage,
  useImportPipelineAsTemplate, usePipelines, STAGE_TYPES,
  type PipelineTemplate, type TemplateStage,
} from "@/hooks/usePipeline";

// --------------------------------------------------------------------------
// Stage row (view + inline edit)
// --------------------------------------------------------------------------
function StageRow({ stage, templateId }: { stage: TemplateStage; templateId: string }) {
  const { t } = useTranslation("pipeline");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(stage.name);
  const [stageType, setStageType] = useState<string>(stage.stage_type);
  const [reqApproval, setReqApproval] = useState(stage.requires_approval);
  const [reqVerif, setReqVerif] = useState(stage.requires_verification);
  const updateMut = useUpdateTemplateStage(templateId);
  const deleteMut = useDeleteTemplateStage(templateId);

  const save = async () => {
    await updateMut.mutateAsync({ id: stage.id, name, stage_type: stageType, order_index: stage.order_index, requires_approval: reqApproval, requires_verification: reqVerif });
    setEditing(false);
  };

  if (editing) {
    return (
      <tr className="bg-muted/10">
        <td className="px-3 py-2 text-xs text-muted-foreground">{stage.order_index}</td>
        <td className="px-3 py-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} className="h-7 text-xs" />
        </td>
        <td className="px-3 py-2">
          <select value={stageType} onChange={(e) => setStageType(e.target.value)}
            className="h-7 rounded-md border border-input px-2 text-xs w-full"
            style={{ backgroundColor: "hsl(var(--background))" }}>
            {STAGE_TYPES.map((type) => <option key={type} value={type}>{t(`stageType.${type}`)}</option>)}
          </select>
        </td>
        <td className="px-3 py-2 text-center">
          <input type="checkbox" checked={reqApproval} onChange={(e) => setReqApproval(e.target.checked)} />
        </td>
        <td className="px-3 py-2 text-center">
          <input type="checkbox" checked={reqVerif} onChange={(e) => setReqVerif(e.target.checked)} />
        </td>
        <td className="px-3 py-2">
          <div className="flex gap-1 justify-end">
            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={save} disabled={updateMut.isPending}>
              {updateMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            </Button>
            <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing(false)}>
              <X className="h-3 w-3" />
            </Button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="hover:bg-muted/20 group">
      <td className="px-3 py-2 text-xs text-muted-foreground">{stage.order_index}</td>
      <td className="px-3 py-2 text-sm font-medium">{stage.name}</td>
      <td className="px-3 py-2"><Badge variant="outline" className="text-xs">{t(`stageType.${stage.stage_type}`)}</Badge></td>
      <td className="px-3 py-2 text-center text-xs">{stage.requires_approval ? "✓" : "—"}</td>
      <td className="px-3 py-2 text-center text-xs">{stage.requires_verification ? "✓" : "—"}</td>
      <td className="px-3 py-2">
        <div className="flex gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
          <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing(true)} title={t("templates.stageRow.editTitle")}>
            <Pencil className="h-3 w-3" />
          </Button>
          <Button size="icon" variant="ghost" className="h-6 w-6 text-destructive hover:text-destructive"
            onClick={() => deleteMut.mutate(stage.id)} disabled={deleteMut.isPending} title={t("templates.stageRow.deleteTitle")}>
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </td>
    </tr>
  );
}

// --------------------------------------------------------------------------
// Add stage form
// --------------------------------------------------------------------------
function AddStageForm({ templateId, nextOrder, onDone }: { templateId: string; nextOrder: number; onDone: () => void }) {
  const { t } = useTranslation("pipeline");
  const [name, setName] = useState("");
  const [stageType, setStageType] = useState<string>(STAGE_TYPES[0]);
  const createMut = useCreateTemplateStage();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await createMut.mutateAsync({ template_id: templateId, name, stage_type: stageType, order_index: nextOrder });
    setName("");
    onDone();
  };

  return (
    <form onSubmit={submit} className="flex gap-2 items-end px-3 py-2 border-t border-border/50">
      <div className="flex-1 flex flex-col gap-1">
        <Label className="text-xs">{t("templates.addStageForm.nameLabel")}</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} required className="h-7 text-xs" placeholder={t("templates.addStageForm.namePlaceholder")} />
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-xs">{t("templates.addStageForm.typeLabel")}</Label>
        <select value={stageType} onChange={(e) => setStageType(e.target.value)}
          className="h-7 rounded-md border border-input px-2 text-xs"
          style={{ backgroundColor: "hsl(var(--background))" }}>
          {STAGE_TYPES.map((type) => <option key={type} value={type}>{t(`stageType.${type}`)}</option>)}
        </select>
      </div>
      <Button type="submit" size="sm" className="h-7 text-xs" disabled={createMut.isPending || !name}>
        {createMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : t("templates.addStageForm.addButton")}
      </Button>
      <Button type="button" size="sm" variant="ghost" className="h-7 text-xs" onClick={onDone}>{t("templates.cancel")}</Button>
    </form>
  );
}

// --------------------------------------------------------------------------
// Template card
// --------------------------------------------------------------------------
function TemplateCard({ template }: { template: PipelineTemplate }) {
  const { t } = useTranslation("pipeline");
  const [open, setOpen] = useState(false);
  const [editingHeader, setEditingHeader] = useState(false);
  const [name, setName] = useState(template.name);
  const [description, setDescription] = useState(template.description ?? "");
  const [addingStage, setAddingStage] = useState(false);

  const { data: stages, isLoading: loadingStages } = useTemplateStages(open ? template.id : "");
  const updateMut = useUpdateTemplate(template.id);
  const deleteMut = useDeleteTemplate();

  const saveHeader = async () => {
    await updateMut.mutateAsync({ name, description: description || undefined });
    setEditingHeader(false);
  };

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        {editingHeader ? (
          <div className="flex gap-2 items-end">
            <div className="flex-1 flex flex-col gap-1">
              <Label className="text-xs">{t("templates.card.nameLabel")}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} className="h-7 text-sm" />
            </div>
            <div className="flex-1 flex flex-col gap-1">
              <Label className="text-xs">{t("templates.card.descriptionLabel")}</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} className="h-7 text-sm" placeholder={t("templates.optionalPlaceholder")} />
            </div>
            <Button size="sm" className="h-7" onClick={saveHeader} disabled={updateMut.isPending}>
              {updateMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            </Button>
            <Button size="sm" variant="ghost" className="h-7" onClick={() => setEditingHeader(false)}><X className="h-3.5 w-3.5" /></Button>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <button type="button" onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 text-left flex-1 min-w-0">
              {open ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
              <div className="min-w-0">
                <CardTitle className="text-sm truncate">{template.name}</CardTitle>
                {template.description && <p className="text-xs text-muted-foreground truncate">{template.description}</p>}
              </div>
            </button>
            <div className="flex gap-1 shrink-0">
              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setEditingHeader(true)} title={t("templates.card.editTitle")}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive"
                onClick={() => { if (confirm(t("templates.card.deleteConfirm", { name: template.name }))) deleteMut.mutate(template.id); }}
                disabled={deleteMut.isPending} title={t("templates.card.deleteTitle")}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
      </CardHeader>

      {open && (
        <CardContent className="p-0">
          {loadingStages && (
            <div className="flex justify-center py-4">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          )}
          {stages && stages.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-y border-border/50 bg-muted/30">
                    <th className="px-3 py-1.5 text-left text-muted-foreground w-10">#</th>
                    <th className="px-3 py-1.5 text-left text-muted-foreground">{t("templates.table.nameHeader")}</th>
                    <th className="px-3 py-1.5 text-left text-muted-foreground">{t("templates.table.typeHeader")}</th>
                    <th className="px-3 py-1.5 text-center text-muted-foreground">{t("templates.table.approvalHeader")}</th>
                    <th className="px-3 py-1.5 text-center text-muted-foreground">{t("templates.table.verificationHeader")}</th>
                    <th className="px-3 py-1.5 w-16" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {stages.map((s) => <StageRow key={s.id} stage={s} templateId={template.id} />)}
                </tbody>
              </table>
            </div>
          )}
          {stages && stages.length === 0 && !addingStage && (
            <p className="px-4 py-3 text-xs text-muted-foreground italic">{t("templates.card.noStagesYet")}</p>
          )}
          {addingStage
            ? <AddStageForm templateId={template.id} nextOrder={(stages?.length ?? 0)} onDone={() => setAddingStage(false)} />
            : (
              <div className="px-3 py-2 border-t border-border/50">
                <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={() => setAddingStage(true)}>
                  <Plus className="h-3 w-3" /> {t("templates.card.addStageButton")}
                </Button>
              </div>
            )
          }
        </CardContent>
      )}
    </Card>
  );
}

// --------------------------------------------------------------------------
// Import from pipeline dialog
// --------------------------------------------------------------------------
function ImportDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("pipeline");
  const { data: pipelines } = usePipelines();
  const [pipelineId, setPipelineId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const importMut = useImportPipelineAsTemplate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await importMut.mutateAsync({ pipeline_id: pipelineId, name, description: description || undefined });
    onClose();
  };

  return (
    <Card className="border-primary/30">
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-sm flex items-center gap-2">
          <Download className="h-4 w-4" /> {t("templates.import.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <form onSubmit={submit} className="space-y-3">
          <div className="flex flex-col gap-1">
            <Label className="text-xs">{t("templates.import.sourceLabel")}</Label>
            <select value={pipelineId} onChange={(e) => setPipelineId(e.target.value)} required
              className="h-9 rounded-md border border-input px-3 text-sm"
              style={{ backgroundColor: "hsl(var(--background))" }}>
              <option value="">{t("templates.import.selectPlaceholder")}</option>
              {pipelines?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <Label className="text-xs">{t("templates.import.nameLabel")}</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} required className="h-8 text-sm" placeholder={t("templates.import.namePlaceholder")} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs">{t("templates.card.descriptionLabel")}</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} className="h-8 text-sm" placeholder={t("templates.optionalPlaceholder")} />
            </div>
          </div>
          {importMut.isError && <p className="text-xs text-destructive">{(importMut.error as Error).message}</p>}
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>{t("templates.cancel")}</Button>
            <Button type="submit" size="sm" disabled={importMut.isPending || !pipelineId || !name} className="gap-1.5">
              {importMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              {t("templates.import.importButton")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------
export default function PipelineTemplatesPage() {
  const { t } = useTranslation("pipeline");
  const { data: templates, isLoading } = usePipelineTemplates();
  const createMut = useCreateTemplate();
  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await createMut.mutateAsync({ name: newName, description: newDesc || undefined });
    setNewName(""); setNewDesc(""); setShowCreate(false);
  };

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <GitBranch className="h-5 w-5" /> {t("templates.pageTitle")}
        </h1>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => { setShowImport((v) => !v); setShowCreate(false); }}>
            <Download className="h-4 w-4" /> {t("templates.importPipelineButton")}
          </Button>
          <Button size="sm" className="gap-1.5" onClick={() => { setShowCreate((v) => !v); setShowImport(false); }}>
            <Plus className="h-4 w-4" /> {t("templates.newTemplateButton")}
          </Button>
        </div>
      </div>

      {showImport && <ImportDialog onClose={() => setShowImport(false)} />}

      {showCreate && (
        <Card>
          <CardContent className="pt-4 pb-4">
            <form onSubmit={handleCreate} className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <Label>{t("templates.create.nameLabel")}</Label>
                <Input value={newName} onChange={(e) => setNewName(e.target.value)} required placeholder={t("templates.create.namePlaceholder")} />
              </div>
              <div className="flex flex-col gap-1">
                <Label>{t("templates.card.descriptionLabel")}</Label>
                <Input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder={t("templates.optionalPlaceholder")} />
              </div>
              {createMut.isError && <p className="col-span-2 text-xs text-destructive">{(createMut.error as Error).message}</p>}
              <div className="col-span-2 flex gap-2 justify-end">
                <Button type="button" variant="ghost" size="sm" onClick={() => setShowCreate(false)}>{t("templates.cancel")}</Button>
                <Button type="submit" size="sm" disabled={createMut.isPending || !newName} className="gap-1.5">
                  {createMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                  {t("templates.create.submitButton")}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {isLoading && <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>}

      {templates?.length === 0 && !isLoading && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <GitBranch className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">{t("templates.emptyDescription")}</p>
          </CardContent>
        </Card>
      )}

      {templates?.map((template) => <TemplateCard key={template.id} template={template} />)}
    </div>
  );
}
