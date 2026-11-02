import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { Loader2, Plus, Pencil, Building2, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";
import { useDarckwareClients } from "@/hooks/useClientOps";
import { useProducts, useCreateProduct, useUpdateProduct } from "@/hooks/useProduct";
import {
  useCreateProject,
  useUpdateAnyProject,
  type Project,
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
}

interface SystemProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editingProject?: Project | null;
  onSuccess?: () => void;
}

export function SystemProjectDialog({
  open,
  onOpenChange,
  editingProject,
  onSuccess,
}: SystemProjectDialogProps) {
  const { t } = useTranslation(["cockpit", "product", "project"]);
  const queryClient = useQueryClient();
  const { data: clientsData } = useDarckwareClients();
  const clientList = clientsData?.items ?? [];
  const { data: products } = useProducts();

  const createProduct = useCreateProduct();
  const updateProduct = useUpdateProduct();
  const createProject = useCreateProject();
  const updateAnyProject = useUpdateAnyProject();

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Find associated product if editing
  const associatedProduct = products?.find((prod) =>
    prod.versions?.some((v) => v.id === editingProject?.product_version_id)
  );

  const { register, handleSubmit, setValue, watch, reset, formState: { errors } } = useForm<SystemFormData>({
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
    },
  });

  const selectedClientId = watch("darckware_client_id");
  const workingDir = watch("working_directory_path");

  // Sync form values on open or editingProject change
  useEffect(() => {
    if (open) {
      setErrorMessage(null);
      if (editingProject) {
        reset({
          name: editingProject.name,
          description: editingProject.description ?? associatedProduct?.description ?? "",
          solution_type: (editingProject.solution_type as ProjectSolutionType) ?? "web_app",
          darckware_client_id: editingProject.darckware_client_id ?? associatedProduct?.darckware_client_id ?? "",
          working_directory_path: editingProject.working_directory_path ?? "",
          github_repo_url: editingProject.github_repo_url ?? "",
          application_url: associatedProduct?.application_url ?? "",
          application_url_dev: associatedProduct?.application_url_dev ?? "",
          status: editingProject.status ?? "active",
        });
      } else {
        reset({
          name: "",
          description: "",
          solution_type: "web_app",
          darckware_client_id: "",
          working_directory_path: "",
          github_repo_url: "",
          application_url: "",
          application_url_dev: "",
          status: "active",
        });
      }
    }
  }, [open, editingProject, associatedProduct, reset]);

  if (!open) return null;

  const onSubmit = async (values: SystemFormData) => {
    setIsSubmitting(true);
    setErrorMessage(null);

    const selectedClient = clientList.find((c) => c.id === values.darckware_client_id);
    const clientName = selectedClient ? selectedClient.company_name : null;
    const clientId = values.darckware_client_id ? values.darckware_client_id : null;

    try {
      if (editingProject) {
        // Mode 1: Edit existing Project
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

        // Also update associated Product if present
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

      // Invalidate queries so Cockpit and other views reflect immediately
      await queryClient.invalidateQueries({ queryKey: ["cockpit"] });
      await queryClient.invalidateQueries({ queryKey: ["products"] });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });

      onOpenChange(false);
      onSuccess?.();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Falha ao salvar sistema.";
      setErrorMessage(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" aria-modal="true">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => onOpenChange(false)} />
      <div className="relative z-10 my-auto w-full max-w-2xl rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150 p-6 space-y-4">
        <div className="flex items-start justify-between border-b pb-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold text-foreground">
              {editingProject ? (
                <>
                  <Pencil className="h-5 w-5 text-primary" />
                  Editar Sistema: {editingProject.name}
                </>
              ) : (
                <>
                  <Plus className="h-5 w-5 text-primary" />
                  Novo Sistema / Aplicação
                </>
              )}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {editingProject
                ? "Atualize as informações do sistema, tipo de solução técnica e vínculo com cliente Darckware."
                : "Cadastre uma nova solução (produto Darckware ou sistema de cliente) para ser orquestrada pela Software Factory."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {errorMessage && (
            <div className="rounded-md bg-destructive/15 p-3 text-xs text-destructive font-medium border border-destructive/20">
              {errorMessage}
            </div>
          )}

          {/* Nome do Sistema */}
          <div className="space-y-1.5">
            <Label htmlFor="name" className="text-xs font-semibold">
              Nome do Sistema / Aplicação <span className="text-destructive">*</span>
            </Label>
            <Input
              id="name"
              placeholder="ex: SAEDAS Platform, Automação Semug, Portal CoreTI"
              {...register("name", { required: "Nome é obrigatório" })}
            />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>

          {/* Tipo de Solução / Implementação Técnica */}
          <div className="space-y-1.5">
            <Label htmlFor="solution_type" className="text-xs font-semibold">
              Tipo de Solução / Implementação
            </Label>
            <Select id="solution_type" {...register("solution_type")}>
              {PROJECT_SOLUTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {PROJECT_SOLUTION_TYPE_LABELS[type]} ({type})
                </option>
              ))}
            </Select>
            <p className="text-[11px] text-muted-foreground">
              Define a natureza da entrega: aplicação web, automação, análise de banco de dados, APIs ou migrações.
            </p>
          </div>

          {/* Cliente Darckware (Opcional) */}
          <div className="space-y-1.5 rounded-lg border p-3 bg-muted/20">
            <div className="flex items-center justify-between">
              <Label htmlFor="darckware_client_id" className="text-xs font-semibold flex items-center gap-1.5">
                {selectedClientId ? (
                  <Building2 className="h-3.5 w-3.5 text-sky-500" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5 text-purple-500" />
                )}
                Associação com Cliente (Darckware)
              </Label>
              <span className="text-[10px] text-muted-foreground uppercase font-bold">Opcional</span>
            </div>
            <Select id="darckware_client_id" {...register("darckware_client_id")}>
              <option value="">⚡ Produto Próprio Darckware (Sem cliente vinculado)</option>
              {clientList.map((client) => (
                <option key={client.id} value={client.id}>
                  🏢 {client.company_name}
                </option>
              ))}
            </Select>
            <p className="text-[11px] text-muted-foreground">
              {selectedClientId
                ? "Este sistema faz parte do escopo de serviços contratados pelo cliente (franquia de manutenção, locação de produto ou implementação)."
                : "Produto interno desenvolvido e mantido como propriedade da Darckware."}
            </p>
          </div>

          {/* Descrição */}
          <div className="space-y-1.5">
            <Label htmlFor="description" className="text-xs font-semibold">
              Descrição / Escopo
            </Label>
            <Textarea
              id="description"
              rows={3}
              className="resize-none text-xs"
              placeholder="Descreva a finalidade, escopo funcional ou objetivos do sistema..."
              {...register("description")}
            />
          </div>

          {/* Diretório de Trabalho (working_directory_path) */}
          <div className="space-y-1.5">
            <Label htmlFor="working_directory_path" className="text-xs font-semibold">
              Diretório de Trabalho no Host
            </Label>
            <div className="flex items-center gap-2">
              <Input
                id="working_directory_path"
                placeholder="/root/project/nome-do-sistema"
                className="text-xs"
                {...register("working_directory_path")}
              />
              <WorkingDirPicker
                workingDir={workingDir || undefined}
                onSelect={(path) => setValue("working_directory_path", path ?? "")}
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              Onde o código-fonte reside. Usado para terminal de agentes e auditoria de arquivos.
            </p>
          </div>

          {/* URLs de Aplicação */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="application_url_dev" className="text-xs font-semibold">
                URL de Desenvolvimento
              </Label>
              <Input
                id="application_url_dev"
                type="url"
                placeholder="http://localhost:3000"
                className="text-xs"
                {...register("application_url_dev")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="application_url" className="text-xs font-semibold">
                URL de Produção
              </Label>
              <Input
                id="application_url"
                type="url"
                placeholder="https://app.darckware.com"
                className="text-xs"
                {...register("application_url")}
              />
            </div>
          </div>

          {/* Status */}
          <div className="space-y-1.5">
            <Label htmlFor="status" className="text-xs font-semibold">
              Status do Ciclo de Vida
            </Label>
            <Select id="status" {...register("status")}>
              {PROJECT_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {t(`project:enums.projectStatus.${status}`, status)}
                </option>
              ))}
            </Select>
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t">
            <Button
              type="button"
              variant="outline"
              disabled={isSubmitting}
              onClick={() => onOpenChange(false)}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {editingProject ? "Salvar Alterações" : "Criar Sistema"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
