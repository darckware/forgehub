import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  BookOpen,
  Database,
  FileText,
  Filter,
  Image as ImageIcon,
  Layout,
  Layers,
  Lightbulb,
  Loader2,
  Network,
  Palette,
  Plus,
  Rocket,
  Sparkles,
  Trash2,
  Upload,
  Wrench,
} from "lucide-react";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { CopyButton } from "@/components/CopyButton";
import { TechStackOptionPicker } from "@/components/TechStackOptionPicker";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";
import { useChattableAgents } from "@/hooks/useAgent";
import { usePromptTemplate, useStreamAgentDraft } from "@/hooks/useAiDraft";
import { useDeleteProduct, useProductVersions, useUpdateProduct } from "@/hooks/useProduct";
import {
  PROJECT_SOLUTION_TYPES,
  PROJECT_SOLUTION_TYPE_LABELS,
  useDeleteProject,
  useProjects,
} from "@/hooks/useProject";
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
  useAllTechStackOptions,
  useUpdateConceptDeliveryMetadata,
  useUpdateConceptDocumentMetadata,
  useUpdateDevelopmentRequest,
  useUploadConceptDocument,
  type DeliveryPlanningProjectResult,
  type DeliveryPlanningProjectSpec,
  type DevelopmentRequest,
  type TechStackDecision,
  type TechStackLayer,
} from "@/hooks/useSystemScope";

const CONTEXT_DRAFT_DOC_FILENAME = "context-draft.md";

// UI guardrails for the idea-capture form. name mirrors the backend's
// IdeaCreate max_length=255; the Text-column fields (no DB limit) get a
// generous soft cap so the char counter has a target to show.
const NAME_MAX = 255;
const PROBLEM_STATEMENT_MAX = 4000;
const VISION_MAX = 2000;
const SCOPE_SUMMARY_MAX = 2000;
const PROJECT_DESCRIPTION_MAX = 4000;

// Layer vocabulary per TECH_STACK_LAYERS (backend/app/db/models/system_scope.py),
// each backed by an approved option catalog seeded from stack/02-UI-DESIGN-
// SYSTEM-AND-TECHNOLOGY-SPEC.md (frontend §12/§14, backend §17, data §18;
// "deploy_infra" has no dedicated section there -- Docker Compose is the
// org's documented deploy baseline, see TechStackOptionPicker's own seed).
// The list of entries itself is NOT fixed to "exactly one per layer" --
// not every pipeline needs all four layers, and some need more than one
// technology in the same layer (e.g. two backends) -- so the form is a
// free add/remove list rather than four hardcoded slots (2026-08-15,
// Marcelo: "nem todo pipeline seria usado esse padrão").
const TECH_STACK_LAYERS: TechStackLayer[] = [
  "frontend",
  "mobile",
  "backend",
  "database",
  "cache",
  "messaging",
  "auth",
  "storage",
  "search",
  "api_gateway",
  "deploy_infra",
  "cicd",
  "observability",
  "testing",
  "documentation",
];

interface TechStackEntry { key: string; layer: TechStackLayer; decision: string; rationale: string }

function techStackToEntries(decisions: TechStackDecision[] | null | undefined): TechStackEntry[] {
  return (decisions ?? []).map((item) => ({
    key: crypto.randomUUID(), layer: item.layer, decision: item.decision, rationale: item.rationale ?? "",
  }));
}

