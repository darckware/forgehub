import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Loader2, PackageSearch, Trash2, Pencil, Download, Upload, Database, FolderOpen } from "lucide-react";
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
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";
import {
  useProducts,
  useCreateProduct,
  useDeleteProduct,
  productInputSchema,
  type ProductInput,
  type Product,
} from "@/hooks/useProduct";
import { apiClient } from "@/lib/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";

const statusBadgeVariant: Record<string, "success" | "secondary" | "outline"> = {
  active: "success",
  inactive: "secondary",
  archived: "outline",
};

// ---------------------------------------------------------------------------
// Inline edit row
// ---------------------------------------------------------------------------
interface EditRowProps {
  product: Product;
  onClose: () => void;
}

function EditProductRow({ product, onClose }: EditRowProps) {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (payload: Partial<ProductInput>) =>
      apiClient.put<Product>(`/api/v1/products/${product.id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      onClose();
    },
  });

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<ProductInput>({
    resolver: zodResolver(productInputSchema),
    defaultValues: {
      name: product.name,
      description: product.description ?? "",
      status: (product.status as "active" | "inactive" | "archived") ?? "active",
    },
  });

  return (
    <TableRow className="bg-muted/30">
      <TableCell colSpan={4} className="py-3">
        <form onSubmit={handleSubmit((v) => update.mutate(v))} className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Name</Label>
              <Input className="h-8 text-sm" {...register("name")} />
              {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Description</Label>
              <Input className="h-8 text-sm" {...register("description")} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Status</Label>
              <Select className="h-8 text-sm" {...register("status")}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="archived">Archived</option>
              </Select>
            </div>
          </div>
          {update.isError && (
            <p className="text-xs text-destructive">Failed to save. Please try again.</p>
          )}
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={isSubmitting || update.isPending}>
              {(isSubmitting || update.isPending) && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
              Save
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      </TableCell>
    </TableRow>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Restore modal
// ---------------------------------------------------------------------------
interface RestoreModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (restoreDb: boolean, restoreFiles: boolean) => void;
  loading: boolean;
}

function RestoreModal({ open, onClose, onConfirm, loading }: RestoreModalProps) {
  const [restoreDb, setRestoreDb] = useState(true);
  const [restoreFiles, setRestoreFiles] = useState(true);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <div className="h-1 w-full rounded-t-xl bg-blue-500/80" />
        <div className="p-6 space-y-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-500/10">
              <Upload className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <h2 className="text-base font-semibold">Restore backup</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Select what will be restored from the ZIP file.
              </p>
            </div>
          </div>
          <div className="space-y-3">
            <label className="flex items-center gap-3 rounded-lg border border-border p-3 cursor-pointer hover:bg-accent/50">
              <input type="checkbox" checked={restoreDb} onChange={(e) => setRestoreDb(e.target.checked)} className="h-4 w-4" />
              <Database className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Database data</p>
                <p className="text-xs text-muted-foreground">Product, versions, projects, tasks, pipelines and planning items</p>
              </div>
            </label>
            <label className="flex items-center gap-3 rounded-lg border border-border p-3 cursor-pointer hover:bg-accent/50">
              <input type="checkbox" checked={restoreFiles} onChange={(e) => setRestoreFiles(e.target.checked)} className="h-4 w-4" />
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Project folder</p>
                <p className="text-xs text-muted-foreground">Files and folders from each project's working_directory_path</p>
              </div>
            </label>
          </div>
          <div className="flex justify-end gap-3 pt-1">
            <Button variant="outline" onClick={onClose} className="min-w-[88px]">Cancel</Button>
            <Button
              onClick={() => onConfirm(restoreDb, restoreFiles)}
              disabled={loading || (!restoreDb && !restoreFiles)}
              className="min-w-[88px]"
            >
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Restore
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function ProductPage() {
  const { data: products, isLoading, isError, error, refetch } = useProducts();
  const createProduct = useCreateProduct();
  const deleteProduct = useDeleteProduct();
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [backupLoading, setBackupLoading] = useState<string | null>(null);
  const [restoreModalOpen, setRestoreModalOpen] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [pendingRestoreFile, setPendingRestoreFile] = useState<File | null>(null);
  const restoreInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const pendingDeleteProduct = products?.find((p) => p.id === pendingDeleteId);

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<ProductInput>({
    resolver: zodResolver(productInputSchema),
    defaultValues: { name: "", description: "", status: "active" },
  });

  const onSubmit = async (values: ProductInput) => {
    await createProduct.mutateAsync(values);
    reset();
    setShowForm(false);
  };

  // --- Backup: call backend endpoint which returns a ZIP ---
  const handleBackup = async (product: Product) => {
    setBackupLoading(product.id);
    try {
      const BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;
      const resp = await fetch(`${BASE_URL}/api/v1/products/${product.id}/backup`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `product-backup-${product.name.replace(/\s+/g, "_").toLowerCase()}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Falha ao gerar backup.");
    } finally {
      setBackupLoading(null);
    }
  };

  // --- Restore: pick file → show modal → POST to backend ---
  const handleRestoreFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (restoreInputRef.current) restoreInputRef.current.value = "";
    if (!file) return;
    setPendingRestoreFile(file);
    setRestoreModalOpen(true);
  };

  const handleRestoreConfirm = async (restoreDb: boolean, restoreFiles: boolean) => {
    if (!pendingRestoreFile) return;
    setRestoreLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", pendingRestoreFile);
      const BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;
      const url = `${BASE_URL}/api/v1/products/restore?restore_db=${restoreDb}&restore_files=${restoreFiles}`;
      const resp = await fetch(url, { method: "POST", body: formData });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${resp.status}`);
      }
      queryClient.invalidateQueries({ queryKey: ["products"] });
      setRestoreModalOpen(false);
      setPendingRestoreFile(null);
      alert("Backup restaurado com sucesso.");
    } catch (err) {
      alert(`Falha ao restaurar: ${err instanceof Error ? err.message : "Erro desconhecido."}`);
    } finally {
      setRestoreLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Products</h1>
          <p className="text-muted-foreground">
            Products under continuous development, each with one or more versions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={restoreInputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={handleRestoreFileChange}
          />
          <Button
            variant="outline"
            onClick={() => restoreInputRef.current?.click()}
            title="Restaurar produto de um backup JSON"
          >
            <Upload className="mr-2 h-4 w-4" />
            Restore
          </Button>
          <Button onClick={() => setShowForm((v) => !v)}>
            <Plus className="mr-2 h-4 w-4" />
            New Product
          </Button>
        </div>
      </div>

      {showForm && (
        <Card>
          <form onSubmit={handleSubmit(onSubmit)}>
            <CardHeader>
              <CardTitle>Create Product</CardTitle>
              <CardDescription>Register a new product. Name must be unique.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input id="name" placeholder="e.g. ForgeHub" {...register("name")} />
                {errors.name && (
                  <p className="text-sm text-destructive">{errors.name.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  placeholder="Optional description of the product"
                  {...register("description")}
                />
                {errors.description && (
                  <p className="text-sm text-destructive">{errors.description.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="status">Status</Label>
                <Select id="status" {...register("status")}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="archived">Archived</option>
                </Select>
              </div>

              {createProduct.isError && (
                <p className="text-sm text-destructive">
                  Failed to create product. Please try again.
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
                onClick={() => { reset(); setShowForm(false); }}
              >
                Cancel
              </Button>
            </CardFooter>
          </form>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {isLoading && (
            <div className="flex items-center justify-center gap-2 p-10 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading products...
            </div>
          )}

          {isError && !isLoading && (
            <div className="flex flex-col items-center gap-3 p-10 text-center">
              <p className="text-sm text-destructive">
                {error instanceof Error ? error.message : "Failed to load products."}
              </p>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Retry
              </Button>
            </div>
          )}

          {!isLoading && !isError && (products?.length ?? 0) === 0 && (
            <div className="flex flex-col items-center gap-2 p-10 text-center text-muted-foreground">
              <PackageSearch className="h-10 w-10" />
              <p className="font-medium">No products yet</p>
              <p className="text-sm">Create your first product to get started.</p>
            </div>
          )}

          {!isLoading && !isError && (products?.length ?? 0) > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Versions</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {products?.map((product) => (
                  <>
                    <TableRow key={product.id}>
                      <TableCell>
                        <Link
                          to={`/product/${product.id}`}
                          className="font-medium text-foreground hover:underline"
                        >
                          {product.name}
                        </Link>
                        {product.description && (
                          <p className="line-clamp-1 text-sm text-muted-foreground">
                            {product.description}
                          </p>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={statusBadgeVariant[product.status] ?? "outline"}
                          className={cn("capitalize")}
                        >
                          {product.status}
                        </Badge>
                      </TableCell>
                      <TableCell>{product.versions?.length ?? 0}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Edit product"
                            onClick={() =>
                              setEditingId(editingId === product.id ? null : product.id)
                            }
                            className={cn(editingId === product.id && "bg-accent")}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Backup (export JSON)"
                            disabled={backupLoading === product.id}
                            onClick={() => handleBackup(product)}
                          >
                            {backupLoading === product.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Download className="h-4 w-4 text-blue-500" />
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Delete product"
                            disabled={deleteProduct.isPending}
                            onClick={() => setPendingDeleteId(product.id)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {editingId === product.id && (
                      <EditProductRow
                        key={`edit-${product.id}`}
                        product={product}
                        onClose={() => setEditingId(null)}
                      />
                    )}
                  </>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={`Delete "${pendingDeleteProduct?.name ?? "product"}"`}
        description="This action is irreversible. All projects, pipelines, planning items, tasks, executions, artifacts and governance records linked to this product will be cascade-deleted."
        confirmLabel="Delete all"
        onConfirm={() => {
          if (pendingDeleteId) deleteProduct.mutate(pendingDeleteId);
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
      <RestoreModal
        open={restoreModalOpen}
        onClose={() => { setRestoreModalOpen(false); setPendingRestoreFile(null); }}
        onConfirm={handleRestoreConfirm}
        loading={restoreLoading}
      />
    </div>
  );
}
