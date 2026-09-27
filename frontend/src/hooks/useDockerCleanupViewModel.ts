import { useState } from "react";
import {
  useDockerPrune,
  useDockerUsage,
  type DockerPruneResult,
  type DockerUnusedImage,
  type DockerUsage,
  type DockerUsageType,
} from "@/hooks/useSystemControl";

/** ViewModel Hook (§21) for System Control's Docker card (2026-09-27,
 * Marcelo: "limpeza de cache do docker e de imagens que não estão sendo
 * utilizadas"). Every prune is a hard delete, so each goes through an
 * explicit `confirming` step naming what it will remove before `submitting`.
 */
export type DockerCleanupStatus = "loading" | "ready" | "confirming" | "submitting" | "success" | "error";

/** What a confirmation is about to prune. */
export type DockerPruneAction = "build_cache" | "unused_images" | "all";

export interface DockerCleanupViewModel {
  status: DockerCleanupStatus;
  usage?: DockerUsage;
  buildCache?: DockerUsageType;
  images?: DockerUsageType;
  unusedImages: DockerUnusedImage[];
  /** Build cache + images reclaimable, as Docker itself computes them --
   * summing the unused-image list would count shared layers once per image. */
  totalReclaimable: number;
  /** Root filesystem use, 0-100, or null when unknown. */
  diskPercent: number | null;
  refreshing: boolean;
  loadError?: string;
  pendingAction: DockerPruneAction | null;
  lastResult?: DockerPruneResult;
  errorMessage?: string;
  showImages: boolean;
  toggleImages(): void;
  refresh(): void;
  requestPrune(action: DockerPruneAction): void;
  cancelPrune(): void;
  confirmPrune(): Promise<void>;
}

export function useDockerCleanupViewModel(): DockerCleanupViewModel {
  const usageQuery = useDockerUsage();
  const prune = useDockerPrune();
  const [pendingAction, setPendingAction] = useState<DockerPruneAction | null>(null);
  const [lastResult, setLastResult] = useState<DockerPruneResult>();
  const [errorMessage, setErrorMessage] = useState<string>();
  const [showImages, setShowImages] = useState(false);

  const usage = usageQuery.data;
  const buildCache = usage?.types.find((t) => t.type === "Build Cache");
  const images = usage?.types.find((t) => t.type === "Images");
  const unusedImages = usage?.unused_images ?? [];
  const disk = usage?.disk;

  let status: DockerCleanupStatus;
  if (prune.isPending) status = "submitting";
  else if (pendingAction) status = "confirming";
  else if (errorMessage) status = "error";
  else if (lastResult) status = "success";
  else if (usageQuery.isLoading) status = "loading";
  else status = "ready";

  return {
    status,
    usage,
    buildCache,
    images,
    unusedImages,
    totalReclaimable: (buildCache?.reclaimable ?? 0) + (images?.reclaimable ?? 0),
    diskPercent: disk && disk.total > 0 ? Math.round((disk.used / disk.total) * 100) : null,
    refreshing: usageQuery.isFetching,
    loadError: usageQuery.isError ? (usageQuery.error as Error).message : undefined,
    pendingAction,
    lastResult,
    errorMessage,
    showImages,
    toggleImages: () => setShowImages((value) => !value),
    refresh: () => void usageQuery.refetch(),
    requestPrune(action) {
      setErrorMessage(undefined);
      setPendingAction(action);
    },
    cancelPrune: () => setPendingAction(null),
    async confirmPrune() {
      if (!pendingAction) return;
      try {
        const result = await prune.mutateAsync({
          build_cache: pendingAction !== "unused_images",
          unused_images: pendingAction !== "build_cache",
        });
        setLastResult(result);
        setErrorMessage(undefined);
      } catch (error) {
        setLastResult(undefined);
        setErrorMessage((error as Error).message);
      } finally {
        setPendingAction(null);
      }
    },
  };
}
