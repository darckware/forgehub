import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import {
  ArrowLeft,
  Building2,
  Layers,
  Loader2,
  Save,
  Server,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { PageHeader } from "@/components/PageHeader";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";
import { useDarckwareClients } from "@/hooks/useClientOps";
import {
  useProducts,
  useCreateProduct,
  useUpdateProduct,
} from "@/hooks/useProduct";
import {
  useProjects,
  useCreateProject,
  useUpdateAnyProject,
  PROJECT_SOLUTION_TYPES,
  PROJECT_SOLUTION_TYPE_LABELS,
  type ProjectSolutionType,
  PROJECT_STATUSES,
} from "@/hooks/useProject";
import { useQueryClient } from "@tanstack/react-query";

export interface SystemFormData {
  name: string;
  description: string;
  solution_type: ProjectSolutionType;
  darckware_client_id: string;
  working_directory_path: string;
  github_repo_url: string;
  application_url: string;
  application_url_dev: string;
  status: string;
  initial_version?: string;
  initial_version_status?: string;
}

export default function SystemFormPage() {
  const { id } = useParams<{ id?: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: clientsData } = useDarckwareClients();
  const clientList = clientsData?.items ?? [];
  const { data: products, isLoading: isLoadingProducts } = useProducts();
  const { data: projects, isLoading: isLoadingProjects } = useProjects();

  const createProduct = useCreateProduct();
  const updateProduct = useUpdateProduct();
  const createProject = useCreateProject();
  const updateAnyProject = useUpdateAnyProject();

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Identify editing project and associated product
  const editingProject = isEdit
    ? projects?.find((p) => p.id === id) ??
      projects?.find((p) => {
        const prod = products?.find((pr) => pr.id === id);
        return prod?.versions?.some((v) => v.id === p.product_version_id);
      })
    : null;

  const associatedProduct = isEdit
    ? products?.find((pr) => pr.id === id) ??
      products?.find((pr) =>
        pr.versions?.some((v) => v.id === editingProject?.product_version_id)
      )
    : null;

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<SystemFormData>({
    defaultValues: {
      name: "",
      description: "",
      solution_type: "web_app",
      darckware_client_id: "",
      working_directory_path: "",
      github_repo_url: "",
      application_url: "",
      application_url_dev: "",
      status: "active",
      initial_version: "0.1.0",
      initial_version_status: "planned",
    },
  });

  const selectedClientId = watch("darckware_client_id");
  const workingDir = watch("working_directory_path");

  // Sync form values on load
  useEffect(() => {
    if (isEdit && (editingProject || associatedProduct)) {
      reset({
        name: editingProject?.name ?? associatedProduct?.name ?? "",
        description:
          editingProject?.description ?? associatedProduct?.description ?? "",
        solution_type:
          (editingProject?.solution_type as ProjectSolutionType) ?? "web_app",
        darckware_client_id:
          editingProject?.darckware_client_id ??
          associatedProduct?.darckware_client_id ??
          "",
        working_directory_path: editingProject?.working_directory_path ?? "",
        github_repo_url: editingProject?.github_repo_url ?? "",
        application_url: associatedProduct?.application_url ?? "",
        application_url_dev: associatedProduct?.application_url_dev ?? "",
        status: editingProject?.status ?? associatedProduct?.status ?? "active",
      });
    }
  }, [isEdit, editingProject, associatedProduct, reset]);

  const onSubmit = async (values: SystemFormData) => {
    setIsSubmitting(true);
    setErrorMessage(null);

    const selectedClient = clientList.find((c) => c.id === values.darckware_client_id);
    const clientName = selectedClient ? selectedClient.company_name : null;
    const clientId = values.darckware_client_id ? values.darckware_client_id : null;

    try {
      if (isEdit && editingProject) {
        // Mode 1: Edit existing Project & Product
        await updateAnyProject.mutateAsync({
          id: editingProject.id,
          payload: {
            name: values.name,
            description: values.description,
            solution_type: values.solution_type,
            status: values.status as any,
            working_directory_path: values.working_directory_path || undefined,
            github_repo_url: values.github_repo_url || undefined,
            darckware_client_id: clientId || undefined,
          },
        });

        if (associatedProduct) {
          await updateProduct.mutateAsync({
            id: associatedProduct.id,
            payload: {
              name: values.name,
              description: values.description,
              application_url: values.application_url || null,
              application_url_dev: values.application_url_dev || null,
              darckware_client_id: clientId,
              darckware_client_name: clientName,
            },
          });
        }
      } else {
        // Mode 2: Create new Product + initial Version + Project
        const newProduct = await createProduct.mutateAsync({
          name: values.name,
          description: values.description,
          status: "active",
          application_url: values.application_url || undefined,
          application_url_dev: values.application_url_dev || undefined,
          darckware_client_id: clientId || undefined,
          darckware_client_name: clientName || undefined,
          initial_version: values.initial_version
            ? {
                version: values.initial_version,
                status: (values.initial_version_status as any) || "planned",
              }
            : undefined,
        });

        const initialVersionId = newProduct.versions?.[0]?.id;
        if (initialVersionId) {
          await createProject.mutateAsync({
            name: values.name,
            description: values.description,
            product_version_id: initialVersionId,
            solution_type: values.solution_type,
            status: (values.status as any) ?? "active",
            working_directory_path: values.working_directory_path || undefined,
            github_repo_url: values.github_repo_url || undefined,
            backup_enabled: false,
            darckware_client_id: clientId || undefined,
          });
        }
      }

      await queryClient.invalidateQueries({ queryKey: ["cockpit"] });
      await queryClient.invalidateQueries({ queryKey: ["products"] });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });

      // Navigate back to Cockpit or previous page
      navigate("/cockpit");
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Falha ao salvar sistema.";
      setErrorMessage(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setIsSubmitting(false);
    }
  };

  const isLoadingData = isEdit && (isLoadingProducts || isLoadingProjects);

  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-12">
      {/* Top Header */}
      <PageHeader
        align="start"
        title={isEdit ? `Editar Sistema: ${editingProject?.name ?? associatedProduct?.name ?? ""}` : "Cadastrar Novo Sistema"}
        description={
          <p>
            {isEdit
              ? "Atualize as configurações de engenharia, ciclo de vida e vínculos comerciais deste sistema."
              : "Defina a identidade, arquitetura, diretório no host e cliente associado para o novo sistema na Software Factory."}
          </p>
        }
        actions={
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate(-1)}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Button>
        }
      />

      {isLoadingData ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {errorMessage && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
              <strong>Erro: </strong>
              {errorMessage}
            </div>
          )}

          {/* Seção 1: Identificação e Solução */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Layers className="h-4 w-4" />
                </div>
                <div>
                  <CardTitle className="text-base">Identificação & Tipo de Solução</CardTitle>
                  <CardDescription className="text-xs">
                    Defina o nome de identificação e a classificação técnica na esteira de desenvolvimento.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="name" className="text-xs font-semibold">
                    Nome do Sistema / Aplicação <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="name"
                    placeholder="Ex: SAEDAS Dashboard, CoreTI, Portal Financeiro"
                    {...register("name", { required: "Nome é obrigatório" })}
                  />
                  {errors.name && (
                    <p className="text-xs text-destructive">{errors.name.message}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="solution_type" className="text-xs font-semibold">
                    Tipo de Solução / Implementação
                  </Label>
                  <Select id="solution_type" {...register("solution_type")}>
                    {PROJECT_SOLUTION_TYPES.map((st) => (
                      <option key={st} value={st}>
                        {PROJECT_SOLUTION_TYPE_LABELS[st] ?? st}
                      </option>
                    ))}
                  </Select>
                  <p className="text-[11px] text-muted-foreground">
                    Classificação técnica (API, Banco de Dados, Aplicação Web, Automação, etc.).
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="description" className="text-xs font-semibold">
                  Descrição e Escopo
                </Label>
                <Textarea
                  id="description"
                  rows={3}
                  placeholder="Descreva o propósito, requisitos principais e valor de negócio entregue por esta solução..."
                  {...register("description")}
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="status" className="text-xs font-semibold">
                    Status do Ciclo de Vida
                  </Label>
                  <Select id="status" {...register("status")}>
                    {PROJECT_STATUSES.map((st) => (
                      <option key={st} value={st}>
                        {st === "active"
                          ? "Ativo (Em Execução)"
                          : st === "planned"
                          ? "Planejado"
                          : st === "on_hold"
                          ? "Em Espera (Pausado)"
                          : st === "completed"
                          ? "Concluído"
                          : "Cancelado"}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>

              {!isEdit && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="initial_version" className="text-xs font-semibold">
                      Versão Inicial
                    </Label>
                    <Input
                      id="initial_version"
                      placeholder="Ex: 0.1.0 ou 2026.11"
                      {...register("initial_version")}
                    />
                    <p className="text-[11px] text-muted-foreground">
                      Versão inicial criada no cadastro (ex: 2026.11 ou 0.1.0).
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="initial_version_status" className="text-xs font-semibold">
                      Estado da Versão
                    </Label>
                    <Select id="initial_version_status" {...register("initial_version_status")}>
                      <option value="planned">Planejada (planned)</option>
                      <option value="in_development">Em Desenvolvimento (in_development)</option>
                      <option value="in_test">Em Teste (in_test)</option>
                      <option value="published">Publicada (published)</option>
                      <option value="deprecated">Descontinuada (deprecated)</option>
                    </Select>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Seção 2: Vínculo Comercial / Cliente */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10 text-blue-500">
                  <Building2 className="h-4 w-4" />
                </div>
                <div>
                  <CardTitle className="text-base">Vínculo Comercial & Cliente</CardTitle>
                  <CardDescription className="text-xs">
                    Associe esta aplicação a uma empresa cliente da Darckware ou mantenha como Produto Próprio.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="darckware_client_id" className="text-xs font-semibold">
                  Cliente da Darckware (Opcional)
                </Label>
                <Select id="darckware_client_id" {...register("darckware_client_id")}>
                  <option value="">⚡ Produto Próprio Darckware (Sem cliente vinculado)</option>
                  {clientList.map((client) => (
                    <option key={client.id} value={client.id}>
                      🏢 {client.company_name}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="flex items-center gap-2 rounded-lg border bg-muted/40 p-3 text-xs text-muted-foreground">
                {selectedClientId ? (
                  <>
                    <Building2 className="h-4 w-4 text-blue-500 shrink-0" />
                    <span>
                      Este sistema está associado a uma conta cliente. Demandas abertas por esta empresa poderão ser encaminhadas para a esteira deste projeto.
                    </span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 text-purple-500 shrink-0" />
                    <span>
                      Este sistema é um <strong>Produto Próprio da Darckware</strong> (como o próprio ForgeHub, ForgeRouter ou novas ferramentas internas).
                    </span>
                  </>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Seção 3: Infraestrutura e Diretórios no Host */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500">
                  <Server className="h-4 w-4" />
                </div>
                <div>
                  <CardTitle className="text-base">Infraestrutura, Código & Ambientes</CardTitle>
                  <CardDescription className="text-xs">
                    Caminhos locais no host para que os agentes possam inspecionar, executar testes e fazer deploy.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="working_directory_path" className="text-xs font-semibold">
                  Diretório do Código no Host (Servidor)
                </Label>
                <div className="flex gap-2 items-center">
                  <Input
                    id="working_directory_path"
                    placeholder="/root/project/meu-sistema"
                    className="font-mono text-xs"
                    {...register("working_directory_path")}
                  />
                  <WorkingDirPicker
                    workingDir={workingDir || undefined}
                    onSelect={(path) => setValue("working_directory_path", path ?? "", { shouldDirty: true })}
                  />
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Selecione pelo navegador de pastas ou digite o caminho absoluto no servidor Linux.
                </p>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="github_repo_url" className="text-xs font-semibold">
                    Repositório Git / GitHub
                  </Label>
                  <Input
                    id="github_repo_url"
                    placeholder="https://github.com/darckware/..."
                    {...register("github_repo_url")}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="application_url_dev" className="text-xs font-semibold">
                    URL de Desenvolvimento / Staging
                  </Label>
                  <Input
                    id="application_url_dev"
                    placeholder="http://localhost:3000"
                    {...register("application_url_dev")}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="application_url" className="text-xs font-semibold">
                    URL de Produção
                  </Label>
                  <Input
                    id="application_url"
                    placeholder="https://app.darckware.net"
                    {...register("application_url")}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Barra de Ações */}
          <div className="flex items-center justify-between pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate(-1)}
              disabled={isSubmitting}
            >
              Cancelar
            </Button>

            <Button
              type="submit"
              disabled={isSubmitting}
              className="gap-2 min-w-[140px]"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Salvando...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4" />
                  {isEdit ? "Salvar Alterações" : "Cadastrar Sistema"}
                </>
              )}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