function techStackToPayload(entries: TechStackEntry[]): TechStackDecision[] {
  return entries
    .filter((entry) => entry.decision.trim().length > 0)
    .map((entry) => ({
      layer: entry.layer, decision: entry.decision,
      rationale: entry.rationale.trim() ? entry.rationale : null,
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
const DOCUMENT_CATEGORIES = [
  { id: "prd", label: "PRD / Requisitos", icon: FileText, defaultFilename: "PRD.md", description: "Documento de Requisitos do Produto (PRD)", color: "text-blue-500 bg-blue-500/10 border-blue-500/20" },
  { id: "design_system", label: "Design System / UI", icon: Palette, defaultFilename: "DESIGN_SYSTEM.md", description: "Guia de Estilos, Tokens e Componentes UI", color: "text-purple-500 bg-purple-500/10 border-purple-500/20" },
  { id: "database", label: "Modelagem de Banco de Dados", icon: Database, defaultFilename: "DATABASE_SPEC.md", description: "Modelagem, Schemas e Tabelas do Banco", color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" },
  { id: "architecture", label: "Arquitetura / SPEC", icon: Layers, defaultFilename: "SPEC.md", description: "Especificação Técnica e Arquitetura do Sistema", color: "text-amber-500 bg-amber-500/10 border-amber-500/20" },
  { id: "screens", label: "Telas / Wireframes", icon: Layout, defaultFilename: "SCREENS.md", description: "Especificação e Protótipos de Telas", color: "text-indigo-500 bg-indigo-500/10 border-indigo-500/20" },
  { id: "api", label: "APIs / Integrações", icon: Network, defaultFilename: "API_SPEC.md", description: "Contratos de Endpoints e Integrações", color: "text-cyan-500 bg-cyan-500/10 border-cyan-500/20" },
  { id: "other", label: "Outros Documentos", icon: BookOpen, defaultFilename: "DOC.md", description: "Documentação Geral de Referência", color: "text-slate-500 bg-slate-500/10 border-slate-500/20" },
] as const;

type DocCategoryKey = (typeof DOCUMENT_CATEGORIES)[number]["id"];

function inferDocCategory(filename: string): DocCategoryKey {
  const lower = filename.toLowerCase();
  if (lower.includes("prd") || lower.includes("requisito") || lower.includes("requirements")) return "prd";
  if (lower.includes("design") || lower.includes("theme") || lower.includes("style") || lower.includes("ui")) return "design_system";
  if (lower.includes("data") || lower.includes("db") || lower.includes("banco") || lower.includes("model") || lower.includes("erd")) return "database";
  if (lower.includes("screen") || lower.includes("tela") || lower.includes("wireframe") || lower.includes("paste_") || lower.includes("mockup")) return "screens";
  if (lower.includes("spec") || lower.includes("tech") || lower.includes("arch") || lower.includes("arquitetura")) return "architecture";
  if (lower.includes("api") || lower.includes("endpoint") || lower.includes("contrato") || lower.includes("openapi") || lower.includes("swagger")) return "api";
  return "other";
}

function getCategoryConfig(key?: string | null) {
  return DOCUMENT_CATEGORIES.find((c) => c.id === key) ?? DOCUMENT_CATEGORIES[6];
}

function ConceptDocumentsPanel({ conceptId }: { conceptId: string | undefined }) {
  const { t } = useTranslation("conception");
  const documents = useConceptDocuments(conceptId);
  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const document = useConceptDocument(conceptId, selectedFilename ?? undefined);
  const saveDocument = useSaveConceptDocument();
  const uploadDocument = useUploadConceptDocument();
  const updateDocMetadata = useUpdateConceptDocumentMetadata();
  const deleteDocument = useDeleteConceptDocument();
  const [editedContent, setEditedContent] = useState("");
  const [newFilename, setNewFilename] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<DocCategoryKey>("prd");
  const [creating, setCreating] = useState(false);
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [localDescriptions, setLocalDescriptions] = useState<Record<string, string>>({});

  useEffect(() => {
    if (document.data) {
      setEditedContent(document.data.content);
    }
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

          const timestamp = new Date()
            .toISOString()
            .split("-").join("")
            .split(":").join("")
            .split("T").join("")
            .split(".").join("")
            .slice(0, 14);
          const extension = file.type.split("/")[1] || "png";
          const pastedFile = new File([file], `paste_${timestamp}.${extension}`, { type: file.type });

          const result = await uploadDocument.mutateAsync({
            conceptId,
            file: pastedFile,
            category: "screens",
            description: "Mockup / Imagem de Tela Colada",
          });
          setSelectedFilename(result.filename);
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
    const filename = /\.(md|markdown|txt|json)$/i.test(trimmed) ? trimmed : `${trimmed}.md`;
    const cat = DOCUMENT_CATEGORIES.find((c) => c.id === selectedCategory);
    const initialContent = `# ${cat?.label ?? "Documento"}\n\n${cat?.description ?? ""}\n\n## Detalhes\n\n`;
    const result = await saveDocument.mutateAsync({
      conceptId,
      filename,
      content: initialContent,
      category: selectedCategory,
      description: cat?.description ?? "",
    });
    setNewFilename("");
    setCreating(false);
    setSelectedFilename(result.filename);
  };

  const addTemplateDocument = async (category: typeof DOCUMENT_CATEGORIES[number]) => {
    const filename = category.defaultFilename;
    const initialContent = `# ${category.label}\n\n${category.description}\n\n## 1. Visão Geral\n\n## 2. Especificação Detalhada\n\n`;
    const result = await saveDocument.mutateAsync({
      conceptId,
      filename,
      content: initialContent,
      category: category.id,
      description: category.description,
    });
    setSelectedFilename(result.filename);
  };

  const isImageFile = (filename: string | null) => {
    if (!filename) return false;
    return /\.(png|jpg|jpeg|webp|svg|gif)$/i.test(filename);
  };

  const handleCategoryChange = (filename: string, newCat: string) => {
    updateDocMetadata.mutate({
      conceptId,
      filename,
      category: newCat,
    });
  };

  const handleDescriptionBlur = (filename: string, desc: string) => {
    updateDocMetadata.mutate({
      conceptId,
      filename,
      description: desc,
    });
  };

  const allDocs = documents.data ?? [];
  const filteredDocs = activeFilter === "all"
    ? allDocs
    : allDocs.filter((doc) => {
        const cat = doc.category || inferDocCategory(doc.filename);
        return cat === activeFilter;
      });

  return (
    <div className="space-y-4">
      {/* Atalhos Rápidos para Catalogar Documentação Padrão */}
      <div className="flex flex-wrap items-center gap-2 pb-2 border-b">
        <span className="text-xs font-semibold text-muted-foreground mr-1">Catalogar Modelo:</span>
        {DOCUMENT_CATEGORIES.map((cat) => {
          const alreadyExists = documents.data?.some((d) => d.filename.toLowerCase() === cat.defaultFilename.toLowerCase());
          const Icon = cat.icon;
          return (
            <Button
              key={cat.id}
              type="button"
              variant={alreadyExists ? "secondary" : "outline"}
              size="sm"
              className="h-7 text-xs gap-1.5"
              onClick={() => {
                if (alreadyExists) {
                  setSelectedFilename(cat.defaultFilename);
                } else {
                  void addTemplateDocument(cat);
                }
              }}
            >
              <Icon className={`h-3.5 w-3.5 ${alreadyExists ? "text-primary" : ""}`} />
              {cat.label}
            </Button>
          );
        })}
      </div>

      {/* Filtros Rápidos por Classificação */}
      <div className="flex flex-wrap items-center gap-1.5 pb-1">
        <span className="text-[11px] font-medium text-muted-foreground mr-1 flex items-center gap-1">
          <Filter className="h-3 w-3" /> Filtrar:
        </span>
        <Button
          type="button"
          variant={activeFilter === "all" ? "default" : "ghost"}
          size="sm"
          className="h-6 text-[11px] px-2"
          onClick={() => setActiveFilter("all")}
        >
          Todos ({allDocs.length})
        </Button>
        {DOCUMENT_CATEGORIES.map((cat) => {
          const count = allDocs.filter((d) => (d.category || inferDocCategory(d.filename)) === cat.id).length;
          if (count === 0 && activeFilter !== cat.id) return null;
          const Icon = cat.icon;
          return (
            <Button
              key={cat.id}
              type="button"
              variant={activeFilter === cat.id ? "default" : "outline"}
              size="sm"
              className="h-6 text-[11px] px-2 gap-1"
              onClick={() => setActiveFilter(cat.id)}
            >
              <Icon className="h-3 w-3" />
              {cat.label} ({count})
            </Button>
          );
        })}
      </div>

      <div className="grid gap-4 md:grid-cols-[380px_1fr] focus:outline-none" tabIndex={0}>
        <div className="space-y-3 border-r pr-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{t("wizard.documentation.filesTitle")}</p>
            <div className="flex gap-1">
              <input
                ref={fileInputRef} type="file" accept=".md,.markdown,.txt,.png,.jpg,.jpeg,.webp,.svg,.pdf,.json" className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  const cat = selectedCategory || inferDocCategory(file.name);
                  const result = await uploadDocument.mutateAsync({
                    conceptId,
                    file,
                    category: cat,
                    description: DOCUMENT_CATEGORIES.find((c) => c.id === cat)?.description ?? "",
                  });
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
            <div className="space-y-2 rounded-lg border p-2 bg-muted/30">
              <div className="space-y-1">
                <Label className="text-[11px] font-semibold text-muted-foreground">Classificação do Documento</Label>
                <Select value={selectedCategory} onChange={(e) => {
                  const catKey = e.target.value as DocCategoryKey;
                  setSelectedCategory(catKey);
                  const catObj = DOCUMENT_CATEGORIES.find((c) => c.id === catKey);
                  if (catObj && !newFilename.trim()) {
                    setNewFilename(catObj.defaultFilename);
                  }
                }}>
                  {DOCUMENT_CATEGORIES.map((c) => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </Select>
              </div>
              <div className="flex gap-1">
                <Input
                  className="h-8 text-xs"
                  placeholder="Nome do arquivo (ex: PRD.md)"
                  value={newFilename}
                  onChange={(e) => setNewFilename(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void createDocument(); } }}
                />
                <Button type="button" size="sm" className="h-8 px-2 text-xs" onClick={() => void createDocument()} disabled={saveDocument.isPending || !newFilename.trim()}>
                  {t("wizard.documentation.create")}
                </Button>
              </div>
            </div>
          )}

          {documents.isLoading && <p className="text-xs text-muted-foreground">{t("wizard.documentation.loading")}</p>}
          {filteredDocs.length === 0 && !creating && (
            <p className="text-xs text-muted-foreground">
              {activeFilter === "all" ? t("wizard.documentation.empty") : "Nenhum documento nesta classificação."}
            </p>
          )}
          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {filteredDocs.map((doc) => {
              const catKey = (doc.category || inferDocCategory(doc.filename)) as DocCategoryKey;
              const catObj = getCategoryConfig(catKey);
              const Icon = catObj.icon;
              const desc = localDescriptions[doc.filename] ?? doc.description ?? "";

              return (
                <div
                  key={doc.filename}
                  onClick={() => setSelectedFilename(doc.filename)}
                  className={`rounded-lg border p-2.5 text-xs space-y-2 cursor-pointer transition-colors ${selectedFilename === doc.filename ? "border-primary bg-primary/5 shadow-sm" : "hover:bg-accent/40"}`}
                >
                  <div className="flex items-center justify-between gap-1.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Icon className={`h-4 w-4 shrink-0 ${catObj.color.split(" ")[0]}`}/>
                      <span className="font-semibold truncate" title={doc.filename}>{doc.filename}</span>
                    </div>

                    {/* Dropdown de Classificação Direta */}
                    <div onClick={(e) => e.stopPropagation()}>
                      <Select
                        className="h-6 text-[10px] py-0 px-1 font-medium w-36"
                        value={catKey}
                        onChange={(e) => handleCategoryChange(doc.filename, e.target.value)}
                      >
                        {DOCUMENT_CATEGORIES.map((c) => (
                          <option key={c.id} value={c.id}>{c.label}</option>
                        ))}
                      </Select>
                    </div>
                  </div>

                  {/* Campo de Descrição / Propósito do Arquivo */}
                  <div className="space-y-1" onClick={(e) => e.stopPropagation()}>
                    <Input
                      className="h-6 text-[11px] px-2 bg-background/80 placeholder:text-muted-foreground/60"
                      placeholder="Descreva o propósito deste documento..."
                      value={desc}
                      onChange={(e) => setLocalDescriptions((prev) => ({ ...prev, [doc.filename]: e.target.value }))}
                      onBlur={(e) => handleDescriptionBlur(doc.filename, e.target.value)}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          {!selectedFilename ? (
            <div className="flex flex-col items-center justify-center h-80 border rounded-lg border-dashed text-muted-foreground space-y-2 text-center p-6">
              <FileText className="h-10 w-10 text-muted-foreground/40" />
              <p className="text-sm font-semibold">{t("wizard.documentation.selectHint")}</p>
              <p className="text-xs text-muted-foreground max-w-md">
                Selecione um documento catalogado ao lado para visualizar e editar, ou use os botões rápidos no topo para criar <strong>PRD</strong>, <strong>Design System</strong>, <strong>Modelagem de Banco</strong>, <strong>SPEC de Arquitetura</strong>, <strong>Telas</strong> ou <strong>APIs</strong>.
              </p>
              <p className="text-[11px] text-muted-foreground/80 bg-muted/40 px-3 py-1.5 rounded-full border">
                💡 Dica: Você pode colar prints de tela diretamente com <kbd className="font-mono bg-muted px-1 rounded">Ctrl+V</kbd> / <kbd className="font-mono bg-muted px-1 rounded">Cmd+V</kbd>.
              </p>
            </div>
          ) : (
            <>
              {(() => {
                const currentDoc = documents.data?.find((d) => d.filename === selectedFilename) ?? document.data;
                const currentCatKey = (currentDoc?.category || inferDocCategory(selectedFilename)) as DocCategoryKey;
                const currentCatObj = getCategoryConfig(currentCatKey);
                const CurrentIcon = currentCatObj.icon;
                const currentDesc = localDescriptions[selectedFilename] ?? currentDoc?.description ?? "";

                return (
                  <div className="space-y-3 pb-2 border-b">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <CurrentIcon className={`h-5 w-5 ${currentCatObj.color.split(" ")[0]}`} />
                        <div>
                          <p className="text-sm font-bold">{selectedFilename}</p>
                          <p className="text-xs text-muted-foreground">
                            {currentDesc || currentCatObj.description}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Seletor de Categoria no Cabeçalho */}
                        <div className="flex items-center gap-1.5">
                          <Label className="text-xs text-muted-foreground">Classificação:</Label>
                          <Select
                            className="h-7 text-xs font-medium w-48"
                            value={currentCatKey}
                            onChange={(e) => handleCategoryChange(selectedFilename, e.target.value)}
                          >
                            {DOCUMENT_CATEGORIES.map((c) => (
                              <option key={c.id} value={c.id}>{c.label}</option>
                            ))}
                          </Select>
                        </div>

                        {!isImageFile(selectedFilename) && (
                          <Button
                            type="button"
                            size="sm"
                            disabled={saveDocument.isPending || document.isLoading}
                            onClick={() => saveDocument.mutate({
                              conceptId,
                              filename: selectedFilename,
                              content: editedContent,
                              category: currentCatKey,
                              description: currentDesc,
                            })}
                          >
                            {saveDocument.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin"/>}
                            {t("wizard.documentation.save")}
                          </Button>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            deleteDocument.mutate({ conceptId, filename: selectedFilename });
                            setSelectedFilename(null);
                          }}
                          disabled={deleteDocument.isPending}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive"/>
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {document.isLoading ? (
                <p className="text-xs text-muted-foreground">{t("wizard.documentation.loading")}</p>
              ) : isImageFile(selectedFilename) ? (
                <div className="flex flex-col items-center justify-center p-4 border rounded-lg bg-muted/10 min-h-[340px]">
                  <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                    <ImageIcon className="h-3.5 w-3.5 text-amber-500" /> Visualização do Asset / Mockup de Tela
                  </p>
                  <img
                    src={`/api/v1/product-concepts/${conceptId}/documents/${selectedFilename}`}
                    alt={selectedFilename}
                    className="max-h-[500px] max-w-full rounded border shadow-sm object-contain bg-background"
                  />
                </div>
              ) : (
                <Textarea
                  rows={20}
                  className="resize-none font-mono text-xs leading-relaxed"
                  value={editedContent}
                  onChange={(e) => setEditedContent(e.target.value)}
                  placeholder="Conteúdo do documento em Markdown..."
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

type ProjectSpecForm = DeliveryPlanningProjectSpec & { version: string };

const EMPTY_PROJECT_SPEC: ProjectSpecForm = {
  solution_type: "web_app", project_name: "", version: "0.1.0", project_type: "creation",
};

/** Project(s) section -- turns an approved Concept into one Project per
 * requested application type (2026-08-01 decision: one Project per type,
 * not Tracks inside a single Project -- see docs/architecture/
 * PLANNING_DELIVERY_ARCHITECTURE.md section 2.2's note). Folded into the
 * single-form Conception page (not its own tab) as of 2026-08-15 -- its
 * working-directory input was a duplicate of the "Description and folder"
 * section's, so this now takes the concept-level `workingDirectoryPath` and
 * applies it to every Project instead of asking again per row. (The pipeline
 * template picker that used to be chosen once, up top, and threaded through
 * here was removed 2026-08-16 -- Marcelo: "já tinha decidido que não
 * precisava mais" -- every Project now goes through :authorize-delivery-
 * planning with no `pipeline_template_id`, i.e. the default local pipeline.)
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
function getNextVersion(currentVersion?: string): string {
  if (!currentVersion) return "0.1.1";
  const clean = currentVersion.replace(/^v/, "").trim();
  const parts = clean.split(".").map((x) => parseInt(x, 10));
  if (parts.length === 3 && !parts.some(isNaN)) {
    return `${parts[0]}.${parts[1]}.${parts[2] + 1}`;
  }
  return `${clean}.1`;
}

function ProjectPlanningPanel({
  productId, conceptId, workingDirectoryPath,
}: {
  productId: string | undefined;
  conceptId: string | undefined;
  workingDirectoryPath: string;
}) {
  const { t } = useTranslation("conception");
  const queryClient = useQueryClient();
  const authorize = useAuthorizeDeliveryPlanning();
  const sync = useSyncArtifactsToProject();
  const deleteProject = useDeleteProject();
  const { data: allProjects } = useProjects();
  const { data: productVersions } = useProductVersions(productId);

  const [actionType, setActionType] = useState<"creation" | "maintenance">("creation");
  const [specs, setSpecs] = useState<ProjectSpecForm[]>([{ ...EMPTY_PROJECT_SPEC }]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [maintenanceVersion, setMaintenanceVersion] = useState<string>("0.1.1");
  const [maintenanceProjectName, setMaintenanceProjectName] = useState<string>("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [results, setResults] = useState<DeliveryPlanningProjectResult[] | null>(null);
  const [pendingDeleteProject, setPendingDeleteProject] = useState<{ id: string; name: string } | null>(null);

  const versionIds = new Set((productVersions || []).map((v) => v.id));
  const productProjects = (allProjects || []).filter((p) => p.product_version_id && versionIds.has(p.product_version_id));

  // Auto-select first existing project when entering maintenance if none is selected
  useEffect(() => {
    if (actionType === "maintenance" && productProjects.length > 0 && !selectedProjectId) {
      const first = productProjects[0];
      setSelectedProjectId(first.id);
      setMaintenanceProjectName(first.name);
      const v = productVersions?.find((x) => x.id === first.product_version_id);
      setMaintenanceVersion(getNextVersion(v?.version));
    }
  }, [actionType, productProjects, selectedProjectId, productVersions]);

  if (!conceptId) {
    return <p className="text-sm text-muted-foreground">Salve a ideia primeiro para poder criar o projeto.</p>;
  }

  const handleSelectExistingProject = (projId: string) => {
    setSelectedProjectId(projId);
    const p = productProjects.find((x) => x.id === projId);
    if (p) {
      setMaintenanceProjectName(p.name);
      const v = productVersions?.find((x) => x.id === p.product_version_id);
      setMaintenanceVersion(getNextVersion(v?.version));
    }
  };

  const updateSpec = (index: number, patch: Partial<ProjectSpecForm>) =>
    setSpecs((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  const addSpec = () => setSpecs((prev) => [...prev, { ...EMPTY_PROJECT_SPEC }]);
  const removeSpec = (index: number) => setSpecs((prev) => prev.filter((_, i) => i !== index));

  const submitCreation = async () => {
    const projects = specs.filter((s) => s.project_name.trim());
    if (!projects.length) return;
    const groups = new Map<string, DeliveryPlanningProjectSpec[]>();
    for (const { version, ...spec } of projects) {
      const key = version.trim() || "0.1.0";
      const withSharedFields = { ...spec, project_type: "creation" as const, working_directory_path: workingDirectoryPath || undefined };
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(withSharedFields);
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const allResults: DeliveryPlanningProjectResult[] = [];
      for (const [version, groupProjects] of groups) {
        const res = await authorize.mutateAsync({ conceptId, version, projects: groupProjects });
        allResults.push(...res.projects);
      }
      setResults(allResults);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      if (productId) {
        queryClient.invalidateQueries({ queryKey: ["products", productId, "versions"] });
      }
    } catch (e) {
      setSubmitError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const submitMaintenance = async () => {
    const selectedProj = productProjects.find((p) => p.id === selectedProjectId);
    if (!selectedProj) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await authorize.mutateAsync({
        conceptId,
        version: maintenanceVersion.trim() || "0.1.1",
        projects: [
          {
            project_name: maintenanceProjectName.trim() || selectedProj.name,
            solution_type: selectedProj.solution_type || "web_app",
            project_type: "maintenance",
            working_directory_path: workingDirectoryPath || undefined,
          },
        ],
      });
      setResults(res.projects);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      if (productId) {
        queryClient.invalidateQueries({ queryKey: ["products", productId, "versions"] });
      }
    } catch (e) {
      setSubmitError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteProject = (projectId: string, projectName: string) => {
    setPendingDeleteProject({ id: projectId, name: projectName });
  };

  const confirmDeleteProject = () => {
    if (!pendingDeleteProject) return;
    deleteProject.mutate(pendingDeleteProject.id, {
      onSuccess: () => {
        if (results) {
          setResults((prev) => prev ? prev.filter((r) => r.project_id !== pendingDeleteProject.id) : null);
        }
        queryClient.invalidateQueries({ queryKey: ["projects"] });
        setPendingDeleteProject(null);
      },
    });
  };

  const selectedExistingProject = productProjects.find((p) => p.id === selectedProjectId);
  const selectedProjectVersion = productVersions?.find((v) => v.id === selectedExistingProject?.product_version_id);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Defina se este escopo de concepção é um <strong>Novo Projeto</strong> ou uma <strong>Manutenção</strong> de projeto existente.
      </p>

      {/* Projetos Existentes no Produto */}
      {productProjects.length > 0 && (
        <div className="space-y-2 rounded-md border p-3 bg-muted/20">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Projetos Existentes no Produto ({productProjects.length})</p>
          {productProjects.map((p) => {
            const versionObj = productVersions?.find((v) => v.id === p.product_version_id);
            const resultInfo = results?.find((r) => r.project_id === p.id);
            return (
              <div key={p.id} className="flex flex-wrap items-center justify-between gap-2 text-sm border-b last:border-0 pb-2 last:pb-0">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{p.solution_type ? PROJECT_SOLUTION_TYPE_LABELS[p.solution_type] : "Geral"}</Badge>
                  {versionObj && <Badge variant="secondary">v{versionObj.version}</Badge>}
                  <Link to={`/projects/${p.id}`} className="text-primary font-medium hover:underline">
                    {p.name}
                  </Link>
                  {resultInfo && (
                    <span className="text-xs text-muted-foreground">
                      ({resultInfo.scope_items_created} escopos, {resultInfo.tasks_created} tasks)
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm" variant="outline" disabled={sync.isPending}
                    onClick={() => sync.mutate({ conceptId, projectId: p.id })}
                    title="Sincronizar documentos da concepção para o projeto"
                  >
                    {sync.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                    Sincronizar docs
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    title={t("developmentRequests.delete")}
                    onClick={() => handleDeleteProject(p.id, p.name)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>
            );
          })}
          {sync.isSuccess && (
            <p className="text-xs text-emerald-600 font-medium pt-1">
              Gravado: {sync.data.files_written.join(", ") || "(nenhum documento gerado ainda)"}
            </p>
          )}
        </div>
      )}

      {/* Seletor Prévio de Modalidade: Novo Projeto vs Manutenção */}
      <div className="space-y-2 pt-1">
        <Label className="text-sm font-semibold">Definição do Escopo</Label>
        <div className="grid grid-cols-2 gap-3 max-w-md">
          <button
            type="button"
            onClick={() => setActionType("creation")}
            className={`flex items-center gap-2.5 p-3 rounded-lg border text-left transition-all ${
              actionType === "creation"
                ? "border-primary bg-primary/10 text-primary ring-1 ring-primary font-semibold"
                : "border-input bg-background hover:bg-muted/40 text-muted-foreground"
            }`}
          >
            <Rocket className="h-4 w-4 shrink-0" />
            <div>
              <p className="text-xs font-bold">Novo Projeto</p>
              <p className="text-[10px] opacity-80">Criar nova aplicação ou camada</p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => setActionType("maintenance")}
            className={`flex items-center gap-2.5 p-3 rounded-lg border text-left transition-all ${
              actionType === "maintenance"
                ? "border-primary bg-primary/10 text-primary ring-1 ring-primary font-semibold"
                : "border-input bg-background hover:bg-muted/40 text-muted-foreground"
            }`}
          >
            <Wrench className="h-4 w-4 shrink-0" />
            <div>
              <p className="text-xs font-bold">Manutenção</p>
              <p className="text-[10px] opacity-80">Evoluir projeto existente</p>
            </div>
          </button>
        </div>
      </div>

      {/* CASO 1: NOVO PROJETO */}
      {actionType === "creation" && (
        <div className="space-y-3 rounded-lg border p-3.5 bg-muted/10">
          <Label className="text-xs font-semibold text-foreground">Definir Novos Projetos / Camadas</Label>
          {specs.map((spec, i) => (
            <div key={i} className="space-y-2 rounded-md border bg-background p-2.5">
              <div className="grid grid-cols-[160px_1fr_32px] gap-2 items-center">
                <Select value={spec.solution_type} onChange={(e) => updateSpec(i, { solution_type: e.target.value as ProjectSpecForm["solution_type"] })}>
                  {PROJECT_SOLUTION_TYPES.map((t) => <option key={t} value={t}>{PROJECT_SOLUTION_TYPE_LABELS[t]}</option>)}
                </Select>
                <Input placeholder="Nome do projeto (ex: Portal Web Factory)" value={spec.project_name} onChange={(e) => updateSpec(i, { project_name: e.target.value })} />
                <Button variant="ghost" size="icon" onClick={() => removeSpec(i)} disabled={specs.length === 1}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Versão Inicial</Label>
                  <Input placeholder="0.1.0" value={spec.version} onChange={(e) => updateSpec(i, { version: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-muted-foreground">Tipo</Label>
                  <Input value="Nova Implementação (Criação)" disabled className="bg-muted text-muted-foreground text-xs" />
                </div>
              </div>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={addSpec}><Plus className="mr-1.5 h-3.5 w-3.5" />Adicionar tipo de aplicação</Button>
          </div>
          <div className="pt-2">
            <Button disabled={submitting || specs.every((s) => !s.project_name.trim())} onClick={submitCreation}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              <Rocket className="mr-2 h-4 w-4" />Criar Novo Projeto
            </Button>
          </div>
        </div>
      )}

      {/* CASO 2: MANUTENÇÃO DE PROJETO EXISTENTE */}
      {actionType === "maintenance" && (
        <div className="space-y-4 rounded-lg border p-3.5 bg-muted/10">
          <Label className="text-xs font-semibold text-foreground">Selecionar Projeto Existente para Manutenção</Label>

          {productProjects.length === 0 ? (
            <div className="p-4 rounded-lg border border-amber-500/30 bg-amber-500/10 text-xs text-amber-700 dark:text-amber-400 space-y-2">
              <p className="font-semibold">Nenhum projeto existente encontrado para este produto.</p>
              <p>Para realizar manutenção, o produto precisa ter ao menos um projeto já criado. Alterne para a opção <strong>Novo Projeto</strong> acima para criar o projeto inicial.</p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Projeto a receber a manutenção:</Label>
                <Select
                  value={selectedProjectId}
                  onChange={(e) => handleSelectExistingProject(e.target.value)}
                >
                  {productProjects.map((p) => {
                    const v = productVersions?.find((x) => x.id === p.product_version_id);
                    return (
                      <option key={p.id} value={p.id}>
                        {p.name} ({p.solution_type ? PROJECT_SOLUTION_TYPE_LABELS[p.solution_type] : "Geral"} · v{v?.version || "0.1.0"})
                      </option>
                    );
                  })}
                </Select>
              </div>

              {selectedExistingProject && (
                <div className="rounded-md border bg-background p-3 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2">
                    <div className="space-y-0.5">
                      <p className="text-xs font-bold text-foreground">{selectedExistingProject.name}</p>
                      <p className="text-[11px] text-muted-foreground">
                        {selectedExistingProject.solution_type ? PROJECT_SOLUTION_TYPE_LABELS[selectedExistingProject.solution_type] : "Geral"} · Versão Atual: v{selectedProjectVersion?.version || "0.1.0"}
                      </p>
                    </div>
                    <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-600 bg-amber-500/10">
                      Modo: Manutenção
                    </Badge>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Nome / Identificação do Projeto</Label>
                      <Input
                        value={maintenanceProjectName}
                        onChange={(e) => setMaintenanceProjectName(e.target.value)}
                        placeholder="Nome do projeto"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Nova Versão da Manutenção (Patch / Minor)</Label>
                      <Input
                        value={maintenanceVersion}
                        onChange={(e) => setMaintenanceVersion(e.target.value)}
                        placeholder="0.1.1"
                      />
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 pt-2">
                    <Button
                      disabled={submitting || !maintenanceProjectName.trim() || !maintenanceVersion.trim()}
                      onClick={submitMaintenance}
                    >
                      {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      <Wrench className="mr-2 h-4 w-4" />Autorizar Manutenção do Projeto
                    </Button>

                    <Button
                      size="sm"
                      variant="outline"
                      disabled={sync.isPending}
                      onClick={() => sync.mutate({ conceptId, projectId: selectedExistingProject.id })}
                    >
                      {sync.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                      Sincronizar Docs c/ Projeto
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {submitError && <p className="text-sm text-destructive">Falha ao processar: {submitError}</p>}

      <ConfirmDialog
        open={pendingDeleteProject !== null}
        title={`Excluir projeto "${pendingDeleteProject?.name ?? ""}"?`}
        description="Isso excluirá o projeto permanentemente junto com suas tarefas e configurações. Esta ação não pode ser desfeita."
        confirmLabel="Excluir"
        loading={deleteProject.isPending}
        onConfirm={confirmDeleteProject}
        onCancel={() => setPendingDeleteProject(null)}
      />
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
  const saveConceptDocument = useSaveConceptDocument();
  const agents = useChattableAgents();
  const generateDraft = useStreamAgentDraft<"concept">();
  const generateTechStackDraft = useStreamAgentDraft<"tech_stack">();
  const generateContextSummary = useStreamAgentDraft<"context_summary">();
  const promptTemplate = usePromptTemplate("concept");
  const [selectedProduct, setSelectedProduct] = useState("");
  const concept = useConcept(selectedProduct);
  const [form, setForm] = useState(EMPTY_FORM);
  const [techStack, setTechStack] = useState<TechStackEntry[]>([]);
  // Step 1 "start": paste/upload a loose context .md, ask an agent to draft
  // the structured fields below from it -- prefills form/techStack for
  // review, never auto-saves (2026-08-15/16, Marcelo: "esse vai ser o
  // start... que pode ser processado pelo agente"). Regenerable any number
  // of times; the generated documentation draft is saved as a concept
  // document (overwriting the same filename each time) once a concept
  // exists -- immediately in edit mode, or right after creation for a new
  // idea (see submit()).
  const [contextAgentId, setContextAgentId] = useState("");
  const [contextText, setContextText] = useState("");
  const [contextGenerating, setContextGenerating] = useState(false);
  const [contextError, setContextError] = useState<string | null>(null);
  const [pendingContextDoc, setPendingContextDoc] = useState<string | null>(null);
  // "Upload file" below the Context textarea (2026-08-16, Marcelo: "eu estou
  // criticando que precisa ser mais completo... é melhor eu enviar um
  // arquivo md grande e gerar um resumo no campo de texto" / "apos o envio
  // gere o resumo do texto que caiba no campo" / "o arquivo será utilizado
  // para o contexto para o preechimento do formulário") -- a large uploaded
  // .md is summarized via target_kind="context_summary" (see
  // core/ai_draft.py) down to something that fits the textarea and reads
  // well, then replaces contextText so "Generate from context" above works
  // on it exactly like manually pasted/trimmed context. Requires an agent
  // (same selector as the rest of Step 1) since summarizing is itself an
  // agent call, not a client-side truncation.
  const contextFileInputRef = useRef<HTMLInputElement>(null);
  const [contextUploading, setContextUploading] = useState(false);
  // Step 4 "Tech stack" own generate action -- same agent selected in Step 1
  // (2026-08-16, Marcelo: "ele será o agente responsável por gerar a
  // documentação"), grounded in help/TECH_STACK_GUIDE.md + the current
  // tech_stack_options catalog (see core/ai_draft.py's "tech_stack"
  // instructions) instead of the model's own general knowledge (Marcelo:
  // "preciso dar a nossa base de tecnologia a ser aplicado nos produtos.
  // São nossas ferramentas"). Separate loading/error state from the Step 1
  // context generation so the two actions don't fight over one spinner.
  const [stackGenerating, setStackGenerating] = useState(false);
  const [stackError, setStackError] = useState<string | null>(null);
  // "Ver catálogo completo" toggle (2026-08-16, Marcelo: "não entendi essa
  // referência. Pensei em consultar todos as tech stack") -- a recap of
  // only the entries already added below was redundant with those same
  // rows; what's actually useful for consultation is the full org catalog
  // per layer, browsable before deciding what to add. One hook call per
  // fixed layer (rules of hooks -- TECH_STACK_LAYERS can't be .map()ed here).
  const [catalogOpen, setCatalogOpen] = useState(false);
  const allTechOptions = useAllTechStackOptions();
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
    setTechStack(techStackToEntries(revision?.tech_stack_decisions));
  }, [editingRequest, concept.data]);

  const conceptEditable = !concept.data || ["draft", "rework"].includes(concept.data.concept.status);

  const generateConceptDraft = async () => {
    if (!contextAgentId || !contextText.trim()) return;
    setContextError(null);
    setContextGenerating(true);
    try {
      const draft = await generateDraft({ agent_id: contextAgentId, target_kind: "concept", context: contextText });
      setForm((f) => ({
        ...f,
        name: draft.name || f.name,
        problem_statement: draft.problem_statement || f.problem_statement,
        vision: draft.vision ?? f.vision,
        scope_summary: draft.scope_summary ?? f.scope_summary,
        project_description: draft.project_description ?? f.project_description,
      }));
      const draftedStack = draft.tech_stack.filter((item): item is typeof item & { decision: string } => Boolean(item.decision?.trim()));
      if (draftedStack.length) {
        setTechStack(draftedStack.map((item) => ({
          key: crypto.randomUUID(), layer: item.layer, decision: item.decision, rationale: item.rationale ?? "",
        })));
      }
      if (draft.documentation_markdown) {
        setPendingContextDoc(draft.documentation_markdown);
        // Concept already exists (edit mode) -- save immediately so the
        // draft is visible in Step 6 right away; for a brand-new idea
        // there's no concept yet, submit() saves it right after creation.
        if (concept.data?.concept.id) {
          await saveConceptDocument.mutateAsync({
            conceptId: concept.data.concept.id, filename: CONTEXT_DRAFT_DOC_FILENAME, content: draft.documentation_markdown,
          });
        }
      }
    } catch (err) {
      setContextError(err instanceof Error ? err.message : String(err));
    } finally {
      setContextGenerating(false);
    }
  };

  const handleContextFileUpload = async (file: File) => {
    if (!contextAgentId) {
      setContextError(t("wizard.context.uploadNoAgent"));
      return;
    }
    setContextError(null);
    setContextUploading(true);
    try {
      const raw = await file.text();
      const summary = await generateContextSummary({
        agent_id: contextAgentId, target_kind: "context_summary", context: raw.slice(0, 100_000),
      });
      setContextText(summary.summary);
    } catch (err) {
      setContextError(err instanceof Error ? err.message : String(err));
    } finally {
      setContextUploading(false);
    }
  };

  const generateTechStack = async () => {
    if (!contextAgentId) return;
    setStackError(null);
    setStackGenerating(true);
    try {
      const stackContext = [
        form.name, form.problem_statement, form.vision, form.scope_summary, form.project_description,
      ].filter((part) => part.trim().length > 0).join("\n\n");
      const draft = await generateTechStackDraft({ agent_id: contextAgentId, target_kind: "tech_stack", context: stackContext });
      const draftedStack = draft.tech_stack.filter((item): item is typeof item & { decision: string } => Boolean(item.decision?.trim()));
      if (draftedStack.length) {
        setTechStack(draftedStack.map((item) => ({
          key: crypto.randomUUID(), layer: item.layer, decision: item.decision, rationale: item.rationale ?? "",
        })));
      }
    } catch (err) {
      setStackError(err instanceof Error ? err.message : String(err));
    } finally {
      setStackGenerating(false);
    }
  };

  const startEdit = (item: DevelopmentRequest) => {
    setForm({
      name: item.title, problem_statement: item.description, vision: "", scope_summary: "",
      requested_by: item.requested_by ?? "", project_description: "", working_directory_path: "",
    });
    setTechStack([]);
    setContextAgentId(""); setContextText(""); setContextError(null); setPendingContextDoc(null); setStackError(null);
    setSelectedProduct(item.product_id);
    setEditingRequest(item);
    setView("form");
  };

  const backToList = () => {
    setEditingRequest(null);
    setForm(EMPTY_FORM);
    setTechStack([]);
    setContextAgentId(""); setContextText(""); setContextError(null); setPendingContextDoc(null); setStackError(null);
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
      const created = await create.mutateAsync({
        ...form,
        project_description: form.project_description || undefined,
        working_directory_path: form.working_directory_path || undefined,
        tech_stack_decisions: tech_stack_decisions.length ? tech_stack_decisions : undefined,
      });
      if (pendingContextDoc) {
        await saveConceptDocument.mutateAsync({
          conceptId: created.concept.id, filename: CONTEXT_DRAFT_DOC_FILENAME, content: pendingContextDoc,
        });
      }
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
        <form noValidate onSubmit={submit}>
        <CardContent className="space-y-8">
          <section className="space-y-4">
            <h3 className="text-sm font-semibold">{t("wizard.steps.pipeline")}</h3>
            <p className="text-sm text-muted-foreground">{t("wizard.context.help")}</p>
            <div className="space-y-2">
              <Label>{t("wizard.context.contextLabel")}</Label>
              <Textarea
                className="resize-none"
                rows={8} placeholder={t("wizard.context.contextPlaceholder")}
                value={contextText} onChange={(e) => setContextText(e.target.value)}
              />
              <input
                ref={contextFileInputRef} type="file" accept=".md,.markdown,.txt" className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) void handleContextFileUpload(file);
                }}
              />
              <Button
                type="button" variant="outline" size="sm"
                onClick={() => contextFileInputRef.current?.click()}
                disabled={contextUploading}
                title={!contextAgentId ? t("wizard.context.uploadNoAgent") : undefined}
              >
                {contextUploading
                  ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  : <Upload className="mr-2 h-4 w-4" />}
                {t("wizard.context.upload")}
              </Button>
            </div>
            {contextError && <p className="text-sm text-destructive">{contextError}</p>}
            <div className="flex items-center gap-3">
              <Button
                type="button" variant="outline"
                onClick={() => void generateConceptDraft()}
                disabled={!contextAgentId || !contextText.trim() || contextGenerating}
              >
                {contextGenerating
                  ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  : <Sparkles className="mr-2 h-4 w-4" />}
                {t("wizard.context.generate")}
              </Button>
              <Select
                className="w-56"
                aria-label={t("wizard.context.agentLabel")}
                value={contextAgentId} onChange={(e) => setContextAgentId(e.target.value)}
              >
                <option value="">{t("wizard.context.selectAgent")}</option>
                {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </Select>
              <CopyButton
                title={t("wizard.context.copyPrompt")}
                label={t("wizard.context.copyPromptLabel")}
                getText={() => promptTemplate.data?.instructions ?? ""}
              />
              {pendingContextDoc && <span className="text-xs text-muted-foreground">{t("wizard.context.appliedHint")}</span>}
            </div>
          </section>

          <section className="space-y-4 border-t pt-8">
            <h3 className="text-sm font-semibold">{t("wizard.steps.problem")}</h3>
            <div className="space-y-2"><FieldLabel label={t("captureIdea.fields.name")} count={form.name.length} max={NAME_MAX}/><Input maxLength={NAME_MAX} value={form.name} onChange={e => setForm({...form, name:e.target.value})}/></div>
            <div className="space-y-2">
              <FieldLabel label={t("captureIdea.fields.problemStatement")} count={form.problem_statement.length} max={PROBLEM_STATEMENT_MAX}/>
              <Textarea className="resize-none" rows={4} maxLength={PROBLEM_STATEMENT_MAX} value={form.problem_statement} onChange={e => setForm({...form, problem_statement:e.target.value})}/>
            </div>
            <div className="space-y-2">
              <FieldLabel label={t("captureIdea.fields.vision")} count={form.vision.length} max={VISION_MAX}/>
              <Textarea className="resize-none" rows={3} maxLength={VISION_MAX} value={form.vision} onChange={e => setForm({...form, vision:e.target.value})}/>
            </div>
            <div className="space-y-2">
              <FieldLabel label={t("captureIdea.fields.initialScope")} count={form.scope_summary.length} max={SCOPE_SUMMARY_MAX}/>
              <Textarea className="resize-none" rows={3} maxLength={SCOPE_SUMMARY_MAX} value={form.scope_summary} onChange={e => setForm({...form, scope_summary:e.target.value})}/>
            </div>
          </section>

          <section className="space-y-4 border-t pt-8">
            <h3 className="text-sm font-semibold">{t("wizard.steps.description")}</h3>
            <p className="text-sm text-muted-foreground">{t("wizard.description.help")}</p>
            <div className="space-y-2"><FieldLabel label={t("wizard.description.fields.projectDescription")} count={form.project_description.length} max={PROJECT_DESCRIPTION_MAX}/><Textarea className="resize-none" rows={6} maxLength={PROJECT_DESCRIPTION_MAX} value={form.project_description} onChange={e => setForm({...form, project_description:e.target.value})}/></div>
            <div className="space-y-2">
              <Label>{t("wizard.description.fields.workingDirectory")}</Label>
              <div className="flex items-center gap-2">
                <Input placeholder={t("wizard.description.workingDirectoryPlaceholder")} value={form.working_directory_path} onChange={e => setForm({...form, working_directory_path:e.target.value})}/>
                <WorkingDirPicker workingDir={form.working_directory_path || undefined} onSelect={(path) => setForm({...form, working_directory_path: path ?? ""})}/>
              </div>
            </div>
          </section>

          <section className="space-y-4 border-t pt-8">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold">{t("wizard.steps.stack")}</h3>
              <Button type="button" variant="ghost" size="sm" onClick={() => setCatalogOpen((v) => !v)}>
                {catalogOpen ? t("wizard.stack.hideCatalog") : t("wizard.stack.viewCatalog")}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">{t("wizard.stack.help")}</p>
            {catalogOpen && (
              <div className="grid gap-4 rounded-lg border bg-muted/30 p-3 md:grid-cols-3">
                {/* "frontend" splits into 5 scenario groups (platform), since
                 * they're different toolchains lumped under one layer -- every
                 * other layer stays a single group (2026-08-16, Marcelo:
                 * "faltou para mobile", then dictated the full list: "web app,
                 * landing page, site institucional, PWA, mobile"). An
                 * unclassified frontend option (platform=null) defaults into
                 * web_app, the org's own default recommendation. */}
                {TECH_STACK_LAYERS.map((layer) => {
                  const options = (allTechOptions.data ?? []).filter((o) => o.layer === layer);
                  return (
                    <div key={layer} className="space-y-1.5">
                      <p className="text-xs font-semibold">{t(`wizard.stack.layers.${layer}`)}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {options.map((option) => (
                          <Badge key={option.id} variant="outline" className="font-normal" title={option.description ?? undefined}>
                            {option.name}
                          </Badge>
                        ))}
                        {options.length === 0 && (
                          <span className="text-xs text-muted-foreground">{t("wizard.stack.catalogEmpty")}</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            {techStack.length === 0 && (
              <p className="text-sm text-muted-foreground">{t("wizard.stack.empty")}</p>
            )}
            {techStack.map((entry) => (
              <div key={entry.key} className="grid gap-3 rounded-lg border p-3 md:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_minmax(0,1fr)_auto]">
                <div className="space-y-2">
                  <Label>{t("wizard.stack.layer")}</Label>
                  <Select
                    value={entry.layer}
                    onChange={(e) => {
                      const layer = e.target.value as TechStackLayer;
                      setTechStack(techStack.map((item) => item.key === entry.key ? { ...item, layer, decision: "" } : item));
                    }}
                  >
                    {TECH_STACK_LAYERS.map((layer) => (
                      <option key={layer} value={layer}>{t(`wizard.stack.layers.${layer}`)}</option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t("wizard.stack.technology")}</Label>
                  <TechStackOptionPicker
                    layer={entry.layer}
                    value={entry.decision}
                    onChange={(decision) => setTechStack(techStack.map((item) => item.key === entry.key ? { ...item, decision } : item))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>{t("wizard.stack.rationale")}</Label>
                  <Input
                    value={entry.rationale}
                    onChange={(e) => setTechStack(techStack.map((item) => item.key === entry.key ? { ...item, rationale: e.target.value } : item))}
                  />
                </div>
                <div className="flex items-end">
                  <Button
                    type="button" variant="ghost" size="icon"
                    aria-label={t("wizard.stack.remove")}
                    onClick={() => setTechStack(techStack.filter((item) => item.key !== entry.key))}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button" variant="outline" size="sm"
                onClick={() => setTechStack([...techStack, { key: crypto.randomUUID(), layer: "frontend", decision: "", rationale: "" }])}
              >
                <Plus className="mr-2 h-4 w-4" />{t("wizard.stack.add")}
              </Button>
              <Button
                type="button" variant="outline" size="sm"
                onClick={() => void generateTechStack()}
                disabled={!contextAgentId || stackGenerating}
                title={!contextAgentId ? t("wizard.stack.generateNoAgent") : undefined}
              >
                {stackGenerating
                  ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  : <Sparkles className="mr-2 h-4 w-4" />}
                {t("wizard.stack.generate")}
              </Button>
            </div>
            {!contextAgentId && <p className="text-xs text-muted-foreground">{t("wizard.stack.generateNoAgent")}</p>}
            {stackError && <p className="text-sm text-destructive">{stackError}</p>}
          </section>

          <section className="space-y-4 border-t pt-8">
            <h3 className="text-sm font-semibold">{t("wizard.steps.delivery")}</h3>
            <ProjectPlanningPanel
              productId={concept.data?.concept.product_id}
              conceptId={concept.data?.concept.id}
              workingDirectoryPath={form.working_directory_path}
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
