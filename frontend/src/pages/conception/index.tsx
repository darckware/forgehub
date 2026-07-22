import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Lightbulb, Loader2, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";
import { useDeleteProduct, useUpdateProduct } from "@/hooks/useProduct";
import {
  useAuthorizeDeliveryPlanning,
  useConcept,
  useCreateIdea,
  useDevelopmentRequests,
  usePreviewConceptSummary,
  useReviseConcept,
  useSubmitConcept,
  useUpdateConceptDeliveryMetadata,
  useUpdateDevelopmentRequest,
  type DevelopmentRequest,
  type TechStackDecision,
  type TechStackLayer,
} from "@/hooks/useSystemScope";

// UI guardrails for the idea-capture form. name/requested_by mirror the
// backend's IdeaCreate max_length=255; the Text-column fields (no DB limit)
// get a generous soft cap so the char counter has a target to show.
const NAME_MAX = 255;
const PROBLEM_STATEMENT_MAX = 4000;
const VISION_MAX = 2000;
const SCOPE_SUMMARY_MAX = 2000;
const REQUESTED_BY_MAX = 255;
const PROJECT_DESCRIPTION_MAX = 4000;

// Fixed set of layers per TECH_STACK_LAYERS (backend/app/db/models/system_scope.py)
// with the approved option list per stack/02-UI-DESIGN-SYSTEM-AND-TECHNOLOGY-SPEC.md
// (frontend tech-selection decision tree §12/§14, backend §17, data §18).
// "deploy_infra" has no dedicated section there -- Docker is the org's
// documented deploy baseline (stack/10-DEVSECOPS-CI-CD-AND-RELEASE-STANDARD.md),
// so it anchors that layer's options instead.
const TECH_STACK_LAYERS: TechStackLayer[] = ["frontend", "backend", "database", "deploy_infra"];
const TECH_STACK_OPTIONS: Record<TechStackLayer, string[]> = {
  frontend: [
    "React + Vite + shadcn/ui (SPA autenticada)",
    "Next.js + shadcn/ui (público/SEO)",
    "React + PrimeReact/MUI/Ant Design (back-office com muitos dados)",
    "React Native + Expo (mobile)",
  ],
  backend: [
    "C#/.NET — Modular Monolith (core de negócio, APIs críticas)",
    "Node.js (BFF, WebSocket, orientado a eventos)",
    "Python (IA, automação, ETL)",
  ],
  database: [
    "PostgreSQL (padrão relacional)",
    "SQL Server (ecossistema Microsoft)",
    "MongoDB (documentos, necessidade comprovada)",
    "Redis (cache, locks, sessões)",
  ],
  deploy_infra: [
    "Docker Compose (host único)",
    "Kubernetes",
    "Serverless / plataforma gerenciada",
  ],
};

type TechStackState = Record<TechStackLayer, { decision: string; rationale: string }>;

const EMPTY_TECH_STACK: TechStackState = {
  frontend: { decision: "", rationale: "" },
  backend: { decision: "", rationale: "" },
  database: { decision: "", rationale: "" },
  deploy_infra: { decision: "", rationale: "" },
};

function techStackToState(decisions: TechStackDecision[] | null | undefined): TechStackState {
  const state = { ...EMPTY_TECH_STACK };
  for (const item of decisions ?? []) {
    state[item.layer] = { decision: item.decision, rationale: item.rationale ?? "" };
  }
  return state;
}

function techStackToPayload(state: TechStackState): TechStackDecision[] {
  return TECH_STACK_LAYERS
    .filter((layer) => state[layer].decision.trim().length > 0)
    .map((layer) => ({
      layer, decision: state[layer].decision,
      rationale: state[layer].rationale.trim() ? state[layer].rationale : null,
    }));
}

function FieldLabel({ label, count, max }: { label: string; count: number; max: number }) {
  return (
    <div className="flex items-center justify-between">
      <Label>{label}</Label>
      <span className="text-xs text-muted-foreground">{count}/{max}</span>
    </div>
  );
}

const EMPTY_FORM = {
  name: "", problem_statement: "", vision: "", scope_summary: "", requested_by: "",
  project_description: "", working_directory_path: "",
};

