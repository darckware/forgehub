import { useMemo, useState } from "react";
import { useBackupFiles, useDeleteBackupFiles, type BackupFileGroup, type BackupFiles } from "@/hooks/useSystemControl";

/** ViewModel Hook (§21) for System Control's Backups card (2026-09-28, Marcelo: "limpar todos
 * os arquivos de backup no sistema ... adicione na nossa tela de limpeza"). Selection plus an
 * explicit confirm step: removal moves items to the trash, and the card says so. */
export type BackupFilesStatus = "loading" | "ready" | "confirming" | "submitting" | "success" | "error";

export interface BackupFilesViewModel {
  status: BackupFilesStatus;
  data?: BackupFiles;
  groups: BackupFileGroup[];
  loadError?: string;
  refreshing: boolean;
  selected: Set<string>;
  selectedSize: number;
  expanded: Set<string>;
  lastResult?: { count: number; total_size: number; trash_path: string };
  errorMessage?: string;
  toggleItem(path: string): void;
  toggleGroup(group: BackupFileGroup): void;
  isGroupSelected(group: BackupFileGroup): boolean;
  toggleExpanded(group: string): void;
  refresh(): void;
  requestDelete(): void;
  cancelDelete(): void;
  confirmDelete(): Promise<void>;
}

export function useBackupFilesViewModel(): BackupFilesViewModel {
  const query = useBackupFiles();
  const remove = useDeleteBackupFiles();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [lastResult, setLastResult] = useState<BackupFilesViewModel["lastResult"]>();
  const [errorMessage, setErrorMessage] = useState<string>();

  const groups = query.data?.groups ?? [];
  const sizeByPath = useMemo(() => {
    const map = new Map<string, number>();
    for (const group of groups) for (const item of group.items) map.set(item.path, item.size);
    return map;
  }, [groups]);
  const selectedSize = [...selected].reduce((sum, path) => sum + (sizeByPath.get(path) ?? 0), 0);
  const removable = (group: BackupFileGroup) => group.items.filter((item) => !item.protected).map((item) => item.path);

  let status: BackupFilesStatus;
  if (remove.isPending) status = "submitting";
  else if (confirming) status = "confirming";
  else if (errorMessage) status = "error";
  else if (lastResult) status = "success";
  else if (query.isLoading) status = "loading";
  else status = "ready";

  return {
    status,
    data: query.data,
    groups,
    loadError: query.isError ? (query.error as Error).message : undefined,
    refreshing: query.isFetching,
    selected,
    selectedSize,
    expanded,
    lastResult,
    errorMessage,
    toggleItem(path) {
      setSelected((current) => {
        const next = new Set(current);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        return next;
      });
    },
    isGroupSelected(group) {
      const paths = removable(group);
      return paths.length > 0 && paths.every((path) => selected.has(path));
    },
    toggleGroup(group) {
      const paths = removable(group);
      setSelected((current) => {
        const next = new Set(current);
        const all = paths.every((path) => next.has(path));
        for (const path of paths) {
          if (all) next.delete(path);
          else next.add(path);
        }
        return next;
      });
    },
    toggleExpanded(group) {
      setExpanded((current) => {
        const next = new Set(current);
        if (next.has(group)) next.delete(group);
        else next.add(group);
        return next;
      });
    },
    refresh: () => void query.refetch(),
    requestDelete() {
      if (selected.size === 0) return;
      setErrorMessage(undefined);
      setConfirming(true);
    },
    cancelDelete: () => setConfirming(false),
    async confirmDelete() {
      try {
        const result = await remove.mutateAsync([...selected]);
        setLastResult(result);
        setSelected(new Set());
        setErrorMessage(undefined);
      } catch (error) {
        setLastResult(undefined);
        setErrorMessage((error as Error).message);
      } finally {
        setConfirming(false);
      }
    },
  };
}
