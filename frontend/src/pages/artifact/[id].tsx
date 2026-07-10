import { Link, useParams } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  FileText,
  Loader2,
  Lock,
  Unlock,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useArtifact, useUpdateArtifact, type ArtifactVersion } from "@/hooks/useArtifact";
import { Breadcrumb } from "@/components/ui/breadcrumb";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  draft: "outline",
  in_review: "warning",
  approved: "success",
  rejected: "destructive",
  superseded: "secondary",
};

function VersionRow({ version }: { version: ArtifactVersion }) {
  return (
    <li
      className={cn(
        "flex items-start justify-between gap-4 rounded-md border border-border p-3",
        version.is_current && "border-primary/50 bg-primary/5"
      )}
    >
      <div className="flex items-start gap-3">
        {version.is_current ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
        ) : (
          <CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <div>
          <p className="font-medium">
            v{version.version}
            {version.is_current && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">current</span>
            )}
          </p>
          {version.notes && <p className="text-sm text-muted-foreground">{version.notes}</p>}
          {version.checksum && (
            <p className="mt-1 font-mono text-xs text-muted-foreground">{version.checksum}</p>
          )}
        </div>
      </div>
      {version.content_url && (
        <a
          href={version.content_url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-sm text-primary hover:underline"
        >
          Open
        </a>
      )}
    </li>
  );
}

export default function ArtifactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: artifact, isLoading, isError, error } = useArtifact(id);
  const updateArtifact = useUpdateArtifact(id ?? "");

  const sortedVersions = artifact?.versions
    ? [...artifact.versions].sort((a, b) => a.version.localeCompare(b.version, undefined, { numeric: true }))
    : [];

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Artifacts", href: "/artifact" },
          { label: artifact?.name ?? "…" },
        ]}
      />

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading artifact…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load artifact: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && artifact && (
        <>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{artifact.name}</h1>
              {artifact.description && (
                <p className="mt-1 text-muted-foreground">{artifact.description}</p>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              <Badge
                variant={STATUS_VARIANT[artifact.status] ?? "outline"}
                className="text-sm capitalize"
              >
                {artifact.status.replace(/_/g, " ")}
              </Badge>
              <Badge variant="outline" className="text-sm capitalize">
                {artifact.artifact_type.replace(/_/g, " ")}
              </Badge>
              {artifact.is_locked ? (
                <Badge variant="outline" className="gap-1 text-sm">
                  <Lock className="h-3 w-3" />
                  locked
                </Badge>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                disabled={updateArtifact.isPending}
                onClick={() => updateArtifact.mutate({ is_locked: !artifact.is_locked })}
              >
                {artifact.is_locked ? (
                  <>
                    <Unlock className="mr-2 h-4 w-4" />
                    Unlock
                  </>
                ) : (
                  <>
                    <Lock className="mr-2 h-4 w-4" />
                    Lock
                  </>
                )}
              </Button>
            </div>
          </div>

          {updateArtifact.isError && (
            <p className="text-sm text-destructive">
              {(updateArtifact.error as Error)?.message}
            </p>
          )}

          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Project</CardDescription>
              </CardHeader>
              <CardContent className="text-sm">{artifact.project_id ?? "—"}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Pipeline stage</CardDescription>
              </CardHeader>
              <CardContent className="text-sm">{artifact.pipeline_stage_id ?? "—"}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>Task execution</CardDescription>
              </CardHeader>
              <CardContent className="text-sm">{artifact.task_execution_id ?? "—"}</CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Versions</CardTitle>
              <CardDescription>
                Every revision of this deliverable, most recent first. The version marked
                "current" is what satisfies pipeline stage requirements.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {sortedVersions.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-10 text-center text-muted-foreground">
                  <FileText className="h-8 w-8" />
                  <p className="text-sm">No versions recorded for this artifact yet.</p>
                </div>
              ) : (
                <ul className="space-y-2">
                  {[...sortedVersions].reverse().map((version) => (
                    <VersionRow key={version.id} version={version} />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <div>
            <Link to="/artifact" className={buttonVariants({ variant: "outline" })}>
              Back to list
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
