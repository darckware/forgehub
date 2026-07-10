import { Link, useParams } from "react-router-dom";
import {
  AlertCircle,
  Bug,
  FolderOpen,
  Gavel,
  Layers,
  Lightbulb,
  Loader2,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { usePlanningItem } from "@/hooks/useBacklog";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { EntityDocsCard } from "@/components/EntityDocsCard";

export default function PlanningItemDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: item, isLoading, isError, error } = usePlanningItem(id);

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Planning", href: "/backlog" },
          { label: item?.title ?? "…" },
        ]}
      />

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading planning item…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load planning item: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && item && (
        <>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{item.title}</h1>
              {item.description && (
                <p className="mt-1 max-w-2xl text-muted-foreground">{item.description}</p>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              <Badge variant="outline" className="text-sm capitalize">
                {item.item_type.replace("_", " ")}
              </Badge>
              <Badge variant="outline" className="text-sm capitalize">
                {item.status.replace("_", " ")}
              </Badge>
            </div>
          </div>

          {item.output_path && (
            <Card className="border-primary/30 bg-primary/5">
              <CardContent className="flex items-center gap-3 py-4">
                <FolderOpen className="h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Output path
                  </p>
                  <p className="truncate font-mono text-sm">{item.output_path}</p>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            {item.feature_request && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-xl">
                    <Lightbulb className="h-5 w-5" />
                    Feature request
                  </CardTitle>
                  <CardDescription>Acceptance criteria and business rationale.</CardDescription>
                </CardHeader>
                <CardContent>
                  <dl className="space-y-3 text-sm">
                    {item.feature_request.acceptance_criteria && (
                      <div>
                        <dt className="font-medium text-muted-foreground">
                          Acceptance criteria
                        </dt>
                        <dd>{item.feature_request.acceptance_criteria}</dd>
                      </div>
                    )}
                    {item.feature_request.business_value && (
                      <div>
                        <dt className="font-medium text-muted-foreground">Business value</dt>
                        <dd>{item.feature_request.business_value}</dd>
                      </div>
                    )}
                    {item.feature_request.requested_by && (
                      <div>
                        <dt className="font-medium text-muted-foreground">Requested by</dt>
                        <dd>{item.feature_request.requested_by}</dd>
                      </div>
                    )}
                  </dl>
                </CardContent>
              </Card>
            )}

            {item.bug_report && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-xl">
                    <Bug className="h-5 w-5" />
                    Bug report
                  </CardTitle>
                  <CardDescription>Severity, environment, and reproduction.</CardDescription>
                </CardHeader>
                <CardContent>
                  <dl className="space-y-3 text-sm">
                    {item.bug_report.severity && (
                      <div className="flex items-center gap-2">
                        <dt className="font-medium text-muted-foreground">Severity</dt>
                        <dd>
                          <Badge variant="destructive" className="capitalize">
                            {item.bug_report.severity}
                          </Badge>
                        </dd>
                      </div>
                    )}
                    {item.bug_report.environment && (
                      <div>
                        <dt className="font-medium text-muted-foreground">Environment</dt>
                        <dd>{item.bug_report.environment}</dd>
                      </div>
                    )}
                    {item.bug_report.detected_in_version && (
                      <div>
                        <dt className="font-medium text-muted-foreground">
                          Detected in version
                        </dt>
                        <dd>{item.bug_report.detected_in_version}</dd>
                      </div>
                    )}
                    {item.bug_report.fixed_in_version && (
                      <div>
                        <dt className="font-medium text-muted-foreground">Fixed in version</dt>
                        <dd>{item.bug_report.fixed_in_version}</dd>
                      </div>
                    )}
                    {item.bug_report.steps_to_reproduce && (
                      <div>
                        <dt className="font-medium text-muted-foreground">
                          Steps to reproduce
                        </dt>
                        <dd className="whitespace-pre-wrap">
                          {item.bug_report.steps_to_reproduce}
                        </dd>
                      </div>
                    )}
                  </dl>
                </CardContent>
              </Card>
            )}

            {!item.feature_request && !item.bug_report && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-xl">Details</CardTitle>
                  <CardDescription>
                    No feature or bug specialization recorded for this item yet.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Planning items of type "{item.item_type.replace("_", " ")}" carry no nested
                    specialization in this view.
                  </p>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <Layers className="h-5 w-5" />
                  Version scope
                </CardTitle>
                <CardDescription>Product versions this item is scoped into.</CardDescription>
              </CardHeader>
              <CardContent>
                {item.version_scope_items && item.version_scope_items.length > 0 ? (
                  <ul className="space-y-2 text-sm">
                    {item.version_scope_items.map((scope) => (
                      <li key={scope.id} className="flex items-center justify-between gap-2">
                        <span>{scope.product_version_id}</span>
                        <Badge variant={scope.removed_at ? "destructive" : "success"}>
                          {scope.removed_at ? "removed" : "in scope"}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    This item has not been scoped into a product version yet.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Gavel className="h-5 w-5" />
                Triage decisions
              </CardTitle>
              <CardDescription>
                Outcomes recorded while triaging this item into (or out of) scope.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {item.triage_decisions && item.triage_decisions.length > 0 ? (
                <ul className="space-y-3 text-sm">
                  {item.triage_decisions.map((decision) => (
                    <li key={decision.id} className="rounded-md border border-border p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium capitalize">{decision.decision}</span>
                        {decision.decided_at && (
                          <span className="text-xs text-muted-foreground">
                            {decision.decided_at}
                          </span>
                        )}
                      </div>
                      {decision.rationale && (
                        <p className="mt-1 text-muted-foreground">{decision.rationale}</p>
                      )}
                      {decision.decided_by && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Decided by {decision.decided_by}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No triage decisions have been recorded for this item yet.
                </p>
              )}
            </CardContent>
          </Card>

          <EntityDocsCard entityType="planning_item" entityId={item.id} />

          <div>
            <Link to="/backlog" className={buttonVariants({ variant: "outline" })}>
              Back to list
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
