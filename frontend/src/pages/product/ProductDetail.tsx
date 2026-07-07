import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, Loader2, Plus, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { useProduct } from "@/hooks/useProduct";
import { EntityDocsCard } from "@/components/EntityDocsCard";
import { apiClient } from "@/lib/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ProductVersion } from "@/hooks/useProduct";

const versionStatusBadge: Record<string, "success" | "secondary" | "outline" | "default"> = {
  planned: "outline",
  in_development: "secondary",
  in_test: "default",
  published: "success",
  deprecated: "outline",
};

const productVersionInputSchema = z.object({
  version: z
    .string()
    .min(1, "Version is required")
    .regex(/^\d+\.\d+\.\d+(-[\w.]+)?$/, "Use semantic versioning, e.g. 0.1.0"),
  status: z.enum(["planned", "in_development", "in_test", "published", "deprecated"]).default("planned"),
  release_notes: z.string().max(2000).optional().or(z.literal("")),
});

type ProductVersionInput = z.infer<typeof productVersionInputSchema>;

function useCreateProductVersion(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProductVersionInput) =>
      apiClient.post<ProductVersion>(`/api/v1/products/${productId}/versions`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products", productId] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}

export default function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: product, isLoading, isError, error, refetch } = useProduct(id);
  const createVersion = useCreateProductVersion(id ?? "");
  const [showForm, setShowForm] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProductVersionInput>({
    resolver: zodResolver(productVersionInputSchema),
    defaultValues: { version: "", status: "planned", release_notes: "" },
  });

  const onSubmit = async (values: ProductVersionInput) => {
    await createVersion.mutateAsync(values);
    reset();
    setShowForm(false);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading product...
      </div>
    );
  }

  if (isError || !product) {
    return (
      <div className="space-y-4">
        <Link to="/product" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:underline">
          <ArrowLeft className="h-4 w-4" />
          Back to products
        </Link>
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-10 text-center">
            <p className="text-sm text-destructive">
              {error instanceof Error ? error.message : "Failed to load product."}
            </p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link to="/product" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="h-4 w-4" />
        Back to products
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{product.name}</h1>
          {product.description && (
            <p className="mt-1 text-muted-foreground">{product.description}</p>
          )}
        </div>
        <Badge variant="outline" className="capitalize">
          {product.status}
        </Badge>
      </div>

      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold tracking-tight">Versions</h2>
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          New Version
        </Button>
      </div>

      {showForm && (
        <Card>
          <form onSubmit={handleSubmit(onSubmit)}>
            <CardHeader>
              <CardTitle>Create Product Version</CardTitle>
              <CardDescription>
                Register a new planned, in-development, in-test, or published version.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="version">Version</Label>
                <Input id="version" placeholder="e.g. 0.1.0" {...register("version")} />
                {errors.version && (
                  <p className="text-sm text-destructive">{errors.version.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="status">Status</Label>
                <Select id="status" {...register("status")}>
                  <option value="planned">Planned</option>
                  <option value="in_development">In Development</option>
                  <option value="in_test">In Test</option>
                  <option value="published">Published</option>
                  <option value="deprecated">Deprecated</option>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="release_notes">Release Notes</Label>
                <Textarea
                  id="release_notes"
                  placeholder="Optional release notes"
                  {...register("release_notes")}
                />
                {errors.release_notes && (
                  <p className="text-sm text-destructive">{errors.release_notes.message}</p>
                )}
              </div>

              {createVersion.isError && (
                <p className="text-sm text-destructive">
                  Failed to create version. Please try again.
                </p>
              )}
            </CardContent>
            <CardFooter className="gap-2">
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  reset();
                  setShowForm(false);
                }}
              >
                Cancel
              </Button>
            </CardFooter>
          </form>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {(product.versions?.length ?? 0) === 0 ? (
            <div className="flex flex-col items-center gap-2 p-10 text-center text-muted-foreground">
              <Tag className="h-10 w-10" />
              <p className="font-medium">No versions yet</p>
              <p className="text-sm">Create the first version for this product.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Version</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Release Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {product.versions?.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell className="font-medium">{v.version}</TableCell>
                    <TableCell>
                      <Badge variant={versionStatusBadge[v.status] ?? "outline"} className="capitalize">
                        {v.status.replace("_", " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-muted-foreground">
                      {v.release_notes ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <EntityDocsCard entityType="product" entityId={product?.id} />
    </div>
  );
}
