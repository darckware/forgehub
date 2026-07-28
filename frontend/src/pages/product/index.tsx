import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Plus, Loader2, PackageSearch, Trash2, Pencil, Download, Upload, Database, FolderOpen } from "lucide-react";
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
  type ProductUpdateInput,
  type Product,
} from "@/hooks/useProduct";
import { apiClient } from "@/lib/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";

const statusBadgeVariant: Record<string, "success" | "secondary" | "outline"> = {
  concept: "secondary",
  active: "success",
  inactive: "secondary",
  archived: "outline",
};

// ---------------------------------------------------------------------------
// Edit form (full-width card, not an inline table row -- long descriptions
// need real room to read/write, which a cramped expanded row can't give)
// ---------------------------------------------------------------------------
interface EditFormProps {
  product: Product;
  onClose: () => void;
}

function EditProductForm({ product, onClose }: EditFormProps) {
  const { t } = useTranslation("product");
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (payload: ProductUpdateInput) =>
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
      application_url: product.application_url ?? "",
      application_url_dev: product.application_url_dev ?? "",
    },
  });

  return (
    <Card>
      <form
        onSubmit={handleSubmit((v) =>
          update.mutate({
            ...v,
            // "" limpa a URL: o backend precisa de null, não de string vazia
            // (o pattern ^https?:// rejeitaria "").
            application_url: v.application_url || null,
            application_url_dev: v.application_url_dev || null,
          }),
        )}
      >
        <CardHeader>
          <CardTitle>{t("editRow.title")}</CardTitle>
          <CardDescription>{t("editRow.description", { name: product.name })}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="edit-name">{t("editRow.nameLabel")}</Label>
            <Input id="edit-name" {...register("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-description">{t("editRow.descriptionLabel")}</Label>
            <Textarea id="edit-description" rows={6} {...register("description")} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="edit-url-dev">{t("editRow.urlDevLabel")}</Label>
              <Input
                id="edit-url-dev"
                placeholder={t("editRow.urlDevPlaceholder")}
                {...register("application_url_dev")}
              />
              {errors.application_url_dev && (
                <p className="text-sm text-destructive">{errors.application_url_dev.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-url">{t("editRow.urlLabel")}</Label>
              <Input id="edit-url" placeholder={t("editRow.urlPlaceholder")} {...register("application_url")} />
              {errors.application_url && <p className="text-sm text-destructive">{errors.application_url.message}</p>}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-status">{t("editRow.statusLabel")}</Label>
            <Select id="edit-status" {...register("status")}>
              <option value="active">{t("list.status.active")}</option>
              <option value="inactive">{t("list.status.inactive")}</option>
              <option value="archived">{t("list.status.archived")}</option>
            </Select>
          </div>
          {update.isError && <p className="text-sm text-destructive">{t("editRow.error")}</p>}
        </CardContent>
        <CardFooter className="gap-2">
          <Button type="submit" disabled={isSubmitting || update.isPending}>
            {(isSubmitting || update.isPending) && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("editRow.save")}
          </Button>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("editRow.cancel")}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

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
  const { t } = useTranslation("product");
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
              <h2 className="text-base font-semibold">{t("restoreModal.title")}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {t("restoreModal.description")}
              </p>
            </div>
          </div>
          <div className="space-y-3">
            <label className="flex items-center gap-3 rounded-lg border border-border p-3 cursor-pointer hover:bg-accent/50">
              <input type="checkbox" checked={restoreDb} onChange={(e) => setRestoreDb(e.target.checked)} className="h-4 w-4" />
              <Database className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">{t("restoreModal.dbLabel")}</p>
                <p className="text-xs text-muted-foreground">{t("restoreModal.dbDescription")}</p>
              </div>
            </label>
            <label className="flex items-center gap-3 rounded-lg border border-border p-3 cursor-pointer hover:bg-accent/50">
              <input type="checkbox" checked={restoreFiles} onChange={(e) => setRestoreFiles(e.target.checked)} className="h-4 w-4" />
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">{t("restoreModal.filesLabel")}</p>
                <p className="text-xs text-muted-foreground">{t("restoreModal.filesDescription")}</p>
              </div>
            </label>
          </div>
          <div className="flex justify-end gap-3 pt-1">
            <Button variant="outline" onClick={onClose} className="min-w-[88px]">{t("restoreModal.cancel")}</Button>
            <Button
              onClick={() => onConfirm(restoreDb, restoreFiles)}
              disabled={loading || (!restoreDb && !restoreFiles)}
              className="min-w-[88px]"
            >
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {t("restoreModal.confirm")}
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
  const { t } = useTranslation("product");
  const { data: products, isLoading, isError, error, refetch } = useProducts();
  const createProduct = useCreateProduct();
  const deleteProduct = useDeleteProduct();
  const [view, setView] = useState<"list" | "form">("list");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [backupLoading, setBackupLoading] = useState<string | null>(null);
  const [restoreModalOpen, setRestoreModalOpen] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [pendingRestoreFile, setPendingRestoreFile] = useState<File | null>(null);
  const restoreInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const pendingDeleteProduct = products?.find((p) => p.id === pendingDeleteId);
  const editingProduct = products?.find((p) => p.id === editingId);

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<ProductInput>({
    resolver: zodResolver(productInputSchema),
    defaultValues: {
      name: "",
      description: "",
      status: "active",
      application_url: "",
      application_url_dev: "",
    },
  });

  const onSubmit = async (values: ProductInput) => {
    await createProduct.mutateAsync({
      ...values,
      application_url: values.application_url || undefined,
      application_url_dev: values.application_url_dev || undefined,
    });
    reset();
    setView("list");
  };

  const openCreateForm = () => {
    reset();
    setEditingId(null);
    setView("form");
  };

  const openEditForm = (id: string) => {
    setEditingId(id);
    setView("form");
  };

  const backToList = () => {
    setEditingId(null);
    setView("list");
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
      alert(t("list.alerts.backupFailed"));
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
      alert(t("list.alerts.restoreSuccess"));
    } catch (err) {
      alert(t("list.alerts.restoreFailed", { message: err instanceof Error ? err.message : t("list.alerts.unknownError") }));
    } finally {
      setRestoreLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("list.title")}</h1>
          <p className="text-muted-foreground">
            {t("list.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {view === "list" ? (
            <>
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
                title={t("list.restoreButtonTitle")}
              >
                <Upload className="mr-2 h-4 w-4" />
                {t("list.restoreButton")}
              </Button>
              <Button onClick={openCreateForm}>
                <Plus className="mr-2 h-4 w-4" />
                {t("list.newButton")}
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={backToList}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              {t("list.backToList")}
            </Button>
          )}
        </div>
      </div>

      {view === "form" ? (
        editingId && editingProduct ? (
          <EditProductForm product={editingProduct} onClose={backToList} />
        ) : (
          <Card>
            <form onSubmit={handleSubmit(onSubmit)}>
              <CardHeader>
                <CardTitle>{t("list.createForm.title")}</CardTitle>
                <CardDescription>{t("list.createForm.description")}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="name">{t("list.createForm.nameLabel")}</Label>
                  <Input id="name" placeholder={t("list.createForm.namePlaceholder")} {...register("name")} />
                  {errors.name && (
                    <p className="text-sm text-destructive">{errors.name.message}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="description">{t("list.createForm.descriptionLabel")}</Label>
                  <Textarea
                    id="description"
                    rows={6}
                    placeholder={t("list.createForm.descriptionPlaceholder")}
                    {...register("description")}
                  />
                  {errors.description && (
                    <p className="text-sm text-destructive">{errors.description.message}</p>
                  )}
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="application_url_dev">
                      {t("list.createForm.urlDevLabel")}
                    </Label>
                    <Input
                      id="application_url_dev"
                      type="url"
                      placeholder={t("list.createForm.urlDevPlaceholder")}
                      {...register("application_url_dev")}
                    />
                    {errors.application_url_dev && (
                      <p className="text-sm text-destructive">
                        {errors.application_url_dev.message}
                      </p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="application_url">{t("list.createForm.urlLabel")}</Label>
                    <Input
                      id="application_url"
                      type="url"
                      placeholder={t("list.createForm.urlPlaceholder")}
                      {...register("application_url")}
                    />
                    {errors.application_url && (
                      <p className="text-sm text-destructive">{errors.application_url.message}</p>
                    )}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">{t("list.createForm.urlHint")}</p>

                <div className="space-y-2">
                  <Label htmlFor="status">{t("list.createForm.statusLabel")}</Label>
                  <Select id="status" {...register("status")}>
                    <option value="active">{t("list.status.active")}</option>
                    <option value="inactive">{t("list.status.inactive")}</option>
                    <option value="archived">{t("list.status.archived")}</option>
                  </Select>
                </div>

                {createProduct.isError && (
                  <p className="text-sm text-destructive">
                    {t("list.createForm.error")}
                  </p>
                )}
              </CardContent>
              <CardFooter className="gap-2">
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t("list.createForm.save")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={backToList}
                >
                  {t("list.createForm.cancel")}
                </Button>
              </CardFooter>
            </form>
          </Card>
        )
      ) : (
        <Card>
          <CardContent className="p-0">
            {isLoading && (
              <div className="flex items-center justify-center gap-2 p-10 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                {t("list.loading")}
              </div>
            )}

            {isError && !isLoading && (
              <div className="flex flex-col items-center gap-3 p-10 text-center">
                <p className="text-sm text-destructive">
                  {error instanceof Error ? error.message : t("list.loadError")}
                </p>
                <Button variant="outline" size="sm" onClick={() => refetch()}>
                  {t("list.retry")}
                </Button>
              </div>
            )}

            {!isLoading && !isError && (products?.length ?? 0) === 0 && (
              <div className="flex flex-col items-center gap-2 p-10 text-center text-muted-foreground">
                <PackageSearch className="h-10 w-10" />
                <p className="font-medium">{t("list.emptyTitle")}</p>
                <p className="text-sm">{t("list.emptyDescription")}</p>
              </div>
            )}

            {!isLoading && !isError && (products?.length ?? 0) > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("list.columns.name")}</TableHead>
                    <TableHead>{t("list.columns.status")}</TableHead>
                    <TableHead>{t("list.columns.versions")}</TableHead>
                    <TableHead className="text-right">{t("list.columns.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {products?.map((product) => (
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
                        {(product.application_url_dev || product.application_url) && (
                          <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                            {product.application_url_dev && (
                              <a
                                href={product.application_url_dev}
                                target="_blank"
                                rel="noreferrer"
                                className="truncate hover:underline"
                                title={product.application_url_dev}
                              >
                                dev: {product.application_url_dev}
                              </a>
                            )}
                            {product.application_url && (
                              <a
                                href={product.application_url}
                                target="_blank"
                                rel="noreferrer"
                                className="truncate hover:underline"
                                title={product.application_url}
                              >
                                prod: {product.application_url}
                              </a>
                            )}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={statusBadgeVariant[product.status] ?? "outline"}
                          className={cn("capitalize")}
                        >
                          {t(`list.status.${product.status}`, { defaultValue: product.status })}
                        </Badge>
                      </TableCell>
                      <TableCell>{product.versions?.length ?? 0}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            title={t("list.actions.edit")}
                            disabled={product.status === "concept"}
                            onClick={() => openEditForm(product.id)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title={t("list.actions.backup")}
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
                            title={t("list.actions.delete")}
                            disabled={deleteProduct.isPending}
                            onClick={() => setPendingDeleteId(product.id)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={t("list.deleteDialog.title", { name: pendingDeleteProduct?.name ?? t("list.deleteDialog.defaultName") })}
        description={t("list.deleteDialog.description")}
        confirmLabel={t("list.deleteDialog.confirmLabel")}
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
