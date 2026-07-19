import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertCircle, FolderKanban, Loader2, Plus, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  useCreateProject,
  useDeleteProject,
  useProjects,
  type ProjectCreateInput,
} from "@/hooks/useProject";
import { useProducts } from "@/hooks/useProduct";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ProjectForm } from "./ProjectForm";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  planned: "outline",
  active: "success",
  on_hold: "warning",
  completed: "secondary",
  cancelled: "destructive",
};

export default function ProjectPage() {
  const { t } = useTranslation("project");
  const { data: projects, isLoading, isError, error } = useProjects();
  const { data: products } = useProducts();
  const createProject = useCreateProject();
  const deleteProject = useDeleteProject();
  const [showForm, setShowForm] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const versionLabel = (versionId: string): string => {
    for (const product of products ?? []) {
      const v = product.versions?.find((ver) => ver.id === versionId);
      if (v) return `${product.name} — v${v.version}`;
    }
    return versionId.slice(0, 8) + "…";
  };

  function handleCreate(values: ProjectCreateInput) {
    createProject.mutate(
      {
        ...values,
        description: values.description || undefined,
        working_directory_path: values.working_directory_path || undefined,
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
          <p className="text-muted-foreground">{t("list.subtitle")}</p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          {t("list.newProject")}
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>{t("list.createCardTitle")}</CardTitle>
            <CardDescription>{t("list.createCardDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ProjectForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createProject.isPending}
            />
            {createProject.isError && (
              <p className="mt-3 text-sm text-destructive">
                {t("list.createError", { message: (createProject.error as Error)?.message })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

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
            <span>{t("list.loadError", { message: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && projects && projects.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <FolderKanban className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">{t("list.emptyTitle")}</p>
              <p className="text-sm text-muted-foreground">{t("list.emptyDescription")}</p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t("list.newProject")}
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && projects && projects.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Card key={project.id} className="flex flex-col">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-lg leading-tight">{project.name}</CardTitle>
                  <Badge variant={STATUS_VARIANT[project.status] ?? "outline"}>
                    {t(`enums.projectStatus.${project.status}`, project.status)}
                  </Badge>
                </div>
                {project.description && (
                  <CardDescription className="line-clamp-2">{project.description}</CardDescription>
                )}
              </CardHeader>
              <CardContent className="flex-1 text-sm text-muted-foreground">
                {project.product_version_id ? (
                  <p>{versionLabel(project.product_version_id)}</p>
                ) : (
                  <p className="italic">{t("list.noVersionLinked")}</p>
                )}
              </CardContent>
              <CardFooter className="flex justify-between gap-2">
                <Link
                  to={`/projects/${project.id}`}
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                >
                  {t("list.viewDetails")}
                </Link>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setPendingDeleteId(project.id)}
                  disabled={deleteProject.isPending}
                  aria-label={t("list.deleteAria", { name: project.name })}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={t("list.deleteDialogTitle")}
        description={t("list.deleteDialogDescription")}
        confirmLabel={t("shared.delete")}
        onConfirm={() => {
          if (pendingDeleteId) deleteProject.mutate(pendingDeleteId);
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}
