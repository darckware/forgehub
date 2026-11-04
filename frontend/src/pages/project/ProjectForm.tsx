import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import {
  PROJECT_STATUSES,
  PROJECT_SOLUTION_TYPES,
  PROJECT_SOLUTION_TYPE_LABELS,
  type ProjectCreateInput,
} from "@/hooks/useProject";
import { useDarckwareClients } from "@/hooks/useClientOps";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";
import { useProjectFormViewModel } from "@/hooks/useProjectFormViewModel";

interface ProjectFormProps {
  defaultValues?: Partial<ProjectCreateInput>;
  onSubmit: (values: ProjectCreateInput) => void;
  onCancel?: () => void;
  isSubmitting?: boolean;
  submitLabel?: string;
}

export function ProjectForm({
  defaultValues,
  onSubmit,
  onCancel,
  isSubmitting,
  submitLabel: submitLabelProp,
}: ProjectFormProps) {
  const { t } = useTranslation("project");
  const submitLabel = submitLabelProp ?? t("form.submitLabelDefault");
  const { data: clientsData } = useDarckwareClients();
  const clientList = clientsData?.items ?? [];
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
    products,
    serviceLines,
    isLoadingProducts,
    selectedProductId,
    handleProductChange,
    versions,
    isLoadingVersions,
    productVersionId,
    backupEnabled,
    defaultBackupLocation,
  } = useProjectFormViewModel(defaultValues);

  return (
    <form noValidate onSubmit={handleSubmit((values) => onSubmit({ ...values, service_line_id: values.service_line_id || undefined }))} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="name">{t("form.nameLabel")}</Label>
        <Input id="name" placeholder={t("form.namePlaceholder")} {...register("name")} />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">{t("form.descriptionLabel")}</Label>
        <Textarea className="resize-none"
          id="description"
          placeholder={t("form.descriptionPlaceholder")}
          {...register("description")}
        />
        {errors.description && (
          <p className="text-sm text-destructive">{errors.description.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="service_line_id">{t("form.serviceLine")}</Label>
        <Select id="service_line_id" {...register("service_line_id")}>
          <option value="">{t("form.defaultServiceLine")}</option>
          {serviceLines?.filter((line) => line.is_active).map((line) => <option key={line.id} value={line.id}>{line.name}</option>)}
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="product_id">{t("form.productLabel")}</Label>
          <Select
            id="product_id"
            value={selectedProductId}
            disabled={isLoadingProducts}
            onChange={(e) => handleProductChange(e.target.value)}
          >
            <option value="">
              {isLoadingProducts ? t("form.loadingProducts") : t("form.selectProduct")}
            </option>
            {products?.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="product_version_id">{t("form.versionLabel")}</Label>
          <Select
            id="product_version_id"
            disabled={!selectedProductId}
            // Controlled (not register()'d) -- the version list only
            // populates once `products` loads and the owning product is
            // resolved (see the effect above), which happens after the
            // select's first render when editing an existing project. An
            // uncontrolled <select {...register(...)}> never re-syncs its
            // DOM value once those options show up later, so it would be
            // stuck showing the placeholder even though product_version_id
            // is already set correctly in form state.
            value={productVersionId ?? ""}
            onChange={(e) => setValue("product_version_id", e.target.value)}
          >
            <option value="">
              {!selectedProductId
                ? t("form.selectProductFirst")
                : isLoadingVersions
                  ? t("form.loadingVersions")
                  : t("form.selectVersion")}
            </option>
            {versions?.map((version) => (
              <option key={version.id} value={version.id}>
                {version.version} ({t(`enums.productVersionStatus.${version.status}`, version.status)})
              </option>
            ))}
          </Select>
          {errors.product_version_id && (
            <p className="text-sm text-destructive">{errors.product_version_id.message}</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="solution_type">Tipo de Solução / Implementação</Label>
          <Select id="solution_type" {...register("solution_type")}>
            {PROJECT_SOLUTION_TYPES.map((type) => (
              <option key={type} value={type}>
                {PROJECT_SOLUTION_TYPE_LABELS[type]}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="darckware_client_id">Cliente Associado (Darckware)</Label>
          <Select id="darckware_client_id" {...register("darckware_client_id")}>
            <option value="">⚡ Produto Próprio Darckware</option>
            {clientList.map((client) => (
              <option key={client.id} value={client.id}>
                🏢 {client.company_name}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="status">{t("form.statusLabel")}</Label>
        <Select id="status" {...register("status")}>
          {PROJECT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {t(`enums.projectStatus.${status}`, status)}
            </option>
          ))}
        </Select>
        {errors.status && <p className="text-sm text-destructive">{errors.status.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="working_directory_path">{t("form.workingDirectoryLabel")}</Label>
        <div className="flex items-center gap-2">
          <Input
            id="working_directory_path"
            placeholder={t("form.workingDirectoryPlaceholder")}
            {...register("working_directory_path")}
          />
          <WorkingDirPicker
            workingDir={watch("working_directory_path") || undefined}
            onSelect={(path) => setValue("working_directory_path", path ?? "")}
          />
        </div>
        {errors.working_directory_path && (
          <p className="text-sm text-destructive">{errors.working_directory_path.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="github_repo_url">{t("form.githubUrlLabel")}</Label>
        <Input
          id="github_repo_url"
          placeholder={t("form.githubUrlPlaceholder")}
          {...register("github_repo_url")}
        />
        {errors.github_repo_url && (
          <p className="text-sm text-destructive">{errors.github_repo_url.message}</p>
        )}
        <p className="text-xs text-muted-foreground">{t("form.githubUrlHelp")}</p>
      </div>

      <div className="flex items-center gap-2">
        <input
          id="backup_enabled"
          type="checkbox"
          className="h-4 w-4 rounded border-input"
          {...register("backup_enabled")}
        />
        <Label htmlFor="backup_enabled" className="cursor-pointer">
          {t("form.backupEnabledLabel")}
        </Label>
      </div>

      {backupEnabled && (
        <div className="space-y-2">
          <Label htmlFor="backup_location">{t("form.backupLocationLabel")}</Label>
          <Input id="backup_location" placeholder={defaultBackupLocation} {...register("backup_location")} />
          {errors.backup_location && (
            <p className="text-sm text-destructive">{errors.backup_location.message}</p>
          )}
          <p className="text-xs text-muted-foreground">
            {t("form.backupLocationHelp", { location: defaultBackupLocation })}
          </p>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {t("shared.cancel")}
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
