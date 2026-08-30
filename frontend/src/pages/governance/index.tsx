import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Clock, Loader2, Plus, ShieldCheck, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  useApprovals,
  useApproveApproval,
  useCreateApproval,
  useDecideGovernedApproval,
  useGovernedApprovalRequests,
  useRejectApproval,
  type Approval,
  type ApprovalCreateInput,
  type GovernedApprovalRequest,
} from "@/hooks/useGovernance";
import { ApprovalForm } from "./ApprovalForm";

const STATUS_VARIANT: Record<string, "outline" | "success" | "destructive" | "secondary"> = {
  pending: "outline",
  approved: "success",
  rejected: "destructive",
  decided: "secondary",
  expired: "destructive",
  stale: "destructive",
};

function ApprovalRow({ approval }: { approval: Approval }) {
  const approve = useApproveApproval();
  const reject = useRejectApproval();
  const isPending = approval.status === "pending";
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Link to={`/governance/${approval.id}`} className="font-medium hover:underline">
            {approval.approval_type}
          </Link>
          <Badge variant="outline" className="text-xs">{approval.entity_type}</Badge>
          <Badge variant={STATUS_VARIANT[approval.status] ?? "outline"}>{approval.status}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {approval.requested_by} · entidade {approval.entity_id.slice(0, 8)}…
          {approval.comments && <> · {approval.comments}</>}
        </p>
      </div>
      {isPending && (
        <div className="flex shrink-0 gap-2">
          <Button
            size="sm" variant="outline" disabled={approve.isPending || reject.isPending}
            onClick={() => approve.mutate({ id: approval.id, decided_by: "operator" })}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />Aprovar
          </Button>
          <Button
            size="sm" variant="ghost" disabled={approve.isPending || reject.isPending}
            onClick={() => reject.mutate({ id: approval.id, decided_by: "operator" })}
          >
            <XCircle className="mr-1.5 h-3.5 w-3.5 text-destructive" />Rejeitar
          </Button>
        </div>
      )}
    </div>
  );
}

function ApprovalsTab() {
  const approvals = useApprovals();
  const create = useCreateApproval();
  const [showForm, setShowForm] = useState(false);

  const pending = approvals.data?.filter((a) => a.status === "pending") ?? [];
  const decided = approvals.data?.filter((a) => a.status !== "pending") ?? [];

  const submit = async (values: ApprovalCreateInput) => {
    await create.mutateAsync({
      ...values,
      comments: values.comments || undefined,
      policy_id: values.policy_id || undefined,
    });
    setShowForm(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          {showForm ? "Cancelar" : "Nova Aprovação"}
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle className="text-base">Nova Aprovação</CardTitle></CardHeader>
          <CardContent>
            <ApprovalForm onSubmit={submit} onCancel={() => setShowForm(false)} isSubmitting={create.isPending} />
            {create.isError && <p className="mt-2 text-sm text-destructive">{(create.error as Error)?.message}</p>}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base"><Clock className="h-4 w-4" />Pendentes</CardTitle>
          <CardDescription>{pending.length} aguardando decisão</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {approvals.isLoading && <p className="text-sm text-muted-foreground">Carregando...</p>}
          {!approvals.isLoading && pending.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma aprovação pendente.</p>}
          {pending.map((a) => <ApprovalRow key={a.id} approval={a} />)}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Histórico</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {decided.length === 0 && <p className="text-sm text-muted-foreground">Sem decisões ainda.</p>}
          {decided.map((a) => <ApprovalRow key={a.id} approval={a} />)}
        </CardContent>
      </Card>
    </div>
  );
}

function ConceptApprovalRow({ request }: { request: GovernedApprovalRequest }) {
  const decide = useDecideGovernedApproval();
  const [comments, setComments] = useState("");
  const isPending = request.status === "pending";
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium">{request.approval_type} — {request.target_type}</p>
          <p className="text-xs text-muted-foreground">
            Solicitado por {request.requested_by_name} ({request.requested_by_type}) · alvo {request.target_id.slice(0, 8)}…
          </p>
        </div>
        <Badge variant={STATUS_VARIANT[request.status] ?? "outline"}>{request.status}</Badge>
      </div>
      {isPending && (
        <div className="flex items-end gap-2">
          <Textarea rows={1} placeholder="Comentário (opcional)" value={comments} onChange={(e) => setComments(e.target.value)} className="resize-none flex-1" />
          <Button
            size="sm" variant="outline" disabled={decide.isPending}
            onClick={() => decide.mutate({ requestId: request.id, decision: "approved", comments: comments || undefined })}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />Aprovar
          </Button>
          <Button
            size="sm" variant="ghost" disabled={decide.isPending}
            onClick={() => decide.mutate({ requestId: request.id, decision: "rejected", comments: comments || undefined })}
          >
            <XCircle className="mr-1.5 h-3.5 w-3.5 text-destructive" />Rejeitar
          </Button>
        </div>
      )}
      {decide.isError && <p className="text-xs text-destructive">{(decide.error as Error)?.message}</p>}
    </div>
  );
}

function ConceptApprovalsTab() {
  const requests = useGovernedApprovalRequests();
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base"><AlertTriangle className="h-4 w-4" />Aprovações de Concepção</CardTitle>
        <CardDescription>
          Fluxo governado (policy + separação de deveres) usado para aprovar Concepções antes da autorização de entrega.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {requests.isLoading && <p className="text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Carregando...</p>}
        {!requests.isLoading && (requests.data?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">Nenhuma solicitação de aprovação de concepção.</p>}
        {requests.data?.map((r) => <ConceptApprovalRow key={r.id} request={r} />)}
      </CardContent>
    </Card>
  );
}

export default function GovernancePage() {
  const [tab, setTab] = useState("approvals");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><ShieldCheck className="h-6 w-6" />Governança</h1>
        <p className="text-sm text-muted-foreground">
          Aprovações, trilha de auditoria e políticas. Ver também <Link to="/governance/policies" className="text-primary hover:underline">Políticas</Link>.
        </p>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="approvals">Aprovações</TabsTrigger>
          <TabsTrigger value="concept">Aprovações de Concepção</TabsTrigger>
        </TabsList>
        <TabsContent value="approvals" className="mt-4">
          <ApprovalsTab />
        </TabsContent>
        <TabsContent value="concept" className="mt-4">
          <ConceptApprovalsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
