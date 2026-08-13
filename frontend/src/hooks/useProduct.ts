import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Product domain
 *
 * Tables (SPEC.md 4.1): products, product_modules, product_versions, releases.
 * Primary entity: Product, with nested ProductVersion[] (PRD.md 4 / 5.2).
 *
 * Backend contract: /api/v1/products (list/create/get/update/delete).
 */

export const productVersionSchema = z.object({
  id: z.string(),
  product_id: z.string(),
  version: z.string(), // semantic version, e.g. "0.1.0"
  status: z.enum(["planned", "in_development", "in_test", "published", "deprecated"]),
  release_notes: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type ProductVersion = z.infer<typeof productVersionSchema>;

export const RELEASE_STATUSES = ["draft", "ready", "released", "cancelled"] as const;

export const releaseSchema = z.object({
  id: z.string(),
  product_version_id: z.string(),
  name: z.string(),
  status: z.enum(RELEASE_STATUSES).default("draft"),
  notes: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type Release = z.infer<typeof releaseSchema>;

export const productSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  status: z.enum(["concept", "active", "inactive", "archived"]).default("active"),
  application_url: z.string().nullable().optional(),
  application_url_dev: z.string().nullable().optional(),
  versions: z.array(productVersionSchema).optional().default([]),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type Product = z.infer<typeof productSchema>;

/** Payload shape for create/update -- server assigns id and timestamps. */
export const productInputSchema = z.object({
  name: z.string().min(1, "Name is required").max(200),
  description: z.string().max(2000).optional().or(z.literal("")),
  status: z.enum(["active", "inactive", "archived"]).default("active"),
  // Uma URL por ambiente. `application_url` é a de producao (nome historico
  // mantido -- ver o comentario no modelo do backend); `application_url_dev` e
  // a de desenvolvimento.
  application_url: z.string().url("Enter a valid http(s) URL").optional().or(z.literal("")),
  application_url_dev: z.string().url("Enter a valid http(s) URL").optional().or(z.literal("")),
});

export type ProductInput = z.infer<typeof productInputSchema>;
export type ProductUpdateInput = Partial<
  Omit<ProductInput, "application_url" | "application_url_dev">
> & {
  application_url?: string | null;
  application_url_dev?: string | null;
};

const RESOURCE = "/api/v1/products";

export function useProducts() {
  return useQuery({
    queryKey: ["products"],
    queryFn: () => apiClient.get<Product[]>(RESOURCE),
  });
}

export function useProduct(id: string | undefined) {
  return useQuery({
    queryKey: ["products", id],
    queryFn: () => apiClient.get<Product>(`${RESOURCE}/${id}`),
    enabled: Boolean(id),
  });
}

export function useProductVersion(id: string | undefined) {
  return useQuery({
    queryKey: ["product-versions", id],
    queryFn: () => apiClient.get<ProductVersion>(`${RESOURCE}/versions/${id}`),
    enabled: Boolean(id),
  });
}

/** Versions for one product. NOTE: the plain `GET /api/v1/products` list
 * (useProducts) does NOT include nested `versions` -- only the single
 * `GET /api/v1/products/{id}` does. Use this hook (backed by the
 * dedicated `/products/{id}/versions` endpoint) whenever you need a
 * specific product's versions without fetching the whole product list
 * with versions attached. */
export function useProductVersions(productId: string | undefined) {
  return useQuery({
    queryKey: ["products", productId, "versions"],
    queryFn: () => apiClient.get<ProductVersion[]>(`${RESOURCE}/${productId}/versions`),
    enabled: Boolean(productId),
  });
}

export function useAllProductVersions() {
  return useQuery({
    queryKey: ["product-versions", "all"],
    queryFn: () => apiClient.get<ProductVersion[]>(`${RESOURCE}/versions`),
    staleTime: 60_000,
  });
}

export interface ProductVersionInput {
  version: string;
  status?: ProductVersion["status"];
  release_notes?: string;
}

export function useCreateProductVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, ...payload }: ProductVersionInput & { productId: string }) =>
      apiClient.post<ProductVersion>(`${RESOURCE}/${productId}/versions`, payload),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["products", variables.productId] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["product-versions"] });
    },
  });
}

export function useUpdateProductVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: Partial<ProductVersionInput> & { id: string }) =>
      apiClient.put<ProductVersion>(`${RESOURCE}/versions/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product-versions"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}

/** Pacote 4 (2026-08-01): dedicated publish action -- blocks (409 + the
 * list of unfinished tasks) instead of force-completing anything; see
 * publish_product_version in backend/app/api/routes/product.py. */
export function usePublishProductVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.post<ProductVersion>(`${RESOURCE}/versions/${id}:publish`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["product-versions"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}

const RELEASES_RESOURCE = `${RESOURCE}/releases`;

export function useReleases() {
  return useQuery({
    queryKey: ["releases"],
    queryFn: () => apiClient.get<Release[]>(RELEASES_RESOURCE),
  });
}

export interface ReleaseInput {
  product_version_id: string;
  name: string;
  status?: (typeof RELEASE_STATUSES)[number];
  notes?: string;
}

export function useCreateRelease() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReleaseInput) => apiClient.post<Release>(RELEASES_RESOURCE, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["releases"] }),
  });
}

export function useUpdateRelease() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...payload }: Partial<ReleaseInput> & { id: string }) =>
      apiClient.put<Release>(`${RELEASES_RESOURCE}/${id}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["releases"] }),
  });
}

export function useCreateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProductInput) => apiClient.post<Product>(RESOURCE, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}

export function useUpdateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ProductUpdateInput }) =>
      apiClient.put<Product>(`${RESOURCE}/${id}`, payload),
    onSuccess: (product) => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.setQueryData(["products", product.id], product);
    },
  });
}

export function useDeleteProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${RESOURCE}/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}
