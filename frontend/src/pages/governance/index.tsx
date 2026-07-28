import { useState } from "react";
import { ShieldCheck, Sparkles, CheckCircle2, XCircle, Clock, AlertTriangle, UserCheck, Bot, KeyRound, Lock } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

interface ApprovalItem {
  id: string;
  type: "revisao_conceito" | "mudanca_schema" | "delegacao_agente" | "liberacao_wave";
  title: string;
  requestedBy: string;
  requestedByType: "user" | "agent";
  date: string;
  status: "pending" | "approved" | "rejected";
  details: string;
  riskLevel: "low" | "medium" | "high";
  isSelfRequested?: boolean;
}

const MOCK_APPROVALS: ApprovalItem[] = [
  {
    id: "app_01",
    type: "revisao_conceito",
    title: "Aprovação de Conceito & Documentação PRD (Frontend OAuth)",
    requestedBy: "Marcelo (Product Owner)",
    requestedByType: "user",
    date: "2026-07-27 02:15",
    status: "pending",
    details: "Revisão v1 contendo escopo de autenticação social e design system.",
    riskLevel: "medium",
    isSelfRequested: true,
  },
  {
    id: "app_02",
    type: "mudanca_schema",
    title: "Alembic Migration: Adição de Tabela `user_tokens`",
    requestedBy: "#Hephaestus (DB Agent)",
    requestedByType: "agent",
    date: "2026-07-27 01:40",
    status: "pending",
    details: "SQL Migration de schema gerada após aprovação no Diagrama ERD.",
    riskLevel: "high",
  },
  {
    id: "app_03",
    type: "liberacao_wave",
    title: "Autorização de Liberação do Lote 2 (Execution Wave 2)",
    requestedBy: "#Athos (Supervisor Agent)",
    requestedByType: "agent",
    date: "2026-07-26 22:10",
    status: "approved",
    details: "Lote de 6 tarefas de frontend liberado para execução autônoma.",
    riskLevel: "low",
  },
];

