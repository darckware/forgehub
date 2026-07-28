import { useState } from "react";
import { Layout, Image as ImageIcon, Sparkles, CheckCircle2, ShieldAlert, Sliders, Layers } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

interface ScreenMockup {
  id: string;
  title: string;
  description: string;
  assetPath: string;
  state: "empty" | "loading" | "success" | "error";
  components: string[];
  rulesCount: number;
}

const MOCK_SCREENS: ScreenMockup[] = [
  {
    id: "screen_dashboard",
    title: "Dashboard Financeiro",
    description: "Visão geral de métricas, cards de saldo e gráficos de desempenho.",
    assetPath: "/assets/dashboard_template.png",
    state: "success",
    components: ["ODCard", "ODStatWidget", "ODLineChart", "ODButton"],
    rulesCount: 3,
  },
  {
    id: "screen_login",
    title: "Tela de Login & Autenticação",
    description: "Formulário de acesso com validação OAuth e suporte a Multi-fator (MFA).",
    assetPath: "/assets/login_mockup.png",
    state: "success",
    components: ["ODInput", "ODButton", "ODCard", "ODAlert"],
    rulesCount: 2,
  },
  {
    id: "screen_users",
    title: "Gestão de Usuários & Perfis",
    description: "Tabela paginada com ações de edição, exclusão e atribuição de papéis RBAC.",
    assetPath: "/assets/users_template.png",
    state: "empty",
    components: ["ODDataTable", "ODBadge", "ODModal", "ODButton"],
    rulesCount: 4,
  },
];

export default function ScreenInspectorPage() {
  const [selectedScreen, setSelectedScreen] = useState<ScreenMockup>(MOCK_SCREENS[0]);
  const [activeState, setActiveState] = useState<"success" | "empty" | "loading" | "error">("success");
  const [contextRuleText, setContextRuleText] = useState("");
  const [savedRules, setSavedRules] = useState<string[]>([
    "Atualizar métricas de vendas a cada 30 segundos via WebSocket.",
    "Restringir visualização de dados financeiros apenas para perfil Admin/Analista.",
    "Exibir badge 'Atenção' em vermelho caso o saldo seja menor que zero.",
  ]);

  const handleAddRule = () => {
    if (!contextRuleText.trim()) return;
    setSavedRules([...savedRules, contextRuleText.trim()]);
    setContextRuleText("");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Layout className="h-6 w-6 text-primary" />
            Inspeção de Telas & UI Studio
          </h1>
          <p className="text-sm text-muted-foreground">
            Visualização dos mockups (ComfyUI), componentes do Open Design e injeção de regras de contexto por tela.
          </p>
        </div>
        <Badge variant="outline" className="flex items-center gap-1 border-primary/30 text-primary">
          <Sparkles className="h-3.5 w-3.5" />
          Fase 2: Inspeção Multimodal
        </Badge>
      </div>

      <div className="grid gap-6 md:grid-cols-[280px_1fr]">
        {/* Sidebar Lista de Telas */}
        <Card className="h-fit">
          <CardHeader className="p-4">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Layers className="h-4 w-4" />
              Telas Especificadas ({MOCK_SCREENS.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="p-2 space-y-1">
            {MOCK_SCREENS.map((screen) => (
              <button
                key={screen.id}
                type="button"
                onClick={() => setSelectedScreen(screen)}
                className={`flex w-full flex-col items-start gap-1 rounded-md p-3 text-left transition-colors ${
                  selectedScreen.id === screen.id ? "bg-primary/10 border border-primary/30" : "hover:bg-accent"
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="text-xs font-semibold">{screen.title}</span>
                  <Badge variant="secondary" className="text-[10px]">
                    {screen.rulesCount} regras
                  </Badge>
                </div>
                <span className="text-[11px] text-muted-foreground line-clamp-1">{screen.description}</span>
              </button>
            ))}
          </CardContent>
        </Card>

        {/* Visualizador de Tela Principal */}
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
              <div>
                <CardTitle className="text-lg font-bold">{selectedScreen.title}</CardTitle>
                <CardDescription className="text-xs">{selectedScreen.description}</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-muted-foreground">Estado:</span>
                <Tabs value={activeState} onValueChange={(v) => setActiveState(v as any)}>
                  <TabsList className="h-8">
                    <TabsTrigger value="success" className="text-xs px-2 h-6">Normal</TabsTrigger>
                    <TabsTrigger value="empty" className="text-xs px-2 h-6">Vazio</TabsTrigger>
                    <TabsTrigger value="loading" className="text-xs px-2 h-6">Carregando</TabsTrigger>
                    <TabsTrigger value="error" className="text-xs px-2 h-6">Erro</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Moldura de Inspeção da Imagem / Mockup */}
              <div className="relative aspect-video w-full overflow-hidden rounded-lg border bg-muted/30 flex items-center justify-center">
                {activeState === "loading" && (
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    <span className="text-xs">Simulando estado de carregamento da tela...</span>
                  </div>
                )}

                {activeState === "error" && (
                  <div className="flex flex-col items-center gap-2 text-destructive">
                    <ShieldAlert className="h-10 w-10" />
                    <span className="text-xs font-semibold">Simulação de Estado de Erro / Falha de API</span>
                  </div>
                )}

                {activeState === "empty" && (
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <ImageIcon className="h-10 w-10 text-muted-foreground/50" />
                    <span className="text-xs">Simulação de Estado Vazio (Sem registros cadastrados)</span>
                  </div>
                )}

                {activeState === "success" && (
                  <div className="flex flex-col items-center justify-center p-8 text-center">
                    <ImageIcon className="h-12 w-12 text-primary/40 mb-2" />
                    <p className="text-xs font-semibold text-foreground">Visualização do Template de Tela (ComfyUI)</p>
                    <p className="text-[11px] text-muted-foreground max-w-sm mt-1">
                      Mockup renderizado a partir do arquivo <code className="text-primary">{selectedScreen.assetPath}</code>
                    </p>
                  </div>
                )}
              </div>

              {/* Componentes Open Design Utilizados */}
              <div>
                <Label className="text-xs font-semibold text-muted-foreground uppercase">
                  Componentes Open Design Mapeados:
                </Label>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {selectedScreen.components.map((comp) => (
                    <Badge key={comp} variant="outline" className="text-xs bg-accent/50 font-mono">
                      {comp}
                    </Badge>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Painel de Injeção de Regras de Contexto por Tela */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Sliders className="h-4 w-4 text-primary" />
                Regras de Negócio e Contexto Injetadas para esta Tela
              </CardTitle>
              <CardDescription className="text-xs">
                As regras aqui adicionadas orientarão a IA no momento de gerar as tarefas de Backend e Frontend.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                {savedRules.map((rule, idx) => (
                  <div key={idx} className="flex items-start gap-2 rounded-md border p-2.5 bg-card text-xs">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                    <span>{rule}</span>
                  </div>
                ))}
              </div>

              <div className="space-y-2 pt-2">
                <Label className="text-xs">Adicionar Nova Regra de Contexto:</Label>
                <Textarea
                  rows={2}
                  className="text-xs"
                  placeholder="Ex: O botão de exportação só deve ficar ativo quando houver ao menos 1 item selecionado na tabela."
                  value={contextRuleText}
                  onChange={(e) => setContextRuleText(e.target.value)}
                />
                <Button size="sm" className="text-xs" onClick={handleAddRule} disabled={!contextRuleText.trim()}>
                  Injetar Regra de Contexto
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
