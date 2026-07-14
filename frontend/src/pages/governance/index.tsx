import { useState } from "react";
import { Link } from "react-router-dom";
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
          <h1 className="text-3xl font-bold tracking-tight">Governance</h1>
          <p className="text-muted-foreground">
            Approvals for gated transitions -- pipeline stage gates, release readiness, critical
            skills, and change requests -- backed by audit events and policies.
          </p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          New approval
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Request approval</CardTitle>
            <CardDescription>
              Record an approval request for a gated transition before it is decided.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ApprovalForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createApproval.isPending}
            />
            {createApproval.isError && (
              <p className="mt-3 text-sm text-destructive">
                Failed to create approval: {(createApproval.error as Error)?.message}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Governed planning approvals</CardTitle>
          <CardDescription>Identity, revision hash, policy evaluation and separation of duties are enforced by the backend.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {governed.isLoading && <p className="text-sm text-muted-foreground">Loading governed approvals…</p>}
          {governed.data?.length === 0 && <p className="text-sm text-muted-foreground">No governed approval is pending.</p>}
          {governed.isError && <p className="text-sm text-destructive">You do not have permission to view governed approvals.</p>}
          {governed.data?.map((request) => {
            const selfApproval = request.requested_by_type === "user" && request.requested_by_id === currentUser?.id;
            return <div key={request.id} className="rounded-lg border p-4">
              <div className="flex flex-wrap justify-between gap-3"><div><p className="font-medium">{request.approval_type.replace(/_/g, " ")}</p><p className="text-sm text-muted-foreground">Requested by {request.requested_by_name}</p><code className="block text-[11px] text-muted-foreground">revision {request.target_revision_id} · {request.target_hash.slice(0, 12)}</code><code className="text-[11px] text-muted-foreground">policy evaluation {request.policy_evaluation_id}</code></div><Badge variant="warning">{request.status}</Badge></div>
              <div className="mt-3 flex flex-wrap gap-2"><Button size="sm" disabled={!canDecide || selfApproval || decideGoverned.isPending} onClick={() => decideGoverned.mutate({ requestId: request.id, decision: "approved" })}>Approve</Button><Button size="sm" variant="outline" disabled={!canDecide || selfApproval || decideGoverned.isPending} onClick={() => decideGoverned.mutate({ requestId: request.id, decision: "changes_requested" })}>Request changes</Button><Button size="sm" variant="destructive" disabled={!canDecide || selfApproval || decideGoverned.isPending} onClick={() => decideGoverned.mutate({ requestId: request.id, decision: "rejected" })}>Reject</Button>{selfApproval && <span className="self-center text-xs text-amber-600">Separation of duties: another authority must decide.</span>}</div>
            </div>;
          })}
          {decideGoverned.isError && <p className="text-sm text-destructive">Decision blocked by authority, policy, expiry or separation of duties.</p>}
        </CardContent>
      </Card>

      {canManageDelegation && <Card>
        <CardHeader><CardTitle>Athos authority</CardTitle><CardDescription>Grant bounded, expiring authority. This does not release Tasks or CLI execution.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {athos ? <Button variant="outline" disabled={grantDelegation.isPending} onClick={() => grantDelegation.mutate({ grantee_agent_id: athos.id, allowed_actions: ["governance.approval.decide", "planning.delivery.authorize", "planning.progress.view", "planning.progress.manage", "planning.stage.complete", "planning.execution.view", "planning.execution.manage", "planning.execution.dispatch", "planning.execution.cancel"], scope_type: "organization", max_risk: "medium", expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), reason: "24-hour governed planning, execution and recovery mandate" })}>Grant Athos 24-hour planning mandate</Button> : <p className="text-sm text-muted-foreground">Athos agent was not found in the agent registry.</p>}
          {delegations.data?.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded border p-3 text-sm"><div><p className="font-medium">{item.status} · {item.scope_type}</p><p className="text-xs text-muted-foreground">{item.allowed_actions.join(", ")} · expires {new Date(item.expires_at).toLocaleString()}</p></div>{item.status === "active" && <Button size="sm" variant="destructive" onClick={() => revokeDelegation.mutate(item.id)}>Revoke</Button>}</div>)}
        </CardContent>
      </Card>}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading approvals…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load approvals: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && approvals && approvals.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Gavel className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No approvals yet</p>
              <p className="text-sm text-muted-foreground">
                Request your first approval to start tracking gated decisions.
              </p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New approval
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
                  <TableHead>Entity</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Requested by</TableHead>
                  <TableHead>Decided by</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
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
                        View
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
