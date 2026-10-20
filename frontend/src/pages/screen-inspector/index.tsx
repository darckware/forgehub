import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Layout,
  Loader2,
  Plus,
  Trash2,
  Wand2,
  Maximize2,
  Minimize2,
  FileText,
  Eye,
  Columns,
  Copy,
  Check,
  Image as ImageIcon,
  Code,
  Upload,
  Sparkles,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Database,
  Layers,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Markdown } from "@/components/Markdown";
import { useProjects } from "@/hooks/useProject";
import { useEnsureProjectScope, useProjectScopes } from "@/hooks/useSystemScope";
import {
  useCreateScreen,
  useDeriveDatabase,
  useRemoveScreen,
  useSaveScreenBusinessRule,
  useScreenBusinessRule,
  useScreens,
  useUpdateScreen,
  type Screen,
  type ScreenAttribute,
  type ScreenAttributeType,
} from "@/hooks/useScreenRegistry";

const ATTRIBUTE_TYPES: ScreenAttributeType[] = ["string", "number", "boolean", "date", "relation"];
const EMPTY_ATTRIBUTE: ScreenAttribute = { name: "", type: "string", required: false, description: "" };

const CSS_FRAMEWORK_PRESETS: Record<string, { label: string; head: string }> = {
  plain: { label: "CSS Padrão", head: "" },
  tailwind: {
    label: "Tailwind CSS (CDN)",
    head: '<script src="https://cdn.tailwindcss.com"></script>',
  },
  bootstrap: {
    label: "Bootstrap 5.3",
    head: '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">',
  },
};

