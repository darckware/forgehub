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