export default function ConceptionPage() {
  const { t } = useTranslation("conception");
  const queryClient = useQueryClient();
  const requests = useDevelopmentRequests();
  const create = useCreateIdea();
  const deleteProduct = useDeleteProduct();
  const updateRequest = useUpdateDevelopmentRequest();
  const updateProduct = useUpdateProduct();
  const reviseConcept = useReviseConcept();
  const updateDeliveryMetadata = useUpdateConceptDeliveryMetadata();
  const previewSummary = usePreviewConceptSummary();
  const [selectedProduct, setSelectedProduct] = useState("");
  const concept = useConcept(selectedProduct);
  const submitConcept = useSubmitConcept();
  const authorize = useAuthorizeDeliveryPlanning();
  const [delivery, setDelivery] = useState({ version: "0.1.0", project_name: "", owner: "" });
  const [form, setForm] = useState(EMPTY_FORM);
  const [techStack, setTechStack] = useState<TechStackState>(EMPTY_TECH_STACK);
  const [wizardStep, setWizardStep] = useState<"problem" | "description" | "stack">("problem");
  const [view, setView] = useState<"list" | "form">("list");
  const [pendingDelete, setPendingDelete] = useState<{ productId: string; title: string } | null>(null);
  const [editingRequest, setEditingRequest] = useState<DevelopmentRequest | null>(null);

  // Once the concept for the product being edited loads, backfill everything
  // not present on DevelopmentRequest itself: vision/scope, the project
  // description + working directory staged in Step 2, and the Step 3 stack
  // decisions.
  useEffect(() => {
    if (!editingRequest || !concept.data) return;
    if (concept.data.concept.product_id !== editingRequest.product_id) return;
    const revision = concept.data.current_revision;
    setForm((f) => ({
      ...f,
      vision: revision?.vision ?? "",
      scope_summary: revision?.scope_summary ?? "",
      project_description: revision?.project_description ?? "",
      working_directory_path: revision?.working_directory_path ?? "",
    }));
    setTechStack(techStackToState(revision?.tech_stack_decisions));
  }, [editingRequest, concept.data]);

  const conceptEditable = !concept.data || ["draft", "rework"].includes(concept.data.concept.status);

  const startEdit = (item: DevelopmentRequest) => {
    setForm({
      name: item.title, problem_statement: item.description, vision: "", scope_summary: "",
      requested_by: item.requested_by ?? "", project_description: "", working_directory_path: "",
    });
    setTechStack(EMPTY_TECH_STACK);
    setSelectedProduct(item.product_id);
    setEditingRequest(item);
    setWizardStep("problem");
    setView("form");
  };

  const backToList = () => {
    setEditingRequest(null);
    setForm(EMPTY_FORM);
    setTechStack(EMPTY_TECH_STACK);
    setWizardStep("problem");
    setView("list");
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const tech_stack_decisions = techStackToPayload(techStack);
    if (editingRequest) {
      await updateRequest.mutateAsync({ requestId: editingRequest.id, title: form.name, description: form.problem_statement, requested_by: form.requested_by || undefined });
      await updateProduct.mutateAsync({ id: editingRequest.product_id, payload: { name: form.name } });
      if (conceptEditable && concept.data) {
        await reviseConcept.mutateAsync({
          conceptId: concept.data.concept.id, productId: editingRequest.product_id,
          problem_statement: form.problem_statement, vision: form.vision || undefined, scope_summary: form.scope_summary || undefined,
          project_description: form.project_description || undefined, working_directory_path: form.working_directory_path || undefined,
          tech_stack_decisions: tech_stack_decisions.length ? tech_stack_decisions : undefined,
        });
      } else if (concept.data) {
        // Concept content (problem/vision/scope) is frozen once submitted,
        // but delivery setup metadata isn't part of what governance
        // approves -- it can still be edited in place (see
        // update_concept_delivery_metadata's docstring).
        await updateDeliveryMetadata.mutateAsync({
          conceptId: concept.data.concept.id,
          project_description: form.project_description || undefined,
          working_directory_path: form.working_directory_path || undefined,
          tech_stack_decisions: tech_stack_decisions.length ? tech_stack_decisions : undefined,
        });
      }
    } else {
      await create.mutateAsync({
        ...form,
        project_description: form.project_description || undefined,
        working_directory_path: form.working_directory_path || undefined,
        tech_stack_decisions: tech_stack_decisions.length ? tech_stack_decisions : undefined,
      });
    }
    backToList();
  };
  const confirmDelete = () => {
    if (!pendingDelete) return;
    deleteProduct.mutate(pendingDelete.productId, {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ["conception"] });
        if (selectedProduct === pendingDelete.productId) setSelectedProduct("");
        setPendingDelete(null);
      },
    });
  };
  const saving = create.isPending || updateRequest.isPending || updateProduct.isPending || reviseConcept.isPending || updateDeliveryMetadata.isPending;
  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-2xl font-semibold">{t("page.title")}</h1><p className="text-sm text-muted-foreground">{t("page.description")}</p></div>
      <Button variant="outline" onClick={() => view === "list" ? setView("form") : backToList()}>
        {view === "list"
          ? <><Lightbulb className="mr-2 h-4 w-4"/>{t("toggle.newIdea")}</>
          : <><ArrowLeft className="mr-2 h-4 w-4"/>{t("toggle.backToList")}</>}
      </Button>
    </div>
    {view === "form" ? (
      <Card><CardHeader><CardTitle className="flex items-center gap-2 text-lg"><Lightbulb className="h-5 w-5"/>{editingRequest ? t("captureIdea.editTitle") : t("captureIdea.title")}</CardTitle><CardDescription>{editingRequest ? t("captureIdea.editDescription") : t("captureIdea.description")}</CardDescription></CardHeader>
        <form onSubmit={submit}>
        <CardContent className="space-y-4">
          <Tabs value={wizardStep} onValueChange={(value) => setWizardStep(value as typeof wizardStep)}>
            <TabsList>
              <TabsTrigger value="problem">{t("wizard.steps.problem")}</TabsTrigger>
              <TabsTrigger value="description">{t("wizard.steps.description")}</TabsTrigger>
              <TabsTrigger value="stack">{t("wizard.steps.stack")}</TabsTrigger>
            </TabsList>
            <TabsContent value="problem" className="mt-4 space-y-4">
              <div className="space-y-2"><FieldLabel label={t("captureIdea.fields.name")} count={form.name.length} max={NAME_MAX}/><Input required maxLength={NAME_MAX} value={form.name} onChange={e => setForm({...form, name:e.target.value})}/></div>
              <div className="space-y-2"><FieldLabel label={t("captureIdea.fields.problemStatement")} count={form.problem_statement.length} max={PROBLEM_STATEMENT_MAX}/><Textarea required rows={6} maxLength={PROBLEM_STATEMENT_MAX} readOnly={!conceptEditable} value={form.problem_statement} onChange={e => setForm({...form, problem_statement:e.target.value})}/></div>
              <div className="space-y-2"><FieldLabel label={t("captureIdea.fields.vision")} count={form.vision.length} max={VISION_MAX}/><Textarea rows={5} maxLength={VISION_MAX} readOnly={!conceptEditable} value={form.vision} onChange={e => setForm({...form, vision:e.target.value})}/></div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <FieldLabel label={t("captureIdea.fields.initialScope")} count={form.scope_summary.length} max={SCOPE_SUMMARY_MAX}/>
                  {editingRequest && conceptEditable && (
                    <Button
                      type="button" variant="ghost" size="sm" className="h-6 gap-1 px-2 text-xs"
                      disabled={previewSummary.isPending}
                      onClick={() => previewSummary.mutate(editingRequest.product_id, {
                        onSuccess: (data) => setForm((f) => ({ ...f, scope_summary: data.summary })),
                      })}
                    >
                      {previewSummary.isPending ? <Loader2 className="h-3 w-3 animate-spin"/> : <RefreshCw className="h-3 w-3"/>}
                      {t("wizard.updateFromDiagram")}
                    </Button>
                  )}
                </div>
                <Textarea rows={5} maxLength={SCOPE_SUMMARY_MAX} readOnly={!conceptEditable} value={form.scope_summary} onChange={e => setForm({...form, scope_summary:e.target.value})}/>
                {previewSummary.data && previewSummary.data.summary === "" && (
                  <p className="text-xs text-muted-foreground">{t("wizard.updateFromDiagramEmpty")}</p>
                )}
              </div>
              <div className="space-y-2"><FieldLabel label={t("captureIdea.fields.requestedBy")} count={form.requested_by.length} max={REQUESTED_BY_MAX}/><Input maxLength={REQUESTED_BY_MAX} value={form.requested_by} onChange={e => setForm({...form, requested_by:e.target.value})}/></div>
            </TabsContent>
            <TabsContent value="description" className="mt-4 space-y-4">
              <p className="text-sm text-muted-foreground">{t("wizard.description.help")}</p>
              <div className="space-y-2"><FieldLabel label={t("wizard.description.fields.projectDescription")} count={form.project_description.length} max={PROJECT_DESCRIPTION_MAX}/><Textarea rows={6} maxLength={PROJECT_DESCRIPTION_MAX} value={form.project_description} onChange={e => setForm({...form, project_description:e.target.value})}/></div>
              <div className="space-y-2">
                <Label>{t("wizard.description.fields.workingDirectory")}</Label>
                <div className="flex items-center gap-2">
                  <Input placeholder={t("wizard.description.workingDirectoryPlaceholder")} value={form.working_directory_path} onChange={e => setForm({...form, working_directory_path:e.target.value})}/>
                  <WorkingDirPicker workingDir={form.working_directory_path || undefined} onSelect={(path) => setForm({...form, working_directory_path: path ?? ""})}/>
                </div>
              </div>
            </TabsContent>
            <TabsContent value="stack" className="mt-4 space-y-4">
              <p className="text-sm text-muted-foreground">{t("wizard.stack.help")}</p>
              {TECH_STACK_LAYERS.map((layer) => (
                <div key={layer} className="grid gap-3 rounded-lg border p-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>{t(`wizard.stack.layers.${layer}`)}</Label>
                    <Select value={techStack[layer].decision} onChange={(e) => setTechStack({ ...techStack, [layer]: { ...techStack[layer], decision: e.target.value } })}>
                      <option value="">{t("wizard.stack.selectPlaceholder")}</option>
                      {TECH_STACK_OPTIONS[layer].map((option) => <option key={option} value={option}>{option}</option>)}
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>{t("wizard.stack.rationale")}</Label>
                    <Input value={techStack[layer].rationale} onChange={(e) => setTechStack({ ...techStack, [layer]: { ...techStack[layer], rationale: e.target.value } })}/>
                  </div>
                </div>
              ))}
            </TabsContent>
          </Tabs>
          {editingRequest && !conceptEditable && <p className="text-sm text-muted-foreground">{t("captureIdea.conceptLocked")}</p>}
          {create.isError && <p className="text-sm text-destructive">{t("captureIdea.error.createFailed")}</p>}
        </CardContent>
        <CardFooter className="gap-2">
          <Button type="submit" disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin"/>}
            {editingRequest ? t("captureIdea.buttons.save") : t("captureIdea.buttons.create")}
          </Button>
          <Button type="button" variant="outline" onClick={backToList}>{t("captureIdea.buttons.cancel")}</Button>
        </CardFooter>
        </form>
      </Card>
    ) : (
      <div className="space-y-6"><Card><CardHeader><CardTitle className="text-lg">{t("developmentRequests.title")}</CardTitle><CardDescription>{t("developmentRequests.description")}</CardDescription></CardHeader><CardContent className="space-y-3">
        {requests.isLoading && <p className="text-sm text-muted-foreground">{t("developmentRequests.loading")}</p>}
        {requests.data?.length === 0 && <p className="text-sm text-muted-foreground">{t("developmentRequests.empty")}</p>}
        {requests.data?.map(item => <div
          key={item.id}
          role="button"
          tabIndex={0}
          onClick={()=>{setSelectedProduct(item.product_id);setDelivery(value=>({...value,project_name:item.title}));}}
          onKeyDown={(e)=>{if(e.key==="Enter"||e.key===" "){setSelectedProduct(item.product_id);setDelivery(value=>({...value,project_name:item.title}));}}}
          className={`w-full cursor-pointer rounded-lg border p-4 text-left ${selectedProduct===item.product_id?"border-primary bg-primary/5":""}`}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="font-medium">{item.title}</p>
            <div className="flex shrink-0 items-center gap-1">
              <Badge variant="outline">{item.status}</Badge>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                title={t("developmentRequests.edit")}
                onClick={(e)=>{e.stopPropagation();startEdit(item);}}
              ><Pencil className="h-3.5 w-3.5"/></Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                title={t("developmentRequests.delete")}
                onClick={(e)=>{e.stopPropagation();setPendingDelete({ productId: item.product_id, title: item.title });}}
              ><Trash2 className="h-3.5 w-3.5 text-destructive"/></Button>
            </div>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
          <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground"><span>{item.requested_by || "system"} · {item.priority}</span><Link className="text-primary hover:underline" to={`/system-map?product=${item.product_id}`} onClick={(e)=>e.stopPropagation()}>{t("developmentRequests.openSystemMap")}</Link></div>
        </div>)}
      </CardContent></Card>
      {concept.data && <Card><CardHeader><div className="flex items-center justify-between gap-3"><div><CardTitle className="text-lg">{t("conceptDecision.title")}</CardTitle><CardDescription>{t("conceptDecision.description")}</CardDescription></div><Badge variant="outline">{concept.data.concept.status}</Badge></div></CardHeader><CardContent className="space-y-4">
        <div className="rounded-md bg-muted/40 p-3 text-sm"><p className="font-medium">{concept.data.current_revision?.problem_statement}</p><p className="mt-1 text-muted-foreground">{concept.data.current_revision?.vision}</p></div>
        <div className="flex flex-wrap gap-2"><Link to={`/system-map?product=${selectedProduct}`}><Button variant="outline">{t("conceptDecision.actions.reviewSystemMap")}</Button></Link>
          {["draft","rework"].includes(concept.data.concept.status) && <Button onClick={()=>submitConcept.mutate(concept.data!.concept.id)} disabled={submitConcept.isPending}>{t("conceptDecision.actions.submitForReview")}</Button>}
          {concept.data.concept.status==="in_review" && <Link to="/governance"><Button>{t("conceptDecision.actions.openApprovalInbox")}</Button></Link>}
        </div>
        {submitConcept.isError && <p className="text-sm text-destructive">{t("conceptDecision.error.submitBlocked")}</p>}
        {concept.data.concept.status==="approved" && <form className="grid gap-3 rounded-lg border p-4 md:grid-cols-3" onSubmit={async e=>{e.preventDefault();await authorize.mutateAsync({conceptId:concept.data!.concept.id,...delivery,project_description:concept.data!.current_revision?.project_description ?? undefined,working_directory_path:concept.data!.current_revision?.working_directory_path ?? undefined});}}><div><Label>{t("conceptDecision.authorizeForm.version")}</Label><Input required value={delivery.version} onChange={e=>setDelivery({...delivery,version:e.target.value})}/></div><div><Label>{t("conceptDecision.authorizeForm.projectName")}</Label><Input required value={delivery.project_name} onChange={e=>setDelivery({...delivery,project_name:e.target.value})}/></div><div><Label>{t("conceptDecision.authorizeForm.owner")}</Label><Input value={delivery.owner} onChange={e=>setDelivery({...delivery,owner:e.target.value})}/></div><div className="md:col-span-3 flex items-center gap-3"><Button disabled={authorize.isPending}>{authorize.isPending&&<Loader2 className="mr-2 h-4 w-4 animate-spin"/>}{t("conceptDecision.actions.authorizeDelivery")}</Button>{authorize.data&&<Link className="text-sm text-primary hover:underline" to={`/project-scope`}>{t("conceptDecision.actions.openProjectScope")}</Link>}</div>{authorize.data&&<p className="md:col-span-3 text-xs text-muted-foreground">{t("conceptDecision.authorizeForm.tasksGenerated",{count:authorize.data.tasks_created})}</p>}</form>}
      </CardContent></Card>}
      </div>
    )}
    <ConfirmDialog
      open={pendingDelete !== null}
      title={t("developmentRequests.deleteDialog.title", { name: pendingDelete?.title ?? "" })}
      description={t("developmentRequests.deleteDialog.description")}
      confirmLabel={t("developmentRequests.deleteDialog.confirmLabel")}
      loading={deleteProduct.isPending}
      onConfirm={confirmDelete}
      onCancel={() => setPendingDelete(null)}
    />
  </div>;
}
