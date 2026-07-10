import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, FileBox, Loader2, Lock, Plus, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  useArtifacts,
  useCreateArtifact,
  useDeleteArtifact,
  type ArtifactCreateInput,
} from "@/hooks/useArtifact";
import { ArtifactForm } from "./ArtifactForm";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

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

export default function ArtifactPage() {
  const { data: artifacts, isLoading, isError, error } = useArtifacts();
  const createArtifact = useCreateArtifact();
  const deleteArtifact = useDeleteArtifact();
  const [showForm, setShowForm] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  function handleCreate(values: ArtifactCreateInput) {
    createArtifact.mutate(
      {
        ...values,
        description: values.description || undefined,
        project_id: values.project_id || undefined,
        pipeline_stage_id: values.pipeline_stage_id || undefined,
        task_execution_id: values.task_execution_id || undefined,
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
          <h1 className="text-3xl font-bold tracking-tight">Artifacts</h1>
          <p className="text-muted-foreground">
            Formal deliverables produced by the project — specs, source code, test reports,
            release notes, and approval records — each tracked across revisions.
          </p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          New artifact
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Create artifact</CardTitle>
            <CardDescription>
              Register a new deliverable. Versions can be attached as the artifact evolves.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ArtifactForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createArtifact.isPending}
            />
            {createArtifact.isError && (
              <p className="mt-3 text-sm text-destructive">
                Failed to create artifact: {(createArtifact.error as Error)?.message}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading artifacts…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load artifacts: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && artifacts && artifacts.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <FileBox className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No artifacts yet</p>
              <p className="text-sm text-muted-foreground">
                A stage cannot complete without its required artifacts. Create one to start
                tracking deliverables.
              </p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New artifact
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && artifacts && artifacts.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead>Versions</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {artifacts.map((artifact) => (
                  <TableRow key={artifact.id}>
                    <TableCell>
                      <Link to={`/artifact/${artifact.id}`} className="font-medium hover:underline">
                        {artifact.name}
                      </Link>
                      {artifact.is_locked && (
                        <Badge variant="outline" className="ml-2 gap-1 text-xs">
                          <Lock className="h-3 w-3" />
                          locked
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground capitalize">
                      {artifact.artifact_type.replace(/_/g, " ")}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[artifact.status] ?? "outline"}>
                        {artifact.status.replace(/_/g, " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {artifact.project_id ?? "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {artifact.versions?.length ?? 0}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Link
                          to={`/artifact/${artifact.id}`}
                          className={buttonVariants({ variant: "outline", size: "sm" })}
                        >
                          View
                        </Link>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPendingDeleteId(artifact.id)}
                          disabled={deleteArtifact.isPending}
                          aria-label={`Delete ${artifact.name}`}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete artifact?"
        description="This will permanently delete the artifact. Locked artifacts should be unlocked first."
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDeleteId) deleteArtifact.mutate(pendingDeleteId);
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}
