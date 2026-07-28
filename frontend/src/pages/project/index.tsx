import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AlertCircle, CheckSquare, FolderKanban, ListTodo, Loader2, Plus, Trash2 } from "lucide-react";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useCreateProject,
  useDeleteProject,
  useProjects,
  type ProjectCreateInput,
} from "@/hooks/useProject";
import { useProducts } from "@/hooks/useProduct";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ProjectForm } from "./ProjectForm";
import BacklogPage from "../backlog";
import TaskPage from "../task";

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
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") || "projects";

  const { data: projects, isLoading, isError, error } = useProjects();
  const { data: products } = useProducts();
  const [selectedProductId, setSelectedProductId] = useState<string>("");

  const createProject = useCreateProject();
  const deleteProject = useDeleteProject();
  const [showForm, setShowForm] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  // Filter projects by selected product if a product filter is active
  const filteredProjects = projects?.filter((p) => {
    if (!selectedProductId) return true;
    if (!p.product_version_id) return false;
    const prod = products?.find((pr) => pr.id === selectedProductId);
    return prod?.versions?.some((ver) => ver.id === p.product_version_id);
  });

  const versionLabel = (versionId: string): string => {
    for (const product of products ?? []) {
      const v = product.versions?.find((ver) => ver.id === versionId);
      if (v) return `${product.name} -- v${v.version}`;
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
      <Tabs
        value={activeTab}
        onValueChange={(val) => {
          setSearchParams({ tab: val });
        }}
        className="w-full space-y-6"
      >
        <div className="flex flex-col gap-4 border-b pb-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
              Central de Projetos, Planejamento & Tarefas
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Fase 4 (Projetos & Escopo) e Fase 5 (Backlog de Tarefas & Liberação para Execução) do AI-SDLC.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted-foreground">Produto:</span>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-xs font-medium focus-visible:ring-1 focus-visible:ring-primary"
                value={selectedProductId}
                onChange={(e) => setSelectedProductId(e.target.value)}
              >
                <option value="">Todos os Produtos</option>
                {products?.map((prod) => (
                  <option key={prod.id} value={prod.id}>
                    {prod.name}
                  </option>
                ))}
              </select>
            </div>
            <TabsList className="grid grid-cols-3 bg-muted/60 p-1">
              <TabsTrigger value="projects" className="flex items-center gap-2 data-[state=active]:bg-background">
                <FolderKanban className="h-4 w-4" />
                Projetos do Produto
              </TabsTrigger>
              <TabsTrigger value="planning" className="flex items-center gap-2 data-[state=active]:bg-background">
                <ListTodo className="h-4 w-4" />
                Planejamento & Escopo
              </TabsTrigger>
              <TabsTrigger value="tasks" className="flex items-center gap-2 data-[state=active]:bg-background">
                <CheckSquare className="h-4 w-4" />
                Tarefas & Liberação
              </TabsTrigger>
            </TabsList>
          </div>
        </div>

        {/* Dynamic Context Header Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="bg-muted/20 border-primary/20">
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Fase 4 -- Projetos do Produto
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <div className="text-2xl font-bold">{filteredProjects?.length ?? 0}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {selectedProductId
                  ? `Projetos associados a ${products?.find((p) => p.id === selectedProductId)?.name}`
                  : "Projetos ativos vinculados a versões do produto"}
              </p>
            </CardContent>
          </Card>

          <Card className="bg-muted/20 border-primary/20">
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Fase 4 -- Planejamento
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <div className="text-2xl font-bold">Escopo Integrado</div>
              <p className="text-xs text-muted-foreground mt-1">Features, bugs e melhorias triados no backlog</p>
            </CardContent>
          </Card>

          <Card className="bg-muted/20 border-primary/20">
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Fase 5 -- Liberação
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-0">
              <div className="text-2xl font-bold">Execução Nativa</div>
              <p className="text-xs text-muted-foreground mt-1">Decomposição e ondas de execução de tarefas</p>
            </CardContent>
          </Card>
        </div>

        <TabsContent value="projects" className="pt-2 space-y-6">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Cadastre e gerencie projetos para associar o planejamento técnico aos lançamentos.
            </p>
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

          {!isLoading && !isError && filteredProjects && filteredProjects.length === 0 && (
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

          {!isLoading && !isError && filteredProjects && filteredProjects.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredProjects.map((project) => (
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
        </TabsContent>

        <TabsContent value="planning" className="pt-4">
          <BacklogPage />
        </TabsContent>

        <TabsContent value="tasks" className="pt-4">
          <TaskPage />
        </TabsContent>
      </Tabs>
    </div>
  );
}
