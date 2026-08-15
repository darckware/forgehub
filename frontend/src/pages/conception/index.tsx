import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { FileText, Lightbulb, Loader2, Plus, Rocket, Trash2, Upload } from "lucide-react";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";
import { useDeleteProduct, useUpdateProduct } from "@/hooks/useProduct";
import { PROJECT_SOLUTION_TYPES } from "@/hooks/useProject";
import { usePipelineTemplates } from "@/hooks/usePipeline";
import {
  useAuthorizeDeliveryPlanning,
  useConcept,
  useConceptDocument,
  useConceptDocuments,
  useCreateIdea,
  useDeleteConceptDocument,
  useDevelopmentRequests,
  useReviseConcept,
  useSaveConceptDocument,
  useSyncArtifactsToProject,
  useUpdateConceptDeliveryMetadata,
  useUpdateDevelopmentRequest,
  useUploadConceptDocument,
  type DeliveryPlanningProjectResult,
  type DeliveryPlanningProjectSpec,
  type DevelopmentRequest,
  type TechStackDecision,
  type TechStackLayer,
} from "@/hooks/useSystemScope";

// UI guardrails for the idea-capture form. name mirrors the backend's
// IdeaCreate max_length=255; the Text-column fields (no DB limit) get a
// generous soft cap so the char counter has a target to show.
const NAME_MAX = 255;
const PROBLEM_STATEMENT_MAX = 4000;
const VISION_MAX = 2000;
const SCOPE_SUMMARY_MAX = 2000;
const PROJECT_DESCRIPTION_MAX = 4000;

// Fixed set of layers per TECH_STACK_LAYERS (backend/app/db/models/system_scope.py)
// with the approved option list per stack/02-UI-DESIGN-SYSTEM-AND-TECHNOLOGY-SPEC.md
// (frontend tech-selection decision tree §12/§14, backend §17, data §18).
// "deploy_infra" has no dedicated section there -- Docker is the org's
// documented deploy baseline (stack/10-DEVSECOPS-CI-CD-AND-RELEASE-STANDARD.md),
// so it anchors that layer's options instead.
const TECH_STACK_LAYERS: TechStackLayer[] = ["frontend", "backend", "database", "deploy_infra"];

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

/** Step 4 "Documentation": markdown files attached to this concept (fill-in
 * templates, reference material) -- upload one from disk or write a new one
 * directly, then edit inline. Lives in the same concepts/<slug>/ folder the
 * approval-gated artifact generation (PRD/Spec/...) writes to, so both show
 * up together once a concept is approved. */