export default function ScreenInspectorPage() {
  const { t } = useTranslation("screenInspector");
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const scopes = useProjectScopes(projectId);
  const ensureScope = useEnsureProjectScope();
  const [scopeId, setScopeId] = useState("");
  useEffect(() => setScopeId(scopes.data?.[0]?.id || ""), [scopes.data]);

  const screens = useScreens(scopeId);
  const createScreen = useCreateScreen();
  const updateScreen = useUpdateScreen();
  const removeScreen = useRemoveScreen();
  const deriveDatabase = useDeriveDatabase();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    if (!screens.data?.some((s) => s.element.id === selectedId)) {
      setSelectedId(screens.data?.[0]?.element.id ?? null);
    }
  }, [screens.data, selectedId]);

  const selected = screens.data?.find((s) => s.element.id === selectedId) ?? null;
  const activeProject = projects.data?.find((p) => p.id === projectId);

  const [newScreenName, setNewScreenName] = useState("");
  const [creating, setCreating] = useState(false);

  const filteredScreens = useMemo(() => {
    if (!screens.data) return [];
    if (!searchFilter.trim()) return screens.data;
    const term = searchFilter.toLowerCase();
    return screens.data.filter(
      (s) =>
        s.element.name.toLowerCase().includes(term) ||
        s.element.stable_key.toLowerCase().includes(term)
    );
  }, [screens.data, searchFilter]);

  const submitNewScreen = async () => {
    const name = newScreenName.trim();
    if (!name || !projectId) return;
    setCreating(true);
    try {
      let targetScopeId = scopeId;
      if (!targetScopeId) {
        const ensured = await ensureScope.mutateAsync(projectId);
        targetScopeId = ensured.id;
        setScopeId(ensured.id);
      }
      const created = await createScreen.mutateAsync({ scopeId: targetScopeId, name, spec: { attributes: [] } });
      setNewScreenName("");
      setSelectedId(created.element.id);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header com Contextualização da Concepção */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b pb-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent">
            <Layout className="h-6 w-6 text-primary" />
            {t("page.title")}
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-3xl leading-relaxed">
            {t("page.description")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!scopeId || deriveDatabase.isPending}
            onClick={() => deriveDatabase.mutate(scopeId)}
            className="gap-1.5 text-xs"
          >
            {deriveDatabase.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4 text-primary" />}
            {t("page.deriveDatabase")}
          </Button>
          <Link
            to="/concept-erd"
            className="inline-flex items-center gap-1.5 text-xs rounded-md border border-input bg-background px-3 py-1.5 font-medium hover:bg-accent"
          >
            <Database className="h-4 w-4 text-primary" />
            {t("page.viewErd")}
          </Link>
        </div>
      </div>

      {/* Seletores de Projeto e Escopo */}
      <Card className="border-border/60 bg-card/60">
        <CardContent className="grid gap-4 py-4 md:grid-cols-2">
          <div>
            <Label className="text-xs font-semibold text-muted-foreground">{t("selectors.project")}</Label>
            <Select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="mt-1">
              <option value="">{t("selectors.selectProject")}</option>
              {projects.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label className="text-xs font-semibold text-muted-foreground">{t("selectors.scope")}</Label>
            <Select value={scopeId} onChange={(e) => setScopeId(e.target.value)} disabled={!projectId} className="mt-1">
              <option value="">{t("selectors.selectScope")}</option>
              {scopes.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {t("selectors.revision", { revision: s.revision, status: s.status })}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      {deriveDatabase.isSuccess && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-700 dark:text-emerald-300">
          <span>
            {t("page.deriveSuccess", { created: deriveDatabase.data.tables_created, updated: deriveDatabase.data.tables_updated, fields: deriveDatabase.data.fields_written })}
          </span>
          <Link to="/concept-erd" className="font-semibold underline hover:text-emerald-800">
            {t("page.openErd")}
          </Link>
        </div>
      )}

      {!projectId ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            <Layers className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" />
            {t("empty.selectProject")}
          </CardContent>
        </Card>
      ) : !scopeId ? (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="py-10 text-center space-y-3">
            <Layout className="mx-auto h-10 w-10 text-primary" />
            <h3 className="text-sm font-bold">{t("empty.noScopeTitle")}</h3>
            <p className="text-xs text-muted-foreground max-w-md mx-auto">
              {t("empty.noScopeDescription")}
            </p>
            <Button
              onClick={() => ensureScope.mutate(projectId)}
              disabled={ensureScope.isPending}
              className="text-xs gap-1.5"
            >
              {ensureScope.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {t("empty.initializeScope")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className={`grid gap-6 transition-all ${sidebarCollapsed ? "grid-cols-1" : "xl:grid-cols-[280px_1fr]"}`}>
          {/* Barra Lateral de Telas */}
          {!sidebarCollapsed && (
            <Card className="flex flex-col h-[calc(100vh-280px)] min-h-[500px]">
              <CardHeader className="p-3 border-b flex flex-row items-center justify-between space-y-0">
                <div>
                  <CardTitle className="text-sm font-semibold">{t("sidebar.title")}</CardTitle>
                  <CardDescription className="text-[11px]">{t("sidebar.registered", { count: screens.data?.length ?? 0 })}</CardDescription>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground"
                  onClick={() => setSidebarCollapsed(true)}
                  title={t("sidebar.collapse")}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
              </CardHeader>
              <CardContent className="p-3 space-y-3 flex-1 flex flex-col min-h-0">
                <div className="flex gap-1.5">
                  <Input
                    className="h-8 text-xs"
                    placeholder={t("sidebar.newScreen")}
                    value={newScreenName}
                    onChange={(e) => setNewScreenName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        submitNewScreen();
                      }
                    }}
                  />
                  <Button size="sm" className="h-8 px-2.5" disabled={!newScreenName.trim() || creating} onClick={submitNewScreen}>
                    {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  </Button>
                </div>

                <Input
                  className="h-7 text-xs bg-muted/30"
                  placeholder={t("sidebar.filter")}
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                />

                <div className="space-y-1.5 overflow-y-auto flex-1 pr-1">
                  {screens.isLoading && <p className="text-xs text-muted-foreground py-4 text-center">{t("common.loading")}</p>}
                  {filteredScreens.length === 0 && !screens.isLoading && (
                    <p className="text-xs text-muted-foreground py-6 text-center">{t("sidebar.noScreens")}</p>
                  )}
                  {filteredScreens.map((s) => {
                    const isSelected = selectedId === s.element.id;
                    const attrCount = s.revision.spec_snapshot.attributes?.length ?? 0;
                    const hasHtml = Boolean(s.revision.spec_snapshot.prototype_html?.trim());
                    const imageCount = s.revision.spec_snapshot.image_refs?.length ?? 0;
                    return (
                      <button
                        key={s.element.id}
                        type="button"
                        onClick={() => setSelectedId(s.element.id)}
                        className={`w-full rounded-md border p-2 text-left text-xs transition-all ${
                          isSelected
                            ? "border-primary bg-primary/10 font-semibold shadow-xs"
                            : "hover:bg-accent/50 border-border/50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1">
                          <p className="truncate">{s.element.name}</p>
                          {isSelected && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
                        </div>
                        <div className="mt-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                          <span>{t("sidebar.fields", { count: attrCount })}</span>
                          {hasHtml && <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">HTML</Badge>}
                          {imageCount > 0 && <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">{t("sidebar.images", { count: imageCount })}</Badge>}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Área Principal de Trabalho da Tela */}
          <div className="min-w-0 flex-1">
            {selected ? (
              <ScreenWorkspace
                key={selected.element.id}
                scopeId={scopeId}
                projectName={activeProject?.name ?? t("common.project")}
                screen={selected}
                sidebarCollapsed={sidebarCollapsed}
                onExpandSidebar={() => setSidebarCollapsed(false)}
                onUpdate={updateScreen}
                onRemove={() => {
                  removeScreen.mutate({ scopeId, elementId: selected.element.id });
                  setSelectedId(null);
                }}
              />
            ) : (
              <Card>
                <CardContent className="py-16 text-center text-sm text-muted-foreground">
                  {t("empty.selectScreen")}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface ScreenWorkspaceProps {
  scopeId: string;
  projectName: string;
  screen: Screen;
  sidebarCollapsed: boolean;
  onExpandSidebar: () => void;
  onUpdate: ReturnType<typeof useUpdateScreen>;
  onRemove: () => void;
}

function ScreenWorkspace({
  scopeId,
  projectName,
  screen,
  sidebarCollapsed,
  onExpandSidebar,
  onUpdate,
  onRemove,
}: ScreenWorkspaceProps) {
  const { t, i18n } = useTranslation("screenInspector");
  const elementId = screen.element.id;
  const [mainTab, setMainTab] = useState("preview");
  const [isFullscreen, setIsFullscreen] = useState(false);

  const [screenName, setScreenName] = useState(screen.element.name);
  const [attributes, setAttributes] = useState<ScreenAttribute[]>(screen.revision.spec_snapshot.attributes ?? []);
  const [prototypeMode, setPrototypeMode] = useState<"html" | "template">(
    screen.revision.spec_snapshot.template_ref || (screen.revision.spec_snapshot.image_refs && screen.revision.spec_snapshot.image_refs.length > 0)
      ? "template"
      : "html"
  );
  const [prototypeHtml, setPrototypeHtml] = useState(screen.revision.spec_snapshot.prototype_html ?? "");
  const [cssFramework, setCssFramework] = useState(screen.revision.spec_snapshot.css_framework ?? "plain");
  const [templateRef, setTemplateRef] = useState(screen.revision.spec_snapshot.template_ref ?? "");
  const [imageRefs, setImageRefs] = useState<string[]>(screen.revision.spec_snapshot.image_refs ?? []);
  const [newImageUrl, setNewImageUrl] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Business Rule data
  const businessRule = useScreenBusinessRule(scopeId, elementId);
  const saveBusinessRule = useSaveScreenBusinessRule();
  const [ruleContent, setRuleContent] = useState("");
  const [mdTab, setMdTab] = useState<"edit" | "preview" | "split">("split");
  const [copiedPath, setCopiedPath] = useState(false);
  const [copiedPrompt, setCopiedPrompt] = useState(false);

  useEffect(() => {
    setScreenName(screen.element.name);
    setAttributes(screen.revision.spec_snapshot.attributes ?? []);
    setPrototypeMode(
      screen.revision.spec_snapshot.template_ref || (screen.revision.spec_snapshot.image_refs && screen.revision.spec_snapshot.image_refs.length > 0)
        ? "template"
        : "html"
    );
    setPrototypeHtml(screen.revision.spec_snapshot.prototype_html ?? "");
    setCssFramework(screen.revision.spec_snapshot.css_framework ?? "plain");
    setTemplateRef(screen.revision.spec_snapshot.template_ref ?? "");
    setImageRefs(screen.revision.spec_snapshot.image_refs ?? []);
  }, [screen]);

  useEffect(() => {
    if (businessRule.data) {
      setRuleContent(businessRule.data.content || "");
    }
  }, [businessRule.data]);

  const saveSpec = (patch: Record<string, unknown>) => {
    onUpdate.mutate({ scopeId, elementId, spec: patch });
  };

  const updateAttribute = (index: number, patch: Partial<ScreenAttribute>) => {
    const next = attributes.map((a, i) => (i === index ? { ...a, ...patch } : a));
    setAttributes(next);
    saveSpec({ attributes: next });
  };

  const addAttribute = () => {
    const next = [...attributes, { ...EMPTY_ATTRIBUTE }];
    setAttributes(next);
    saveSpec({ attributes: next });
  };

  const removeAttribute = (index: number) => {
    const next = attributes.filter((_, i) => i !== index);
    setAttributes(next);
    saveSpec({ attributes: next });
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const file = files[0];
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      const next = [...imageRefs, dataUrl];
      setImageRefs(next);
      saveSpec({ image_refs: next });
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const handleAddImageUrl = () => {
    const url = newImageUrl.trim();
    if (!url) return;
    const next = [...imageRefs, url];
    setImageRefs(next);
    setNewImageUrl("");
    saveSpec({ image_refs: next });
  };

  const handleRemoveImage = (index: number) => {
    const next = imageRefs.filter((_, i) => i !== index);
    setImageRefs(next);
    saveSpec({ image_refs: next });
  };

  // Safe doc relative path
  const filePath =
    businessRule.data?.file_path ||
    `projects/${projectName.toLowerCase().replace(/[^a-z0-9_-]+/g, "-")}/business-rules/${screen.element.stable_key}.md`;

  const handleCopyPath = async () => {
    await navigator.clipboard.writeText(filePath);
    setCopiedPath(true);
    setTimeout(() => setCopiedPath(false), 2000);
  };

  const handleCopyAgentPrompt = async () => {
    const attrFormatted = attributes.map((a) => `- ${a.name} (${a.type}${a.required ? `, ${t("prompt.required")}` : ""})`).join("\n");
    const prompt = t("prompt.template", { name: screen.element.name, path: filePath, attributes: attrFormatted || t("prompt.noAttributes") });
    await navigator.clipboard.writeText(prompt);
    setCopiedPrompt(true);
    setTimeout(() => setCopiedPrompt(false), 2000);
  };

  const generatedHtmlDoc = useMemo(() => {
    const headExtra = CSS_FRAMEWORK_PRESETS[cssFramework]?.head || "";
    return `<!DOCTYPE html>
<html lang="${i18n.language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${screen.element.name}</title>
  ${headExtra}
  <style>
    body { margin: 0; padding: 16px; font-family: system-ui, -apple-system, sans-serif; }
  </style>
</head>
<body>
${prototypeHtml || `<div style="color: #888; text-align: center; padding: 40px;">${t("preview.noHtml")}</div>`}
</body>
</html>`;
  }, [prototypeHtml, cssFramework, screen.element.name, i18n.language, t]);

  return (
    <div className={`space-y-4 ${isFullscreen ? "fixed inset-0 z-50 bg-background p-6 overflow-y-auto" : ""}`}>
      {/* Topo do Workspace da Tela */}
      <Card className="border-border/70 shadow-xs">
        <CardHeader className="p-4 flex flex-row items-center justify-between gap-4 space-y-0">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {sidebarCollapsed && (
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={onExpandSidebar}
                title={t("sidebar.expand")}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            )}
            <div className="flex-1 min-w-0">
              <Input
                className="h-8 text-base font-bold max-w-md bg-transparent hover:bg-muted/40 focus:bg-background"
                value={screenName}
                onChange={(e) => setScreenName(e.target.value)}
                onBlur={() => {
                  if (screenName.trim() && screenName !== screen.element.name) {
                    onUpdate.mutate({ scopeId, elementId, name: screenName.trim() });
                  }
                }}
              />
              <div className="flex items-center gap-2 mt-1">
                <Badge variant="outline" className="text-[10px] font-mono">
                  {screen.element.stable_key}
                </Badge>
                <span className="text-[11px] text-muted-foreground">
                  {t("workspace.mdFile")} <code className="text-[10px] text-primary">{filePath}</code>
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              className="gap-1 text-xs"
              onClick={() => setIsFullscreen((v) => !v)}
              title={isFullscreen ? t("workspace.exitFullscreen") : t("workspace.enterFullscreen")}
            >
              {isFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
              {isFullscreen ? t("workspace.reduce") : t("workspace.fullscreen")}
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={onRemove} title={t("workspace.removeScreen")}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
      </Card>

      {/* Abas Principais: Visual / MD / Atributos */}
      <Tabs value={mainTab} onValueChange={setMainTab} className="space-y-4">
        <TabsList className="grid grid-cols-3 w-full max-w-xl bg-muted/60 p-1">
          <TabsTrigger value="preview" className="gap-1.5 text-xs">
            <Eye className="h-3.5 w-3.5" />
            {t("tabs.visual")}
          </TabsTrigger>
          <TabsTrigger value="markdown" className="gap-1.5 text-xs">
            <FileText className="h-3.5 w-3.5" />
            {t("tabs.rules")}
          </TabsTrigger>
          <TabsTrigger value="attributes" className="gap-1.5 text-xs">
            <Layers className="h-3.5 w-3.5" />
            {t("tabs.attributes")}
          </TabsTrigger>
        </TabsList>

        {/* ================= ABA 1: VISUAL DA TELA (ÁREA TOTAL / PREVIEW) ================= */}
        <TabsContent value="preview" className="space-y-4">
          <Card className="border-border/70">
            <CardHeader className="p-4 border-b flex flex-row items-center justify-between space-y-0">
              <div className="flex items-center gap-3">
                <span className="text-xs font-semibold text-muted-foreground">{t("preview.mode")}</span>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant={prototypeMode === "html" ? "default" : "outline"}
                    className="h-7 text-xs"
                    onClick={() => {
                      setPrototypeMode("html");
                      saveSpec({ prototype_html: prototypeHtml, template_ref: null });
                    }}
                  >
                    <Code className="mr-1 h-3.5 w-3.5" /> {t("preview.renderedHtml")}
                  </Button>
                  <Button
                    size="sm"
                    variant={prototypeMode === "template" ? "default" : "outline"}
                    className="h-7 text-xs"
                    onClick={() => {
                      setPrototypeMode("template");
                      saveSpec({ template_ref: templateRef });
                    }}
                  >
                    <ImageIcon className="mr-1 h-3.5 w-3.5" /> {t("preview.imagesAndMockups")}
                  </Button>
                </div>
              </div>

              {prototypeMode === "html" && (
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-muted-foreground">CSS:</Label>
                  <Select
                    value={cssFramework}
                    onChange={(e) => {
                      setCssFramework(e.target.value);
                      saveSpec({ css_framework: e.target.value });
                    }}
                    className="h-7 text-xs w-36"
                  >
                    {Object.entries(CSS_FRAMEWORK_PRESETS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {k === "plain" ? t("preview.plainCss") : v.label}
                      </option>
                    ))}
                  </Select>
                </div>
              )}
            </CardHeader>

            <CardContent className="p-4 space-y-4">
              {prototypeMode === "html" ? (
                <div className="grid gap-4 xl:grid-cols-2">
                  {/* Editor HTML */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs font-semibold flex items-center gap-1.5">
                        <Code className="h-3.5 w-3.5 text-primary" />
                        {t("preview.htmlCode")}
                      </Label>
                      <span className="text-[10px] text-muted-foreground">{t("preview.autosave")}</span>
                    </div>
                    <Textarea
                      rows={18}
                      className="resize-none font-mono text-xs leading-relaxed bg-muted/20"
                      placeholder={t("preview.htmlPlaceholder")}
                      value={prototypeHtml}
                      onChange={(e) => setPrototypeHtml(e.target.value)}
                      onBlur={() => saveSpec({ prototype_html: prototypeHtml, css_framework: cssFramework })}
                    />
                  </div>

                  {/* Renderizador / Preview em Área Total */}
                  <div className="space-y-2 flex flex-col">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs font-semibold flex items-center gap-1.5">
                        <Eye className="h-3.5 w-3.5 text-primary" />
                        {t("preview.renderedPreview")}
                      </Label>
                      <Badge variant="outline" className="text-[10px]">
                        {t("preview.sandboxIframe")}
                      </Badge>
                    </div>
                    <div className="flex-1 rounded-md border bg-white dark:bg-zinc-950 overflow-hidden min-h-[350px]">
                      <iframe
                        title={t("preview.screenPreviewTitle")}
                        sandbox="allow-scripts"
                        srcDoc={generatedHtmlDoc}
                        className="w-full h-full min-h-[420px] border-0"
                      />
                    </div>
                  </div>
                </div>
              ) : (
                /* Imagens e Mockups de Referência */
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 p-3 rounded-lg bg-muted/30 border">
                    <div className="flex items-center gap-2 flex-1 min-w-[280px]">
                      <Input
                        className="h-8 text-xs flex-1"
                        placeholder={t("preview.imageUrlPlaceholder")}
                        value={newImageUrl}
                        onChange={(e) => setNewImageUrl(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            handleAddImageUrl();
                          }
                        }}
                      />
                      <Button size="sm" className="h-8 px-3 text-xs" onClick={handleAddImageUrl} disabled={!newImageUrl.trim()}>
                        <Plus className="mr-1 h-3.5 w-3.5" /> {t("preview.addUrl")}
                      </Button>
                    </div>

                    <div className="flex items-center gap-2">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={handleImageUpload}
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs gap-1.5"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <Upload className="h-3.5 w-3.5" /> {t("preview.uploadImage")}
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">{t("preview.referenceTemplate")}</Label>
                    <Input
                      className="h-8 text-xs"
                      placeholder={t("preview.templatePlaceholder")}
                      value={templateRef}
                      onChange={(e) => setTemplateRef(e.target.value)}
                      onBlur={() => saveSpec({ template_ref: templateRef })}
                    />
                  </div>

                  {imageRefs.length === 0 ? (
                    <div className="py-12 text-center rounded-lg border border-dashed text-xs text-muted-foreground">
                      <ImageIcon className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" />
                      {t("preview.noImages")}
                    </div>
                  ) : (
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      {imageRefs.map((img, idx) => (
                        <div key={idx} className="group relative rounded-lg border bg-card overflow-hidden shadow-xs">
                          <img
                            src={img}
                            alt={t("preview.mockupAlt", { number: idx + 1 })}
                            className="w-full h-48 object-contain bg-black/5 dark:bg-black/40"
                          />
                          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-2 flex items-center justify-between text-white text-[11px]">
                            <span className="truncate max-w-[180px]">{t("preview.imageNumber", { number: idx + 1 })}</span>
                            <div className="flex items-center gap-1">
                              <a
                                href={img}
                                target="_blank"
                                rel="noreferrer"
                                className="p-1 rounded hover:bg-white/20"
                                title={t("preview.openImage")}
                              >
                                <ExternalLink className="h-3.5 w-3.5" />
                              </a>
                              <button
                                type="button"
                                onClick={() => handleRemoveImage(idx)}
                                className="p-1 rounded hover:bg-destructive/80"
                                title={t("preview.removeImage")}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ================= ABA 2: REGRAS DE NEGÓCIO (.MD) ================= */}
        <TabsContent value="markdown" className="space-y-4">
          {/* Card de Localização do Arquivo e Atalhos para o Agente */}
          <Card className="border-primary/20 bg-primary/5">
            <CardContent className="p-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-3 text-xs">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-primary">{t("rules.fileLocation")}</span>
                  <code className="rounded bg-background/80 px-2 py-0.5 font-mono text-[11px] border">
                    {filePath}
                  </code>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {t("rules.fileDescription")}
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs gap-1.5 bg-background"
                  onClick={handleCopyPath}
                >
                  {copiedPath ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                  {copiedPath ? t("rules.pathCopied") : t("rules.copyPath")}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  className="h-8 text-xs gap-1.5"
                  onClick={handleCopyAgentPrompt}
                >
                  {copiedPrompt ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Sparkles className="h-3.5 w-3.5 text-primary" />}
                  {copiedPrompt ? t("rules.promptCopied") : t("rules.copyPrompt")}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Editor e Visualizador de Markdown */}
          <Card className="border-border/70">
            <CardHeader className="p-4 border-b flex flex-row items-center justify-between space-y-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-muted-foreground">{t("rules.view")}</span>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant={mdTab === "edit" ? "default" : "outline"}
                    className="h-7 text-xs"
                    onClick={() => setMdTab("edit")}
                  >
                    <Code className="mr-1 h-3.5 w-3.5" /> {t("rules.edit")}
                  </Button>
                  <Button
                    size="sm"
                    variant={mdTab === "preview" ? "default" : "outline"}
                    className="h-7 text-xs"
                    onClick={() => setMdTab("preview")}
                  >
                    <Eye className="mr-1 h-3.5 w-3.5" /> {t("rules.rendered")}
                  </Button>
                  <Button
                    size="sm"
                    variant={mdTab === "split" ? "default" : "outline"}
                    className="h-7 text-xs"
                    onClick={() => setMdTab("split")}
                  >
                    <Columns className="mr-1 h-3.5 w-3.5" /> {t("rules.sideBySide")}
                  </Button>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {businessRule.data?.updated_at && (
                  <span className="text-[10px] text-muted-foreground">
                    {t("rules.savedAt", { date: new Date(businessRule.data.updated_at).toLocaleString(i18n.language) })}
                  </span>
                )}
                <Button
                  size="sm"
                  disabled={saveBusinessRule.isPending}
                  onClick={() => saveBusinessRule.mutate({ scopeId, elementId, content: ruleContent })}
                  className="h-7 text-xs gap-1.5"
                >
                  {saveBusinessRule.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {t("rules.save")}
                </Button>
              </div>
            </CardHeader>

            <CardContent className="p-4">
              {businessRule.isLoading ? (
                <div className="py-12 text-center text-xs text-muted-foreground">
                  <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-primary" />
                  {t("rules.loading")}
                </div>
              ) : (
                <div className="space-y-4">
                  {mdTab === "edit" && (
                    <Textarea
                      rows={20}
                      className="resize-none font-mono text-xs leading-relaxed bg-muted/20"
                      placeholder={t("rules.editorPlaceholder")}
                      value={ruleContent}
                      onChange={(e) => setRuleContent(e.target.value)}
                    />
                  )}

                  {mdTab === "preview" && (
                    <div className="rounded-md border p-4 min-h-[400px] bg-card text-xs overflow-y-auto">
                      {ruleContent.trim() ? (
                        <Markdown content={ruleContent} />
                      ) : (
                        <p className="text-muted-foreground italic">{t("rules.noContent")}</p>
                      )}
                    </div>
                  )}

                  {mdTab === "split" && (
                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">{t("rules.markdownEditor")}</Label>
                        <Textarea
                          rows={20}
                          className="resize-none font-mono text-xs leading-relaxed bg-muted/20"
                          placeholder={t("rules.shortPlaceholder")}
                          value={ruleContent}
                          onChange={(e) => setRuleContent(e.target.value)}
                        />
                      </div>
                      <div className="space-y-1.5 flex flex-col">
                        <Label className="text-xs text-muted-foreground">{t("rules.renderedPreview")}</Label>
                        <div className="flex-1 rounded-md border p-4 bg-card text-xs overflow-y-auto max-h-[440px]">
                          {ruleContent.trim() ? (
                            <Markdown content={ruleContent} />
                          ) : (
                            <p className="text-muted-foreground italic">{t("rules.nothingToRender")}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ================= ABA 3: ATRIBUTOS & DADOS ================= */}
        <TabsContent value="attributes" className="space-y-4">
          <Card className="border-border/70">
            <CardHeader className="p-4 border-b flex flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle className="text-sm font-semibold">{t("attributes.title")}</CardTitle>
                <CardDescription className="text-xs">
                  {t("attributes.description")}
                </CardDescription>
              </div>
              <Button size="sm" onClick={addAttribute} className="h-7 text-xs gap-1">
                <Plus className="h-3.5 w-3.5" /> {t("attributes.add")}
              </Button>
            </CardHeader>
            <CardContent className="p-4 space-y-3">
              {attributes.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                  {t("attributes.empty")}
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-[1fr_130px_90px_1.5fr_36px] gap-2 text-[11px] font-semibold text-muted-foreground px-1">
                    <span>{t("attributes.fieldName")}</span>
                    <span>{t("attributes.type")}</span>
                    <span>{t("attributes.required")}</span>
                    <span>{t("attributes.descriptionRule")}</span>
                    <span></span>
                  </div>
                  {attributes.map((attr, i) => (
                    <div key={i} className="grid grid-cols-[1fr_130px_90px_1.5fr_36px] gap-2 items-center">
                      <Input
                        className="h-8 text-xs font-medium"
                        placeholder={t("attributes.namePlaceholder")}
                        value={attr.name}
                        onChange={(e) => updateAttribute(i, { name: e.target.value })}
                      />
                      <Select
                        className="h-8 text-xs"
                        value={attr.type}
                        onChange={(e) => updateAttribute(i, { type: e.target.value as ScreenAttributeType })}
                      >
                        {ATTRIBUTE_TYPES.map((attributeType) => (
                          <option key={attributeType} value={attributeType}>
                            {t(`attributes.types.${attributeType}`)}
                          </option>
                        ))}
                      </Select>
                      <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                        <input
                          type="checkbox"
                          className="rounded border-input text-primary focus:ring-primary h-3.5 w-3.5"
                          checked={attr.required}
                          onChange={(e) => updateAttribute(i, { required: e.target.checked })}
                        />
                        <span>{t("attributes.yes")}</span>
                      </label>
                      <Input
                        className="h-8 text-xs"
                        placeholder={t("attributes.purposePlaceholder")}
                        value={attr.description ?? ""}
                        onChange={(e) => updateAttribute(i, { description: e.target.value })}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive"
                        onClick={() => removeAttribute(i)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
