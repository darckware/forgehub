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
  type ApprovalCreateInput,
} from "@/hooks/useGovernance";
import { ApprovalForm } from "./ApprovalForm";
import { EntityRef } from "@/components/EntityRef";

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
