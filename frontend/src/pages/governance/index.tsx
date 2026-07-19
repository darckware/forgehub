import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertCircle, Gavel, Loader2, Plus } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useApprovals,
  useCreateApproval,
  useDecideGovernedApproval,
  useGovernedApprovalRequests,
  useAuthorityDelegations,
  useGrantAuthorityDelegation,
  useRevokeAuthorityDelegation,
  type ApprovalCreateInput,
} from "@/hooks/useGovernance";
import { ApprovalForm } from "./ApprovalForm";
import { EntityRef } from "@/components/EntityRef";
import { useActionPermission } from "@/hooks/usePermission";
import { useAuthStore } from "@/store/authStore";
import { useAgents } from "@/hooks/useAgent";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  pending: "warning",
  approved: "success",
  rejected: "destructive",
};

export default function GovernancePage() {
  const { t } = useTranslation("governance");
  const { data: approvals, isLoading, isError, error } = useApprovals();
  const createApproval = useCreateApproval();
  const [showForm, setShowForm] = useState(false);
  const governed = useGovernedApprovalRequests("pending");
  const decideGoverned = useDecideGovernedApproval();
  const canDecide = useActionPermission("governance.approval.decide");
  const currentUser = useAuthStore((state) => state.user);
  const canManageDelegation = useActionPermission("governance.delegation.manage");
  const agents = useAgents();
  const delegations = useAuthorityDelegations(canManageDelegation);
  const grantDelegation = useGrantAuthorityDelegation();
  const revokeDelegation = useRevokeAuthorityDelegation();
  const athos = agents.data?.find((agent) => agent.profile_slug === "athos" || agent.name.toLowerCase() === "athos");

  function handleCreate(values: ApprovalCreateInput) {
    createApproval.mutate(
      {
        ...values,
        comments: values.comments || undefined,
        policy_id: values.policy_id || undefined,
      },
      {
        onSuccess: () => setShowForm(false),
      }
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("list.title")}</h1>
          <p className="text-muted-foreground">{t("list.description")}</p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          {t("list.newApproval")}
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>{t("list.requestForm.title")}</CardTitle>
            <CardDescription>{t("list.requestForm.description")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ApprovalForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createApproval.isPending}
            />
            {createApproval.isError && (
              <p className="mt-3 text-sm text-destructive">
                {t("list.requestForm.createFailed", { message: (createApproval.error as Error)?.message })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t("list.governed.title")}</CardTitle>
          <CardDescription>{t("list.governed.description")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {governed.isLoading && <p className="text-sm text-muted-foreground">{t("list.governed.loading")}</p>}
          {governed.data?.length === 0 && <p className="text-sm text-muted-foreground">{t("list.governed.empty")}</p>}
          {governed.isError && <p className="text-sm text-destructive">{t("list.governed.noPermission")}</p>}
          {governed.data?.map((request) => {
            const selfApproval = request.requested_by_type === "user" && request.requested_by_id === currentUser?.id;
            return <div key={request.id} className="rounded-lg border p-4">
              <div className="flex flex-wrap justify-between gap-3"><div><p className="font-medium">{request.approval_type.replace(/_/g, " ")}</p><p className="text-sm text-muted-foreground">{t("list.governed.requestedBy", { name: request.requested_by_name })}</p><code className="block text-[11px] text-muted-foreground">{t("list.governed.revision", { id: request.target_revision_id, hash: request.target_hash.slice(0, 12) })}</code><code className="text-[11px] text-muted-foreground">{t("list.governed.policyEvaluation", { id: request.policy_evaluation_id })}</code></div><Badge variant="warning">{request.status}</Badge></div>
              <div className="mt-3 flex flex-wrap gap-2"><Button size="sm" disabled={!canDecide || selfApproval || decideGoverned.isPending} onClick={() => decideGoverned.mutate({ requestId: request.id, decision: "approved" })}>{t("list.governed.approve")}</Button><Button size="sm" variant="outline" disabled={!canDecide || selfApproval || decideGoverned.isPending} onClick={() => decideGoverned.mutate({ requestId: request.id, decision: "changes_requested" })}>{t("list.governed.requestChanges")}</Button><Button size="sm" variant="destructive" disabled={!canDecide || selfApproval || decideGoverned.isPending} onClick={() => decideGoverned.mutate({ requestId: request.id, decision: "rejected" })}>{t("list.governed.reject")}</Button>{selfApproval && <span className="self-center text-xs text-amber-600">{t("list.governed.separationOfDuties")}</span>}</div>
            </div>;
          })}
          {decideGoverned.isError && <p className="text-sm text-destructive">{t("list.governed.decisionBlocked")}</p>}
        </CardContent>
      </Card>

      {canManageDelegation && <Card>
        <CardHeader><CardTitle>{t("list.athos.title")}</CardTitle><CardDescription>{t("list.athos.description")}</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {athos ? <Button variant="outline" disabled={grantDelegation.isPending} onClick={() => grantDelegation.mutate({ grantee_agent_id: athos.id, allowed_actions: ["governance.approval.decide", "planning.delivery.authorize", "planning.progress.view", "planning.progress.manage", "planning.stage.complete", "planning.execution.view", "planning.execution.manage", "planning.execution.dispatch", "planning.execution.cancel"], scope_type: "organization", max_risk: "medium", expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), reason: "24-hour governed planning, execution and recovery mandate" })}>{t("list.athos.grantButton")}</Button> : <p className="text-sm text-muted-foreground">{t("list.athos.notFound")}</p>}
          {delegations.data?.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded border p-3 text-sm"><div><p className="font-medium">{item.status} · {item.scope_type}</p><p className="text-xs text-muted-foreground">{item.allowed_actions.join(", ")} · {t("list.athos.expires", { date: new Date(item.expires_at).toLocaleString() })}</p></div>{item.status === "active" && <Button size="sm" variant="destructive" onClick={() => revokeDelegation.mutate(item.id)}>{t("list.athos.revoke")}</Button>}</div>)}
        </CardContent>
      </Card>}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("list.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("list.loadFailed", { message: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && approvals && approvals.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Gavel className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">{t("list.empty.title")}</p>
              <p className="text-sm text-muted-foreground">{t("list.empty.description")}</p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t("list.newApproval")}
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && approvals && approvals.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("list.table.entity")}</TableHead>
                  <TableHead>{t("list.table.status")}</TableHead>
                  <TableHead>{t("list.table.requestedBy")}</TableHead>
                  <TableHead>{t("list.table.decidedBy")}</TableHead>
                  <TableHead className="text-right">{t("list.table.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {approvals.map((approval) => (
                  <TableRow key={approval.id}>
                    <TableCell>
                      <Link
                        to={`/governance/${approval.id}`}
                        className="font-medium hover:underline"
                      >
                        {approval.entity_type.replace(/_/g, " ")}
                      </Link>
                      <p className="line-clamp-1 text-sm text-muted-foreground">
                        <EntityRef entityType={approval.entity_type} entityId={approval.entity_id} />
                      </p>
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[approval.status] ?? "outline"}>
                        {approval.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {approval.requested_by ?? "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {approval.decided_by ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Link
                        to={`/governance/${approval.id}`}
                        className={buttonVariants({ variant: "outline", size: "sm" })}
                      >
                        {t("list.table.view")}
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