function ConceptDocumentsPanel({ conceptId }: { conceptId: string | undefined }) {
  const { t } = useTranslation("conception");
  const documents = useConceptDocuments(conceptId);
  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const document = useConceptDocument(conceptId, selectedFilename ?? undefined);
  const saveDocument = useSaveConceptDocument();
  const uploadDocument = useUploadConceptDocument();
  const deleteDocument = useDeleteConceptDocument();
  const [editedContent, setEditedContent] = useState("");
  const [newFilename, setNewFilename] = useState("");
  const [creating, setCreating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Every hook this component calls must run on every render, in the same
  // order, regardless of `conceptId` -- this and the paste-handler effect
  // below used to sit after an early `if (!conceptId) return`, which is a
  // Rules-of-Hooks violation (React error #310, "rendered more hooks than
  // during the previous render") the moment a render where conceptId is
  // still undefined is followed by one where it's loaded. That never
  // surfaced while this panel only mounted once its Documentation *tab* was
  // clicked (by then the concept had usually already loaded); folding it
  // into the single continuous form (2026-08-15) mounts it immediately,
  // exposing the pre-existing bug on every "New idea" / freshly-loading
  // "Edit idea" render.
  const [fileDescriptions, setFileDescriptions] = useState<Record<string, string>>({
    "PRD.md": "Documento de Requisitos do Produto (PRD)",
    "SPEC.md": "Especificação Técnica e Arquitetura do Sistema",
    "STACK.md": "Decisão das Tecnologias e Frameworks",
    "DESIGN_SYSTEM.md": "Guia de Estilos e Componentes UI",
    "DATABASE_SPEC.md": "Modelagem e Tabelas do Banco de Dados",
  });

  useEffect(() => {
    if (document.data) setEditedContent(document.data.content);
  }, [document.data]);

  useEffect(() => {
    const handleGlobalPaste = async (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items || !conceptId) return;

      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.type.indexOf("image") !== -1) {
          e.preventDefault();
          const file = item.getAsFile();
          if (!file) continue;

          // Avoid a bracketed regex here: Tailwind scans TSX as plain text and
          // mistakes its character class for an arbitrary CSS class.
          const timestamp = new Date()
            .toISOString()
            .split("-").join("")
            .split(":").join("")
            .split("T").join("")
            .split(".").join("")
            .slice(0, 14);
          const extension = file.type.split("/")[1] || "png";
          const pastedFile = new File([file], `paste_${timestamp}.${extension}`, { type: file.type });

          const result = await uploadDocument.mutateAsync({ conceptId, file: pastedFile });
          setSelectedFilename(result.filename);
          setFileDescriptions((prev) => ({
            ...prev,
            [result.filename]: "Imagem da Área de Transferência",
          }));
          break;
        }
      }
    };

    window.addEventListener("paste", handleGlobalPaste);
    return () => window.removeEventListener("paste", handleGlobalPaste);
  }, [conceptId, uploadDocument]);

  if (!conceptId) {
    return <p className="text-sm text-muted-foreground">{t("wizard.documentation.saveFirst")}</p>;
  }

  const createDocument = async () => {
    const trimmed = newFilename.trim();
    if (!trimmed) return;
    const filename = /\.(md|markdown|txt)$/i.test(trimmed) ? trimmed : `${trimmed}.md`;
    const result = await saveDocument.mutateAsync({ conceptId, filename, content: "" });
    setNewFilename("");
    setCreating(false);
    setSelectedFilename(result.filename);
  };

  const updateDescription = (filename: string, desc: string) => {
    setFileDescriptions((prev) => ({ ...prev, [filename]: desc }));
  };

  return (
    <div className="grid gap-4 md:grid-cols-[320px_1fr] focus:outline-none" tabIndex={0}>
      <div className="space-y-3 border-r pr-4">
        <div className="flex items-center justify-between">
          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{t("wizard.documentation.filesTitle")}</p>
          <div className="flex gap-1">
            <input
              ref={fileInputRef} type="file" accept=".md,.markdown,.txt,.png,.jpg,.svg" className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                const result = await uploadDocument.mutateAsync({ conceptId, file });
                setSelectedFilename(result.filename);
              }}
            />
            <Button type="button" variant="outline" size="sm" className="h-7 gap-1 text-xs" title={t("wizard.documentation.upload")} onClick={() => fileInputRef.current?.click()} disabled={uploadDocument.isPending}>
              {uploadDocument.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin"/> : <Upload className="h-3.5 w-3.5"/>}
              Upload
            </Button>
            <Button type="button" variant="outline" size="sm" className="h-7 gap-1 text-xs" title={t("wizard.documentation.newDocument")} onClick={() => setCreating((v) => !v)}>
              <Plus className="h-3.5 w-3.5"/>
              Novo
            </Button>
          </div>
        </div>
        {creating && (
          <div className="flex gap-1">
            <Input className="h-8 text-xs" placeholder="Nome do arquivo (ex: SPEC.md)" value={newFilename} onChange={(e) => setNewFilename(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); createDocument(); } }} />
            <Button type="button" size="sm" className="h-8 px-2 text-xs" onClick={createDocument} disabled={saveDocument.isPending || !newFilename.trim()}>{t("wizard.documentation.create")}</Button>
          </div>
        )}
        {documents.isLoading && <p className="text-xs text-muted-foreground">{t("wizard.documentation.loading")}</p>}
        {documents.data?.length === 0 && !creating && <p className="text-xs text-muted-foreground">{t("wizard.documentation.empty")}</p>}
        <div className="space-y-2">
          {documents.data?.map((doc) => (
            <div
              key={doc.filename}
              onClick={() => setSelectedFilename(doc.filename)}
              className={`rounded-lg border p-2 text-xs space-y-1.5 cursor-pointer transition-colors ${selectedFilename === doc.filename ? "border-primary bg-primary/5" : "hover:bg-accent/40"}`}
            >
              <div className="flex items-center justify-between gap-1">
                <div className="flex items-center gap-1.5 min-w-0">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-primary"/>
                  <span className="font-semibold truncate">{doc.filename}</span>
                </div>
                <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">
                  {doc.filename.endsWith(".md") ? "Markdown" : "Asset"}
                </Badge>
              </div>

              {/* Campo de Descrição do Arquivo */}
              <div className="space-y-1" onClick={(e) => e.stopPropagation()}>
                <Input
                  className="h-6 text-[11px] px-2 bg-background/80 placeholder:text-muted-foreground/60"
                  placeholder="Descreva a finalidade (ex: PRD, Stack...)"
                  value={fileDescriptions[doc.filename] ?? ""}
                  onChange={(e) => updateDescription(doc.filename, e.target.value)}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-2">
        {!selectedFilename ? (
          <div className="flex flex-col items-center justify-center h-64 border rounded-lg border-dashed text-muted-foreground space-y-1 text-center p-4">
            <FileText className="h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm font-medium">{t("wizard.documentation.selectHint")}</p>
            <p className="text-xs text-muted-foreground max-w-xs">Selecione um arquivo da lista ou pressione Ctrl+V / Cmd+V para colar uma imagem da área de transferência.</p>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between pb-2 border-b">
              <div>
                <p className="text-sm font-bold">{selectedFilename}</p>
                <p className="text-xs text-muted-foreground">
                  {fileDescriptions[selectedFilename] || "Sem descrição informada"}
                </p>
              </div>
              <div className="flex gap-2">
                <Button type="button" size="sm" disabled={saveDocument.isPending || document.isLoading} onClick={() => saveDocument.mutate({ conceptId, filename: selectedFilename, content: editedContent })}>
                  {saveDocument.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin"/>}
                  {t("wizard.documentation.save")}
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => { deleteDocument.mutate({ conceptId, filename: selectedFilename }); setSelectedFilename(null); }} disabled={deleteDocument.isPending}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive"/>
                </Button>
              </div>
            </div>
            {document.isLoading ? (
              <p className="text-xs text-muted-foreground">{t("wizard.documentation.loading")}</p>
            ) : (
              <Textarea rows={18} className="font-mono text-xs" value={editedContent} onChange={(e) => setEditedContent(e.target.value)} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

type ProjectSpecForm = DeliveryPlanningProjectSpec & { version: string };

const EMPTY_PROJECT_SPEC: ProjectSpecForm = {
  solution_type: "web_app", project_name: "", version: "0.1.0", project_type: "creation",
};

const PROJECT_TYPES = ["creation", "maintenance"] as const;

/** Project(s) section -- turns an approved Concept into one Project per
 * requested application type (2026-08-01 decision: one Project per type,
 * not Tracks inside a single Project -- see docs/architecture/
 * PLANNING_DELIVERY_ARCHITECTURE.md section 2.2's note). Folded into the
 * single-form Conception page (not its own tab) as of 2026-08-15 -- its
 * working-directory input was a duplicate of the "Description and folder"
 * section's, so this now takes the concept-level `workingDirectoryPath` and
 * applies it to every Project instead of asking again per row. The pipeline
 * template is likewise chosen once, at the top of the page, and threaded
 * through here via `pipelineTemplateId` -- never asked twice.
 *
 * Each project row still carries its own version (2026-08-15, Marcelo:
 * "para cada projeto o controle de versão, não posso ter uma versão
 * [única]"). The backend call itself still only accepts one shared
 * `version` per request -- a ProductVersion is 1:1 with the System Map
 * revision it authorizes (see the 409 check in authorize_delivery_planning),
 * so two different new versions can't be created in the same call without
 * corrupting that link. Submit works around this without touching the
 * backend contract: specs are grouped by their version string and one
 * :authorize-delivery-planning call is fired per group, sequentially, so
 * each distinct version a project asks for still gets its own call while
 * specs that share a version still batch together exactly like before. */
function ProjectPlanningPanel({
  conceptId, conceptStatus, workingDirectoryPath, pipelineTemplateId,
}: {
  conceptId: string | undefined; conceptStatus: string | undefined;
  workingDirectoryPath: string; pipelineTemplateId: string;
}) {
  const authorize = useAuthorizeDeliveryPlanning();
  const sync = useSyncArtifactsToProject();
  const [specs, setSpecs] = useState<ProjectSpecForm[]>([{ ...EMPTY_PROJECT_SPEC }]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [results, setResults] = useState<DeliveryPlanningProjectResult[] | null>(null);

  if (!conceptId) {
    return <p className="text-sm text-muted-foreground">Salve a ideia primeiro para poder criar o projeto.</p>;
  }
  if (conceptStatus !== "approved") {
    return <p className="text-sm text-muted-foreground">Disponível depois que a Concepção for aprovada (status atual: {conceptStatus ?? "--"}).</p>;
  }

  const updateSpec = (index: number, patch: Partial<ProjectSpecForm>) =>
    setSpecs((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  const addSpec = () => setSpecs((prev) => [...prev, { ...EMPTY_PROJECT_SPEC }]);
  const removeSpec = (index: number) => setSpecs((prev) => prev.filter((_, i) => i !== index));

  const submit = async () => {
    const projects = specs.filter((s) => s.project_name.trim());
    if (!projects.length) return;
    const groups = new Map<string, DeliveryPlanningProjectSpec[]>();
    for (const { version, ...spec } of projects) {
      const key = version.trim() || "0.1.0";
      const withSharedFields = { ...spec, working_directory_path: workingDirectoryPath || undefined };
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(withSharedFields);
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const allResults: DeliveryPlanningProjectResult[] = [];
      for (const [version, groupProjects] of groups) {
        const res = await authorize.mutateAsync({
          conceptId, version, projects: groupProjects,
          pipeline_template_id: pipelineTemplateId || undefined,
        });
        allResults.push(...res.projects);
      }
      setResults(allResults);
    } catch (e) {
      setSubmitError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Cria um Project por tipo de aplicação selecionado, cada um com sua própria versão do produto.
        Cada Project recebe só as tarefas da sua camada (telas para web/mobile, APIs para
        backend, etc.). Repetir a mesma versão + tipo é idempotente -- não duplica.
      </p>
      <div className="space-y-2">
        <Label>Projetos a criar</Label>
        {specs.map((spec, i) => (
          <div key={i} className="space-y-2 rounded-md border p-2">
            <div className="grid grid-cols-[160px_1fr_32px] gap-2 items-center">
              <Select value={spec.solution_type} onChange={(e) => updateSpec(i, { solution_type: e.target.value as ProjectSpecForm["solution_type"] })}>
                {PROJECT_SOLUTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
              <Input placeholder="Nome do projeto" value={spec.project_name} onChange={(e) => updateSpec(i, { project_name: e.target.value })} />
              <Button variant="ghost" size="icon" onClick={() => removeSpec(i)} disabled={specs.length === 1}>
                <Trash2 className="h-3.5 w-3.5 text-destructive" />
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Versão</Label>
                <Input placeholder="0.1.0" value={spec.version} onChange={(e) => updateSpec(i, { version: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Tipo</Label>
                <Select value={spec.project_type ?? "creation"} onChange={(e) => updateSpec(i, { project_type: e.target.value as ProjectSpecForm["project_type"] })}>
                  {PROJECT_TYPES.map((t) => <option key={t} value={t}>{t === "creation" ? "Criação" : "Manutenção"}</option>)}
                </Select>
              </div>
            </div>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={addSpec}><Plus className="mr-1.5 h-3.5 w-3.5" />Adicionar tipo de aplicação</Button>
      </div>
      <Button disabled={submitting || specs.every((s) => !s.project_name.trim())} onClick={submit}>
        {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        <Rocket className="mr-2 h-4 w-4" />Criar Projeto
      </Button>
      {submitError && <p className="text-sm text-destructive">Falha ao criar: {submitError}</p>}
      {results && (
        <div className="space-y-2 rounded-md border p-3">
          <p className="text-sm font-medium">Projetos:</p>
          {results.map((p) => (
            <div key={p.project_id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span>
                <Badge variant="outline" className="mr-2">{p.solution_type}</Badge>
                <Link to={`/projects/${p.project_id}`} className="text-primary hover:underline">abrir projeto</Link>
                {" "}({p.scope_items_created} itens de escopo, {p.tasks_created} tasks)
              </span>
              <Button
                size="sm" variant="outline" disabled={sync.isPending}
                onClick={() => sync.mutate({ conceptId, projectId: p.project_id })}
              >
                {sync.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                Sincronizar docs para o repositório
              </Button>
            </div>
          ))}
          {sync.isSuccess && (
            <p className="text-xs text-muted-foreground">
              Gravado: {sync.data.files_written.join(", ") || "(nenhum documento gerado ainda)"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

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
  const [selectedProduct, setSelectedProduct] = useState("");
  const concept = useConcept(selectedProduct);
  const pipelineTemplates = usePipelineTemplates();
  const [form, setForm] = useState(EMPTY_FORM);
  const [techStack, setTechStack] = useState<TechStackState>(EMPTY_TECH_STACK);
  // Chosen once, at the top of the single-form page, and threaded through
  // to every Project the idea produces (see ProjectPlanningPanel's doc
  // comment) -- 2026-08-15.
  const [pipelineTemplateId, setPipelineTemplateId] = useState("");
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
    setPipelineTemplateId("");
    setSelectedProduct(item.product_id);
    setEditingRequest(item);
    setView("form");
  };

  const backToList = () => {
    setEditingRequest(null);
    setForm(EMPTY_FORM);
    setTechStack(EMPTY_TECH_STACK);
    setPipelineTemplateId("");
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
      <div className="flex items-center gap-2">
        {view === "list" && (
          <Button variant="outline" onClick={() => {
            setEditingRequest(null);
            setForm(EMPTY_FORM);
            setView("form");
          }}>
            <Lightbulb className="mr-2 h-4 w-4"/>{t("toggle.newIdea")}
          </Button>
        )}
        <AssistantToggleButton />
      </div>
    </div>
    {view === "form" ? (
      <Card><CardHeader><CardTitle className="flex items-center gap-2 text-lg"><Lightbulb className="h-5 w-5"/>{editingRequest ? t("captureIdea.editTitle") : t("captureIdea.title")}</CardTitle><CardDescription>{editingRequest ? t("captureIdea.editDescription") : t("captureIdea.description")}</CardDescription></CardHeader>
        <form onSubmit={submit}>
        <CardContent className="space-y-8">
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">{t("wizard.steps.pipeline")}</h3>
            <p className="text-sm text-muted-foreground">{t("wizard.pipeline.help")}</p>
            <Select value={pipelineTemplateId} onChange={(e) => setPipelineTemplateId(e.target.value)}>
              <option value="">{t("wizard.pipeline.placeholder")}</option>
              {pipelineTemplates.data?.map((tpl) => <option key={tpl.id} value={tpl.id}>{tpl.name}</option>)}
            </Select>
          </section>

          <section className="space-y-4 border-t pt-8">
            <h3 className="text-sm font-semibold">{t("wizard.steps.problem")}</h3>
            <div className="space-y-2"><FieldLabel label={t("captureIdea.fields.name")} count={form.name.length} max={NAME_MAX}/><Input maxLength={NAME_MAX} value={form.name} onChange={e => setForm({...form, name:e.target.value})}/></div>
            <div className="space-y-2">
              <FieldLabel label={t("captureIdea.fields.problemStatement")} count={form.problem_statement.length} max={PROBLEM_STATEMENT_MAX}/>
              <Textarea rows={4} maxLength={PROBLEM_STATEMENT_MAX} value={form.problem_statement} onChange={e => setForm({...form, problem_statement:e.target.value})}/>
            </div>
            <div className="space-y-2">
              <FieldLabel label={t("captureIdea.fields.vision")} count={form.vision.length} max={VISION_MAX}/>
              <Textarea rows={3} maxLength={VISION_MAX} value={form.vision} onChange={e => setForm({...form, vision:e.target.value})}/>
            </div>
            <div className="space-y-2">
              <FieldLabel label={t("captureIdea.fields.initialScope")} count={form.scope_summary.length} max={SCOPE_SUMMARY_MAX}/>
              <Textarea rows={3} maxLength={SCOPE_SUMMARY_MAX} value={form.scope_summary} onChange={e => setForm({...form, scope_summary:e.target.value})}/>
            </div>
          </section>

          <section className="space-y-4 border-t pt-8">
            <h3 className="text-sm font-semibold">{t("wizard.steps.description")}</h3>
            <p className="text-sm text-muted-foreground">{t("wizard.description.help")}</p>
            <div className="space-y-2"><FieldLabel label={t("wizard.description.fields.projectDescription")} count={form.project_description.length} max={PROJECT_DESCRIPTION_MAX}/><Textarea rows={6} maxLength={PROJECT_DESCRIPTION_MAX} value={form.project_description} onChange={e => setForm({...form, project_description:e.target.value})}/></div>
            <div className="space-y-2">
              <Label>{t("wizard.description.fields.workingDirectory")}</Label>
              <div className="flex items-center gap-2">
                <Input placeholder={t("wizard.description.workingDirectoryPlaceholder")} value={form.working_directory_path} onChange={e => setForm({...form, working_directory_path:e.target.value})}/>
                <WorkingDirPicker workingDir={form.working_directory_path || undefined} onSelect={(path) => setForm({...form, working_directory_path: path ?? ""})}/>
              </div>
            </div>
          </section>

          <section className="space-y-4 border-t pt-8">
            <h3 className="text-sm font-semibold">{t("wizard.steps.stack")}</h3>
            <p className="text-sm text-muted-foreground">{t("wizard.stack.help")}</p>
            {TECH_STACK_LAYERS.map((layer) => (
              <div key={layer} className="grid gap-3 rounded-lg border p-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>{t(`wizard.stack.layers.${layer}`)}</Label>
                  <Input placeholder={t("wizard.stack.selectPlaceholder")} value={techStack[layer].decision} onChange={(e) => setTechStack({ ...techStack, [layer]: { ...techStack[layer], decision: e.target.value } })}/>
                </div>
                <div className="space-y-2">
                  <Label>{t("wizard.stack.rationale")}</Label>
                  <Input value={techStack[layer].rationale} onChange={(e) => setTechStack({ ...techStack, [layer]: { ...techStack[layer], rationale: e.target.value } })}/>
                </div>
              </div>
            ))}
          </section>

          <section className="space-y-4 border-t pt-8">
            <h3 className="text-sm font-semibold">{t("wizard.steps.delivery")}</h3>
            <ProjectPlanningPanel
              conceptId={concept.data?.concept.id} conceptStatus={concept.data?.concept.status}
              workingDirectoryPath={form.working_directory_path} pipelineTemplateId={pipelineTemplateId}
            />
          </section>

          <section className="space-y-4 border-t pt-8">
            <h3 className="text-sm font-semibold">{t("wizard.steps.documentation")}</h3>
            <p className="text-sm text-muted-foreground">{t("wizard.documentation.help")}</p>
            <ConceptDocumentsPanel conceptId={concept.data?.concept.id}/>
          </section>

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
          onClick={() => startEdit(item)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") startEdit(item); }}
          className={`w-full cursor-pointer rounded-lg border p-4 text-left transition-colors hover:border-primary/50 ${selectedProduct === item.product_id ? "border-primary bg-primary/5" : ""}`}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="font-medium text-base">{item.title}</p>
            <div className="flex shrink-0 items-center gap-1">
              <Badge variant="outline">{item.status}</Badge>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                title={t("developmentRequests.delete")}
                onClick={(e) => { e.stopPropagation(); setPendingDelete({ productId: item.product_id, title: item.title }); }}
              ><Trash2 className="h-3.5 w-3.5 text-destructive"/></Button>
            </div>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
          <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
            <span>{item.priority}</span>
          </div>
        </div>)}
      </CardContent></Card>
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