export default function GovernancePage() {
  const [approvals, setApprovals] = useState<ApprovalItem[]>(MOCK_APPROVALS);
  const [athosDelegated, setAthosDelegated] = useState(true);
  const [activeTab, setActiveTab] = useState("pending");

  const handleDecision = (id: string, decision: "approved" | "rejected") => {
    setApprovals((prev) =>
      prev.map((item) => (item.id === id ? { ...item, status: decision } : item))
    );
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <ShieldCheck className="h-6 w-6 text-primary" />
            Governança & Aprovações AI-SDLC
          </h1>
          <p className="text-sm text-muted-foreground">
            Validação de Políticas, Aprovação de Conceito e Delegação de Autoridade para o Agente Supervisor #Athos.
          </p>
        </div>
        <Badge variant="outline" className="flex items-center gap-1 border-primary/30 text-primary">
          <Sparkles className="h-3.5 w-3.5" />
          Módulo de Governança
        </Badge>
      </div>

      <div className="grid gap-6 md:grid-cols-[1fr_360px]">
        {/* Painel Principal de Pendências e Aprovações */}
        <div className="space-y-6">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="pending">
                Pendentes de Decisão ({approvals.filter((a) => a.status === "pending").length})
              </TabsTrigger>
              <TabsTrigger value="history">
                Histórico & Trilha de Auditoria
              </TabsTrigger>
            </TabsList>

            <TabsContent value="pending" className="mt-4 space-y-4">
              {approvals.filter((a) => a.status === "pending").length === 0 ? (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground space-y-2">
                    <CheckCircle2 className="h-10 w-10 text-emerald-500/60" />
                    <p className="font-semibold text-sm">Nenhuma solicitação pendente no momento</p>
                    <p className="text-xs">Todas as revisões de conceitos e migrações foram avaliadas.</p>
                  </CardContent>
                </Card>
              ) : (
                approvals
                  .filter((a) => a.status === "pending")
                  .map((item) => (
                    <Card key={item.id} className="border-l-4 border-l-amber-500">
                      <CardHeader className="pb-2">
                        <div className="flex items-start justify-between">
                          <div className="space-y-1">
                            <CardTitle className="text-sm font-bold flex items-center gap-2">
                              {item.title}
                            </CardTitle>
                            <CardDescription className="text-xs flex items-center gap-2">
                              {item.requestedByType === "user" ? (
                                <UserCheck className="h-3.5 w-3.5 text-primary" />
                              ) : (
                                <Bot className="h-3.5 w-3.5 text-sky-500" />
                              )}
                              <span>Solicitado por: <strong>{item.requestedBy}</strong></span>
                              <span>•</span>
                              <span>{item.date}</span>
                            </CardDescription>
                          </div>
                          <Badge
                            variant="outline"
                            className={`text-[10px] ${
                              item.riskLevel === "high"
                                ? "border-red-500/50 bg-red-500/10 text-red-600"
                                : item.riskLevel === "medium"
                                ? "border-amber-500/50 bg-amber-500/10 text-amber-600"
                                : "border-emerald-500/50 bg-emerald-500/10 text-emerald-600"
                            }`}
                          >
                            Risco: {item.riskLevel.toUpperCase()}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <p className="text-xs text-muted-foreground bg-muted/40 p-2.5 rounded-md font-mono">
                          {item.details}
                        </p>

                        {/* Guardrail: Separation of Duties */}
                        {item.isSelfRequested && (
                          <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-400">
                            <AlertTriangle className="h-4 w-4 shrink-0" />
                            <span>
                              <strong>Separação de Deveres (Separation of Duties):</strong> Você criou esta solicitação e não pode aprová-la diretamente.
                            </span>
                          </div>
                        )}

                        <div className="flex justify-end gap-2 pt-1">
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-xs text-destructive border-destructive/30 hover:bg-destructive/10"
                            onClick={() => handleDecision(item.id, "rejected")}
                          >
                            <XCircle className="mr-1.5 h-3.5 w-3.5" />
                            Rejeitar / Solicitar Ajustes
                          </Button>
                          <Button
                            size="sm"
                            disabled={item.isSelfRequested}
                            className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
                            onClick={() => handleDecision(item.id, "approved")}
                          >
                            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                            Aprovar & Liberar
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))
              )}
            </TabsContent>

            <TabsContent value="history" className="mt-4 space-y-3">
              {approvals
                .filter((a) => a.status !== "pending")
                .map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between rounded-lg border p-3 text-xs bg-card"
                  >
                    <div className="space-y-1">
                      <p className="font-bold">{item.title}</p>
                      <p className="text-[11px] text-muted-foreground">{item.details}</p>
                    </div>
                    <Badge
                      className={
                        item.status === "approved"
                          ? "bg-emerald-500 text-white"
                          : "bg-red-500 text-white"
                      }
                    >
                      {item.status === "approved" ? "Aprovado" : "Rejeitado"}
                    </Badge>
                  </div>
                ))}
            </TabsContent>
          </Tabs>
        </div>

        {/* Painel Lateral de Delegação de Autoridade para o Agente Athos */}
        <div className="space-y-6">
          <Card className="border-primary/30">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-primary" />
                Mandato do Agente Supervisor #Athos
              </CardTitle>
              <CardDescription className="text-xs">
                Delegação de autoridade por 24h para execução e liberação autônoma de lotes.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border p-3 bg-muted/30 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold flex items-center gap-1.5">
                    <Bot className="h-4 w-4 text-sky-500" />
                    #Athos Supervisor
                  </span>
                  <Badge variant={athosDelegated ? "default" : "outline"} className={athosDelegated ? "bg-emerald-500" : ""}>
                    {athosDelegated ? "Mandato Ativo" : "Sem Mandato"}
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Escopo: <code className="font-mono">planning.execution.manage</code>, <code className="font-mono">wave.release</code>
                </p>
                {athosDelegated && (
                  <p className="text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    Expira em 23h 45m (Nível de Risco Médio)
                  </p>
                )}
              </div>

              <Button
                variant={athosDelegated ? "outline" : "default"}
                size="sm"
                className="w-full text-xs"
                onClick={() => setAthosDelegated(!athosDelegated)}
              >
                {athosDelegated ? "Revogar Mandato do #Athos" : "Conceder Mandato de 24h"}
              </Button>
            </CardContent>
          </Card>

          {/* Políticas Ativas do AI-SDLC */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Lock className="h-4 w-4 text-primary" />
                Políticas de Segurança Vigentes
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2.5 text-xs text-muted-foreground">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0 mt-0.5" />
                <span>Nenhuma alteração de BD entra em produção sem migração Alembic aprovada.</span>
              </div>
              <div className="flex items-start gap-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0 mt-0.5" />
                <span>Lotes de tarefas requerem autorização prévia de wave no Cockpit.</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
