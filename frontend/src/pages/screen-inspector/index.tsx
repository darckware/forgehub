import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Layout, Loader2, Plus, Send, Trash2, Wand2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAgents } from "@/hooks/useAgent";
import { useCreateDemand } from "@/hooks/useDemands";
import { useProjects } from "@/hooks/useProject";
import { useProjectScopes } from "@/hooks/useSystemScope";
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

export default function ScreenInspectorPage() {
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const scopes = useProjectScopes(projectId);
  const [scopeId, setScopeId] = useState("");
  useEffect(() => setScopeId(scopes.data?.[0]?.id || ""), [scopes.data]);

  const screens = useScreens(scopeId);
  const createScreen = useCreateScreen();
  const updateScreen = useUpdateScreen();
  const removeScreen = useRemoveScreen();
  const deriveDatabase = useDeriveDatabase();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    if (!screens.data?.some((s) => s.element.id === selectedId)) {
      setSelectedId(screens.data?.[0]?.element.id ?? null);
    }
  }, [screens.data, selectedId]);
  const selected = screens.data?.find((s) => s.element.id === selectedId) ?? null;

  const [newScreenName, setNewScreenName] = useState("");
  const [creating, setCreating] = useState(false);

  const submitNewScreen = async () => {
    const name = newScreenName.trim();
    if (!name || !scopeId) return;
    setCreating(true);
    try {
      const created = await createScreen.mutateAsync({ scopeId, name, spec: { attributes: [] } });
      setNewScreenName("");
      setSelectedId(created.element.id);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><Layout className="h-6 w-6" />Telas & Regras de Negócio</h1>
          <p className="text-sm text-muted-foreground">
            Cadastro real das telas do sistema: atributos, protótipo conceitual e regra de negócio por tela --
            insumo para o agente responsável pelo frontend, não o código final.
          </p>
        </div>
        <Button
          variant="outline"
          disabled={!scopeId || deriveDatabase.isPending}
          onClick={() => deriveDatabase.mutate(scopeId)}
        >
          {deriveDatabase.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Wand2 className="mr-2 h-4 w-4" />}
          Derivar Banco de Dados
        </Button>
      </div>

      <Card>
        <CardContent className="grid gap-4 pt-6 md:grid-cols-2">
          <div>
            <Label>Projeto</Label>
            <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Selecione um projeto...</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
          </div>
          <div>
            <Label>Escopo</Label>
            <Select value={scopeId} onChange={(e) => setScopeId(e.target.value)} disabled={!projectId}>
              <option value="">Selecione um escopo...</option>
              {scopes.data?.map((s) => <option key={s.id} value={s.id}>Revisão {s.revision} · {s.status}</option>)}
            </Select>
          </div>
        </CardContent>
      </Card>

      {deriveDatabase.isSuccess && (
        <p className="text-sm text-muted-foreground">
          Modelagem derivada: {deriveDatabase.data.tables_created} tabela(s) criada(s), {deriveDatabase.data.tables_updated} atualizada(s), {deriveDatabase.data.fields_written} campo(s).{" "}
          <Link to="/concept-erd" className="text-primary hover:underline">Ver diagrama →</Link>
        </p>
      )}

      {!scopeId ? (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">Selecione um projeto e um escopo para gerenciar as telas.</CardContent></Card>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Telas</CardTitle>
              <CardDescription>{screens.data?.length ?? 0} cadastrada(s)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-1">
                <Input
                  className="h-8 text-xs" placeholder="Nome da nova tela"
                  value={newScreenName} onChange={(e) => setNewScreenName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submitNewScreen(); } }}
                />
                <Button size="sm" className="h-8 px-2" disabled={!newScreenName.trim() || creating} onClick={submitNewScreen}>
                  <Plus className="h-3.5 w-3.5" />
                </Button>
              </div>
              {screens.isLoading && <p className="text-xs text-muted-foreground">Carregando...</p>}
              {screens.data?.length === 0 && <p className="text-xs text-muted-foreground">Nenhuma tela cadastrada ainda.</p>}
              <div className="space-y-1.5">
                {screens.data?.map((s) => (
                  <button
                    key={s.element.id}
                    type="button"
                    onClick={() => setSelectedId(s.element.id)}
                    className={`w-full rounded-lg border p-2.5 text-left text-sm transition-colors ${selectedId === s.element.id ? "border-primary bg-primary/5" : "hover:bg-accent/40"}`}
                  >
                    <p className="font-medium">{s.element.name}</p>
                    <p className="text-xs text-muted-foreground">{s.revision.spec_snapshot.attributes?.length ?? 0} atributo(s)</p>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {selected ? (
            <ScreenEditor
              key={selected.element.id}
              scopeId={scopeId}
              projectId={projectId}
              screen={selected}
              onUpdate={updateScreen}
              onRemove={() => {
                removeScreen.mutate({ scopeId, elementId: selected.element.id });
                setSelectedId(null);
              }}
            />
          ) : (
            <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">Selecione ou crie uma tela para editar.</CardContent></Card>
          )}
        </div>
      )}
    </div>
  );
}

function ScreenEditor({
  scopeId, projectId, screen, onUpdate, onRemove,
}: {
  scopeId: string; projectId: string; screen: Screen;
  onUpdate: ReturnType<typeof useUpdateScreen>; onRemove: () => void;
}) {
  const elementId = screen.element.id;
  const [attributes, setAttributes] = useState<ScreenAttribute[]>(screen.revision.spec_snapshot.attributes ?? []);
  const [prototypeMode, setPrototypeMode] = useState<"html" | "template">(
    screen.revision.spec_snapshot.template_ref ? "template" : "html"
  );
  const [prototypeHtml, setPrototypeHtml] = useState(screen.revision.spec_snapshot.prototype_html ?? "");
  const [cssFramework, setCssFramework] = useState(screen.revision.spec_snapshot.css_framework ?? "plain");
  const [templateRef, setTemplateRef] = useState(screen.revision.spec_snapshot.template_ref ?? "");
  const [imageRefs, setImageRefs] = useState<string[]>(screen.revision.spec_snapshot.image_refs ?? []);
  const [newImageRef, setNewImageRef] = useState("");

  useEffect(() => {
    setAttributes(screen.revision.spec_snapshot.attributes ?? []);
    setPrototypeMode(screen.revision.spec_snapshot.template_ref ? "template" : "html");
    setPrototypeHtml(screen.revision.spec_snapshot.prototype_html ?? "");
    setCssFramework(screen.revision.spec_snapshot.css_framework ?? "plain");
    setTemplateRef(screen.revision.spec_snapshot.template_ref ?? "");
    setImageRefs(screen.revision.spec_snapshot.image_refs ?? []);
  }, [screen]);

  // Direct edits (attributes, prototype) save with no agent call -- Marcelo:
  // "coisas simples pode ajudar na economia de token".
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

  const businessRule = useScreenBusinessRule(scopeId, elementId);
  const saveBusinessRule = useSaveScreenBusinessRule();
  const [ruleContent, setRuleContent] = useState("");
  useEffect(() => { if (businessRule.data) setRuleContent(businessRule.data.content); }, [businessRule.data]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <div>
            <Input
              className="h-8 max-w-sm text-base font-semibold"
              value={screen.element.name}
              onChange={(e) => onUpdate.mutate({ scopeId, elementId, name: e.target.value })}
            />
            <CardDescription className="mt-1">{screen.element.stable_key}</CardDescription>
          </div>
          <Button variant="ghost" size="icon" onClick={onRemove} title="Remover do escopo">
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Atributos</CardTitle>
          <CardDescription>Campos que a tela expõe -- usados para derivar o banco de dados.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {attributes.map((attr, i) => (
            <div key={i} className="grid grid-cols-[1fr_120px_80px_1fr_32px] gap-2 items-center">
              <Input className="h-8 text-xs" placeholder="nome" value={attr.name} onChange={(e) => updateAttribute(i, { name: e.target.value })} />
              <Select className="h-8 text-xs" value={attr.type} onChange={(e) => updateAttribute(i, { type: e.target.value as ScreenAttributeType })}>
                {ATTRIBUTE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
              <label className="flex items-center gap-1 text-xs">
                <input type="checkbox" checked={attr.required} onChange={(e) => updateAttribute(i, { required: e.target.checked })} />
                obrigatório
              </label>
              <Input className="h-8 text-xs" placeholder="descrição" value={attr.description ?? ""} onChange={(e) => updateAttribute(i, { description: e.target.value })} />
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removeAttribute(i)}>
                <Trash2 className="h-3.5 w-3.5 text-destructive" />
              </Button>
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={addAttribute}><Plus className="mr-1.5 h-3.5 w-3.5" />Adicionar atributo</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Protótipo (conceitual)</CardTitle>
          <CardDescription>Ajuda a alinhar estrutura/intenção -- não é o código final da implementação.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Button size="sm" variant={prototypeMode === "html" ? "default" : "outline"} onClick={() => setPrototypeMode("html")}>HTML livre</Button>
            <Button size="sm" variant={prototypeMode === "template" ? "default" : "outline"} onClick={() => setPrototypeMode("template")}>Template + Imagens</Button>
          </div>
          {prototypeMode === "html" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Framework CSS</Label>
                <Input value={cssFramework} onChange={(e) => setCssFramework(e.target.value)} placeholder="plain, tailwind, bootstrap..." />
                <Label>HTML</Label>
                <Textarea
                  rows={12} className="resize-none font-mono text-xs"
                  value={prototypeHtml}
                  onChange={(e) => setPrototypeHtml(e.target.value)}
                  onBlur={() => saveSpec({ prototype_html: prototypeHtml, css_framework: cssFramework, template_ref: null })}
                />
              </div>
              <div className="space-y-2">
                <Label>Preview</Label>
                <iframe title="preview" sandbox="" srcDoc={prototypeHtml} className="h-[19rem] w-full rounded-md border bg-white" />
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <Label>Template de referência</Label>
              <Input
                value={templateRef} onChange={(e) => setTemplateRef(e.target.value)}
                onBlur={() => saveSpec({ template_ref: templateRef, prototype_html: null })}
                placeholder="nome/caminho do template"
              />
              <Label>Imagens de referência</Label>
              <div className="flex gap-1">
                <Input className="h-8 text-xs" value={newImageRef} onChange={(e) => setNewImageRef(e.target.value)} placeholder="URL ou caminho da imagem" />
                <Button size="sm" className="h-8" onClick={() => {
                  if (!newImageRef.trim()) return;
                  const next = [...imageRefs, newImageRef.trim()];
                  setImageRefs(next);
                  setNewImageRef("");
                  saveSpec({ image_refs: next });
                }}>Adicionar</Button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {imageRefs.map((ref, i) => (
                  <Badge key={i} variant="outline" className="gap-1">
                    {ref}
                    <button type="button" onClick={() => {
                      const next = imageRefs.filter((_, idx) => idx !== i);
                      setImageRefs(next);
                      saveSpec({ image_refs: next });
                    }}>×</button>
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Regra de Negócio</CardTitle>
          <CardDescription>Documento .md associado a esta tela.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {businessRule.isLoading ? (
            <p className="text-xs text-muted-foreground">Carregando...</p>
          ) : (
            <>
              <Textarea rows={8} className="resize-none font-mono text-xs" value={ruleContent} onChange={(e) => setRuleContent(e.target.value)} />
              <Button size="sm" disabled={saveBusinessRule.isPending} onClick={() => saveBusinessRule.mutate({ scopeId, elementId, content: ruleContent })}>
                {saveBusinessRule.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                Salvar regra
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <RequestAgentPanel projectId={projectId} screenName={screen.element.name} attributes={attributes} />
    </div>
  );
}

function RequestAgentPanel({ projectId, screenName, attributes }: { projectId: string; screenName: string; attributes: ScreenAttribute[] }) {
  const agents = useAgents();
  const createDemand = useCreateDemand();
  const [open, setOpen] = useState(false);
  const [fromAgentId, setFromAgentId] = useState("");
  const [targetAgentId, setTargetAgentId] = useState("");
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);

  const attributesList = useMemo(
    () => attributes.map((a) => `- ${a.name} (${a.type}${a.required ? ", obrigatório" : ""})`).join("\n"),
    [attributes]
  );

  const submit = async () => {
    const fromAgent = agents.data?.find((a) => a.id === fromAgentId);
    if (!fromAgent) return;
    await createDemand.mutateAsync({
      from_agent: fromAgent.name,
      fromAgentId,
      targetAgentId: targetAgentId || undefined,
      projectId,
      subject: `Tela: ${screenName}`,
      body: `Construir/ajustar o frontend da tela "${screenName}".\n\nAtributos:\n${attributesList || "(nenhum atributo definido ainda)"}\n\n${note}`,
      originType: "task",
    });
    setSent(true);
    setOpen(false);
    setNote("");
  };

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Send className="mr-2 h-4 w-4" />Solicitar ao agente
      </Button>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Solicitar ao agente</CardTitle>
        <CardDescription>Envia como Mensagem (Tipo=Task) -- controlado pelo canal de Mensagens já existente.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <Label>De (agente solicitante)</Label>
            <Select value={fromAgentId} onChange={(e) => setFromAgentId(e.target.value)}>
              <option value="">Selecione...</option>
              {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
          </div>
          <div>
            <Label>Para (agente responsável pelo frontend)</Label>
            <Select value={targetAgentId} onChange={(e) => setTargetAgentId(e.target.value)}>
              <option value="">Selecione...</option>
              {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
          </div>
        </div>
        <div>
          <Label>Instruções adicionais</Label>
          <Textarea className="resize-none" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="O que deve mudar/ser construído..." />
        </div>
        <div className="flex gap-2">
          <Button disabled={!fromAgentId || createDemand.isPending} onClick={submit}>
            {createDemand.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Enviar
          </Button>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
        </div>
      </CardContent>
      {sent && <CardContent className="pt-0"><p className="text-xs text-muted-foreground">Enviado -- confira em <Link to="/demands" className="text-primary hover:underline">Mensagens</Link>.</p></CardContent>}
    </Card>
  );
}
