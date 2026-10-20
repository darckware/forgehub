import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { projectCreateSchema, type ProjectCreateInput } from "@/hooks/useProject";
import { useProducts, useProductVersion, useProductVersions } from "@/hooks/useProduct";

/** ViewModel Hook for ProjectForm.tsx -- Wave 5 of `docs/architecture/
 * FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` (2026-08-07, Marcelo: "faça o
 * item 5 — CRUD simples"). react-hook-form's own `useForm` already plays
 * Model/Controller for the raw field values and Zod validation; what this
 * hook adds is the coordination react-hook-form doesn't cover on its own:
 * the product -> product-version cascading select (`selectedProductId`
 * isn't a form field, `product_version_id` is), resolving which product
 * owns an already-set version when editing an existing project, and the
 * backup-location slug preview. The View renders this hook's fields and
 * owns no state of its own. */
export function useProjectFormViewModel(defaultValues?: Partial<ProjectCreateInput>) {
  const { data: products, isLoading: isLoadingProducts } = useProducts();
  const form = useForm<ProjectCreateInput>({
    resolver: zodResolver(projectCreateSchema),
    defaultValues: {
      name: "",
      description: "",
      product_version_id: "",
      status: "planned",
      working_directory_path: "",
      ...defaultValues,
    },
  });
  const { watch, setValue } = form;

  const productVersionId = watch("product_version_id");
  const [selectedProductId, setSelectedProductId] = useState("");
  const backupEnabled = watch("backup_enabled");
  const nameValue = watch("name");
  // Mirrors the backend's slug rule (_project_slug in
  // backend/app/api/routes/system_control.py) so this preview matches what
  // System Control actually resolves to when backup_location is empty.
  const slug = (nameValue || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const defaultBackupLocation = `/root/backup/${slug || "project-name"}`;

  // Resolve which product owns the current product_version_id -- needed
  // when editing an existing project, which only carries the version id,
  // not which product it belongs to. Fetched directly (GET
  // /products/versions/{id}) rather than searched for in `products`,
  // because the plain products LIST endpoint doesn't return nested
  // versions (only GET /products/{id} does).
  const { data: currentVersion } = useProductVersion(productVersionId || undefined);
  useEffect(() => {
    if (currentVersion && !selectedProductId) {
      setSelectedProductId(currentVersion.product_id);
    }
  }, [currentVersion, selectedProductId]);

  const { data: versions, isLoading: isLoadingVersions } = useProductVersions(
    selectedProductId || undefined
  );

  function handleProductChange(productId: string) {
    setSelectedProductId(productId);
    setValue("product_version_id", "");
  }

  return {
    ...form,
    products,
    isLoadingProducts,
    selectedProductId,
    handleProductChange,
    versions,
    isLoadingVersions,
    productVersionId,
    backupEnabled,
    defaultBackupLocation,
  };
}
