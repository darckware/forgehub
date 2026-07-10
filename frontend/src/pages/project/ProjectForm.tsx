import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import {
  PROJECT_STATUSES,
  projectCreateSchema,
  type ProjectCreateInput,
} from "@/hooks/useProject";
import { useProducts, useProductVersion, useProductVersions } from "@/hooks/useProduct";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";

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
  submitLabel = "Create project",
}: ProjectFormProps) {
  const { data: products, isLoading: isLoadingProducts } = useProducts();
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ProjectCreateInput>({
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

  const productVersionId = watch("product_version_id");
  const [selectedProductId, setSelectedProductId] = useState("");

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

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="name">Name</Label>
        <Input id="name" placeholder="ForgeHub — Foundation MVP" {...register("name")} />
        {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          placeholder="Bounded initiative associated with a product version"
          {...register("description")}
        />
        {errors.description && (
          <p className="text-sm text-destructive">{errors.description.message}</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="product_id">Product</Label>
          <Select
            id="product_id"
            value={selectedProductId}
            disabled={isLoadingProducts}
            onChange={(e) => {
              setSelectedProductId(e.target.value);
              setValue("product_version_id", "");
            }}
          >
            <option value="">
              {isLoadingProducts ? "Loading products…" : "Select a product"}
            </option>
            {products?.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="product_version_id">Version</Label>
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
                ? "Select a product first"
                : isLoadingVersions
                  ? "Loading versions…"
                  : "Select a version"}
            </option>
            {versions?.map((version) => (
              <option key={version.id} value={version.id}>
                {version.version} ({version.status.replace(/_/g, " ")})
              </option>
            ))}
          </Select>
          {errors.product_version_id && (
            <p className="text-sm text-destructive">{errors.product_version_id.message}</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="status">Status</Label>
        <Select id="status" {...register("status")}>
          {PROJECT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.replace("_", " ")}
            </option>
          ))}
        </Select>
        {errors.status && <p className="text-sm text-destructive">{errors.status.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="working_directory_path">Working directory path</Label>
        <div className="flex items-center gap-2">
          <Input
            id="working_directory_path"
            placeholder="/root/project/forgehub"
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

      <div className="flex justify-end gap-2 pt-2">
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            Cancel
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
