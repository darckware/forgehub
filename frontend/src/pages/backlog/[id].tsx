import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
import { EntityDocsCard } from "@/components/EntityDocsCard";

export default function PlanningItemDetailPage() {
  const { t } = useTranslation("backlog");
  const { id } = useParams<{ id: string }>();
  const { data: item, isLoading, isError, error } = usePlanningItem(id);

  return (
    <div className="space-y-6">
      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("detail.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("detail.loadError", { error: (error as Error)?.message })}</span>
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
                {t(`enums.itemTypes.${item.item_type}`, {
                  defaultValue: item.item_type.replace("_", " "),
                })}
              </Badge>
              <Badge variant="outline" className="text-sm capitalize">
                {t(`enums.statuses.${item.status}`, {
                  defaultValue: item.status.replace("_", " "),
                })}
              </Badge>
            </div>
          </div>

          {item.output_path && (
            <Card className="border-primary/30 bg-primary/5">
              <CardContent className="flex items-center gap-3 py-4">
                <FolderOpen className="h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {t("detail.outputPathLabel")}
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
                    {t("detail.featureRequest.title")}
                  </CardTitle>
                  <CardDescription>{t("detail.featureRequest.description")}</CardDescription>
                </CardHeader>
                <CardContent>
                  <dl className="space-y-3 text-sm">
                    {item.feature_request.acceptance_criteria && (
                      <div>
                        <dt className="font-medium text-muted-foreground">
                          {t("detail.featureRequest.acceptanceCriteria")}
                        </dt>
                        <dd>{item.feature_request.acceptance_criteria}</dd>
                      </div>
                    )}
                    {item.feature_request.business_value && (
                      <div>
                        <dt className="font-medium text-muted-foreground">{t("detail.featureRequest.businessValue")}</dt>
                        <dd>{item.feature_request.business_value}</dd>
                      </div>
                    )}
                    {item.feature_request.requested_by && (
                      <div>
                        <dt className="font-medium text-muted-foreground">{t("detail.featureRequest.requestedBy")}</dt>
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
                    {t("detail.bugReport.title")}
                  </CardTitle>
                  <CardDescription>{t("detail.bugReport.description")}</CardDescription>
                </CardHeader>
                <CardContent>
                  <dl className="space-y-3 text-sm">
                    {item.bug_report.severity && (
                      <div className="flex items-center gap-2">
                        <dt className="font-medium text-muted-foreground">{t("detail.bugReport.severity")}</dt>
                        <dd>
                          <Badge variant="destructive" className="capitalize">
                            {t(`enums.severities.${item.bug_report.severity}`, {
                              defaultValue: item.bug_report.severity,
                            })}
                          </Badge>
                        </dd>
                      </div>
                    )}
                    {item.bug_report.environment && (
                      <div>
                        <dt className="font-medium text-muted-foreground">{t("detail.bugReport.environment")}</dt>
                        <dd>{item.bug_report.environment}</dd>
                      </div>
                    )}
                    {item.bug_report.detected_in_version && (
                      <div>
                        <dt className="font-medium text-muted-foreground">
                          {t("detail.bugReport.detectedInVersion")}
                        </dt>
                        <dd>{item.bug_report.detected_in_version}</dd>
                      </div>
                    )}
                    {item.bug_report.fixed_in_version && (
                      <div>
                        <dt className="font-medium text-muted-foreground">{t("detail.bugReport.fixedInVersion")}</dt>
                        <dd>{item.bug_report.fixed_in_version}</dd>
                      </div>
                    )}
                    {item.bug_report.steps_to_reproduce && (
                      <div>
                        <dt className="font-medium text-muted-foreground">
                          {t("detail.bugReport.stepsToReproduce")}
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
                  <CardTitle className="text-xl">{t("detail.noSpecialization.title")}</CardTitle>
                  <CardDescription>
                    {t("detail.noSpecialization.description")}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {t("detail.noSpecialization.body", {
                      type: t(`enums.itemTypes.${item.item_type}`, {
                        defaultValue: item.item_type.replace("_", " "),
                      }),
                    })}
                  </p>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <Layers className="h-5 w-5" />
                  {t("detail.versionScope.title")}
                </CardTitle>
                <CardDescription>{t("detail.versionScope.description")}</CardDescription>
              </CardHeader>
              <CardContent>
                {item.version_scope_items && item.version_scope_items.length > 0 ? (
                  <ul className="space-y-2 text-sm">
                    {item.version_scope_items.map((scope) => (
                      <li key={scope.id} className="flex items-center justify-between gap-2">
                        <span>{scope.product_version_id}</span>
                        <Badge variant={scope.removed_at ? "destructive" : "success"}>
                          {scope.removed_at ? t("detail.versionScope.removed") : t("detail.versionScope.inScope")}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {t("detail.versionScope.empty")}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Gavel className="h-5 w-5" />
                {t("detail.triageDecisions.title")}
              </CardTitle>
              <CardDescription>
                {t("detail.triageDecisions.description")}
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
                          {t("detail.triageDecisions.decidedBy", { name: decision.decided_by })}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {t("detail.triageDecisions.empty")}
                </p>
              )}
            </CardContent>
          </Card>

          <EntityDocsCard entityType="planning_item" entityId={item.id} />

          <div>
            <Link to="/backlog" className={buttonVariants({ variant: "outline" })}>
              {t("detail.backToList")}
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
