import { useState } from "react";
import { CheckCircle2, Sparkles, Package, GitBranch, ShieldCheck, AlertCircle, ArrowRight } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface CompletedProjectItem {
  id: string;
  name: string;
  applicationName: string;
  type: "nova_feature" | "manutencao";
  plansCount: number;
  tasksCount: number;
  completedAt: string;
}

const COMPLETED_PROJECTS_MOCK: CompletedProjectItem[] = [
  {
    id: "proj_01",
    name: "Redesign da Tela de Login & Auth OAuth",
    applicationName: "Frontend Web App",
    type: "nova_feature",
    plansCount: 2,
    tasksCount: 8,
    completedAt: "2026-07-26",
  },
  {
    id: "proj_02",
    name: "API de Métricas Financeiras & WebSockets",
    applicationName: "Backend REST API",
    type: "nova_feature",
    plansCount: 1,
    tasksCount: 5,
    completedAt: "2026-07-26",
  },
  {
    id: "proj_03",
    name: "Ajuste na Query de Filtragem por Filial",
    applicationName: "Backend REST API",
    type: "manutencao",
    plansCount: 1,
    tasksCount: 2,
    completedAt: "2026-07-27",
  },
];

export default function VersionClosurePage() {
  const [versionTag, setVersionTag] = useState("v2.1.0");
  const [releaseNotes, setReleaseNotes] = useState(
    "Lançamento da versão v2.1.0 incluindo novo fluxo de autenticação OAuth, API de métricas financeiras em tempo real e ajustes de performance nas consultas."
  );
  const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>(["proj_01", "proj_02", "proj_03"]);
  const [isPublishing, setIsPublishing] = useState(false);
  const [isPublishedSuccess, setIsPublishedSuccess] = useState(false);

  const toggleProject = (id: string) => {
    setSelectedProjectIds((prev) =>
      prev.includes(id) ? prev.filter((pId) => pId !== id) : [...prev, id]
    );
  };

  const handleCloseVersion = () => {
    if (!versionTag.trim() || selectedProjectIds.length === 0) return;
    setIsPublishing(true);
    setTimeout(() => {
      setIsPublishing(false);
      setIsPublishedSuccess(true);
    }, 1200);
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <CheckCircle2 className="h-6 w-6 text-primary" />
            Fechamento de Versão (Release Closure)
          </h1>
          <p className="text-sm text-muted-foreground">
            Consolidação de múltiplos projetos concluídos em uma Versão Publicável com encerramento automático em cascata.
          </p>
        </div>
        <Badge variant="outline" className="flex items-center gap-1 border-primary/30 text-primary">
          <Sparkles className="h-3.5 w-3.5" />
          Fase 5: Publicação & Release
        </Badge>
      </div>

      {isPublishedSuccess ? (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardContent className="flex flex-col items-center justify-center p-8 text-center space-y-3">
            <CheckCircle2 className="h-12 w-12 text-emerald-500" />
            <h2 className="text-xl font-bold text-emerald-600">Versão {versionTag} Publicada com Sucesso!</h2>
            <p className="text-xs text-muted-foreground max-w-md">
              Todos os <strong>{selectedProjectIds.length} projetos vinculados</strong> e seus planejamentos foram encerrados em cascata (status <code className="text-emerald-600">completed</code>) e a versão da aplicação foi alterada para <code className="text-emerald-600">published</code>.
            </p>
            <Button size="sm" onClick={() => setIsPublishedSuccess(false)} className="mt-2 text-xs">
              Realizar Novo Fechamento de Versão
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-[1fr_360px]">
          {/* Seleção dos Projetos Concluídos */}
          <div className="space-y-6">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Package className="h-4 w-4 text-primary" />
                  Projetos Elegíveis para esta Versão ({COMPLETED_PROJECTS_MOCK.length})
                </CardTitle>
                <CardDescription className="text-xs">
                  Selecione um ou mais projetos finalizados (de diferentes Aplicações) para vincular a esta Release.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {COMPLETED_PROJECTS_MOCK.map((proj) => (
                  <div
                    key={proj.id}
                    onClick={() => toggleProject(proj.id)}
                    className={`flex items-start gap-3 rounded-lg border p-3.5 cursor-pointer transition-colors ${
                      selectedProjectIds.includes(proj.id)
                        ? "border-primary bg-primary/5"
                        : "hover:bg-accent/50"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedProjectIds.includes(proj.id)}
                      onChange={() => toggleProject(proj.id)}
                      className="mt-1 h-4 w-4 rounded border-primary text-primary focus:ring-primary"
                    />
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold">{proj.name}</span>
                        <Badge variant="outline" className="text-[10px]">
                          {proj.type === "nova_feature" ? "Nova Feature" : "Manutenção"}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                        <span>Aplicação: <strong>{proj.applicationName}</strong></span>
                        <span>•</span>
                        <span>{proj.plansCount} Planejamentos</span>
                        <span>•</span>
                        <span>{proj.tasksCount} Tarefas</span>
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Release Notes */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <GitBranch className="h-4 w-4 text-primary" />
                  Notas de Lançamento (Release Notes)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Textarea
                  rows={4}
                  className="text-xs font-mono"
                  value={releaseNotes}
                  onChange={(e) => setReleaseNotes(e.target.value)}
                />
              </CardContent>
            </Card>
          </div>

          {/* Painel Lateral de Confirmação & Encerramento Cascata */}
          <div className="space-y-6">
            <Card className="border-primary/30">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-primary" />
                  Resumo da Publicação
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold">Tag de Versão:</Label>
                  <Input
                    className="h-8 text-xs font-mono font-bold"
                    value={versionTag}
                    onChange={(e) => setVersionTag(e.target.value)}
                  />
                </div>

                <div className="rounded-md bg-muted p-3 space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Projetos Selecionados:</span>
                    <span className="font-bold">{selectedProjectIds.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Status Pós-Fechamento:</span>
                    <Badge variant="secondary" className="text-[10px] text-emerald-600 bg-emerald-500/10">
                      Completed (Cascata)
                    </Badge>
                  </div>
                </div>

                <div className="flex items-start gap-2 text-[11px] text-muted-foreground rounded-md border border-amber-500/30 bg-amber-500/5 p-2.5">
                  <AlertCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                  <span>
                    Ao confirmar, o ForgeHub encerrará automaticamente todos os planejamentos associados e publicará a versão.
                  </span>
                </div>

                <Button
                  className="w-full text-xs flex items-center justify-center gap-2"
                  onClick={handleCloseVersion}
                  disabled={isPublishing || selectedProjectIds.length === 0}
                >
                  {isPublishing ? "Encerrando e Publicando..." : "Confirmar e Publicar Versão"}
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
