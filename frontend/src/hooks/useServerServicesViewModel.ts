/**
 * ViewModel for a server row's services panel (§21 of the org's
 * `05-FRONTEND-ARCHITECTURE-AND-CODING-STANDARD.md`, same shape as
 * `useServerKeyVaultViewModel.ts`).
 *
 * The panel juggles four things at once -- the list, an add/edit form, a port
 * scan whose findings feed that form, and a delete confirmation -- so `status`
 * names the step in flight instead of carrying a boolean per concern. The
 * component below it is close to a pure render of what this returns.
 */
import { useCallback, useMemo, useState } from "react";

import {
  useCreateServerService,
  useDeleteServerService,
  useScanServerPorts,
  useServerServices,
  useUpdateServerService,
  type ServerPortScanEntry,
  type ServerService,
  type ServerServiceInput,
} from "@/hooks/useServerServices";

export type ServerServicesStatus =
  | "idle"
  | "loading"
  | "editing"
  | "saving"
  | "scanning"
  | "confirming_delete"
  | "deleting"
  | "error";

export interface ServerServiceDraft {
  name: string;
  port: string;
  scheme: "http" | "https";
  path: string;
}

const EMPTY_DRAFT: ServerServiceDraft = { name: "", port: "", scheme: "http", path: "" };

export interface ServerServicesViewModel {
  status: ServerServicesStatus;
  services: ServerService[];
  isLoading: boolean;
  error: string | null;
  /** Non-null while the add/edit form is open; the id being edited, or "new". */
  editing: string | "new" | null;
  draft: ServerServiceDraft;
  setDraft: (patch: Partial<ServerServiceDraft>) => void;
  startCreate: () => void;
  startEdit: (service: ServerService) => void;
  cancelEdit: () => void;
  save: () => void;
  canSave: boolean;
  requestDelete: (service: ServerService) => void;
  cancelDelete: () => void;
  confirmDelete: () => void;
  deleteTarget: ServerService | null;
  scan: () => void;
  scanResult: ServerPortScanEntry[] | null;
  scannedCount: number | null;
  /** Pre-fills the form from a scan finding — the scan itself never writes. */
  adoptFinding: (entry: ServerPortScanEntry) => void;
}

export function useServerServicesViewModel(serverId: string): ServerServicesViewModel {
  const { data, isLoading, error: listError } = useServerServices(serverId);
  const createService = useCreateServerService(serverId);
  const updateService = useUpdateServerService(serverId);
  const deleteService = useDeleteServerService(serverId);
  const scanPorts = useScanServerPorts(serverId);

  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [draft, setDraftState] = useState<ServerServiceDraft>(EMPTY_DRAFT);
  const [deleteTarget, setDeleteTarget] = useState<ServerService | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setDraft = useCallback((patch: Partial<ServerServiceDraft>) => {
    setDraftState((prev) => ({ ...prev, ...patch }));
  }, []);

  const startCreate = useCallback(() => {
    setError(null);
    setDraftState(EMPTY_DRAFT);
    setEditing("new");
  }, []);

  const startEdit = useCallback((service: ServerService) => {
    setError(null);
    setDraftState({
      name: service.name,
      port: String(service.port),
      scheme: service.scheme,
      path: service.path ?? "",
    });
    setEditing(service.id);
  }, []);

  const cancelEdit = useCallback(() => {
    setEditing(null);
    setDraftState(EMPTY_DRAFT);
    setError(null);
  }, []);

  const port = Number(draft.port);
  const canSave = Boolean(draft.name.trim()) && Number.isInteger(port) && port >= 1 && port <= 65535;

  const save = useCallback(() => {
    if (!canSave || editing === null) return;
    const payload: ServerServiceInput = {
      name: draft.name.trim(),
      port: Number(draft.port),
      scheme: draft.scheme,
      path: draft.path.trim() || null,
    };
    const onSuccess = () => {
      setEditing(null);
      setDraftState(EMPTY_DRAFT);
      setError(null);
    };
    const onError = (err: Error) => setError(err.message);
    if (editing === "new") createService.mutate(payload, { onSuccess, onError });
    else updateService.mutate({ id: editing, data: payload }, { onSuccess, onError });
  }, [canSave, editing, draft, createService, updateService]);

  const requestDelete = useCallback((service: ServerService) => setDeleteTarget(service), []);
  const cancelDelete = useCallback(() => setDeleteTarget(null), []);

  const confirmDelete = useCallback(() => {
    if (!deleteTarget) return;
    deleteService.mutate(deleteTarget.id, {
      onSuccess: () => setDeleteTarget(null),
      onError: (err) => {
        setError(err.message);
        setDeleteTarget(null);
      },
    });
  }, [deleteTarget, deleteService]);

  const scan = useCallback(() => {
    setError(null);
    scanPorts.mutate(undefined, { onError: (err) => setError(err.message) });
  }, [scanPorts]);

  const adoptFinding = useCallback((entry: ServerPortScanEntry) => {
    setError(null);
    // Name is left blank on purpose: an open port says something is listening,
    // not what it is, so the one field a scan cannot answer is the one the
    // person has to fill in.
    setDraftState({ name: "", port: String(entry.port), scheme: entry.scheme, path: "" });
    setEditing("new");
  }, []);

  const status: ServerServicesStatus = useMemo(() => {
    if (createService.isPending || updateService.isPending) return "saving";
    if (deleteService.isPending) return "deleting";
    if (scanPorts.isPending) return "scanning";
    if (deleteTarget) return "confirming_delete";
    if (error || listError) return "error";
    if (isLoading) return "loading";
    if (editing !== null) return "editing";
    return "idle";
  }, [
    createService.isPending,
    updateService.isPending,
    deleteService.isPending,
    scanPorts.isPending,
    deleteTarget,
    error,
    listError,
    isLoading,
    editing,
  ]);

  return {
    status,
    services: data ?? [],
    isLoading,
    error: error ?? (listError ? listError.message : null),
    editing,
    draft,
    setDraft,
    startCreate,
    startEdit,
    cancelEdit,
    save,
    canSave,
    requestDelete,
    cancelDelete,
    confirmDelete,
    deleteTarget,
    scan,
    scanResult: scanPorts.data?.open_ports ?? null,
    scannedCount: scanPorts.data?.scanned ?? null,
    adoptFinding,
  };
}
