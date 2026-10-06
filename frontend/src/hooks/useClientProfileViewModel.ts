import { useState } from "react";
import {
  useClientOpsText,
  useCreateClient,
  useIssuePortalAccess,
  useUpdateClient,
  type ClientAccountInput,
  type ClientSummary,
  type PortalAccess,
} from "@/hooks/useClientOps";

/**
 * ViewModel Hook (§21) for registering a client from ForgeHub (2026-10-05,
 * Marcelo: "criar e atualizar os dados do cliente... fazer a troca de senha...
 * tudo pelo forgehub"). Three flows, each with its own step:
 *
 * - create / edit the client's data (form dialog);
 * - activate / deactivate (confirmation first);
 * - portal access: confirmation, then the temporary password shown **once**.
 *   It is not kept anywhere after `closeAccess` -- issuing again replaces it,
 *   which is also how a client who forgot the password gets back in.
 */
export type ClientProfileStatus = "idle" | "editing" | "confirming" | "submitting" | "issued" | "error";

export type ClientFormDialog = { mode: "create" } | { mode: "edit"; client: ClientSummary };
export type ClientConfirm = { kind: "portal" } | { kind: "activation"; active: boolean };

export function clientFormDefaults(client?: ClientSummary): ClientAccountInput {
  const primary = client?.contacts.find((c) => c.is_primary);
  return {
    company_name: client?.company_name ?? "",
    contact_name: client?.contact_name ?? "",
    email: client?.email ?? "",
    phone: primary?.phone ?? "",
    department: primary?.department ?? "",
  };
}

/** Portal state as the operator reads it: not released, released but unused, in use. */
export function portalState(client: ClientSummary): "notUsed" | "mustChange" | "active" {
  if (!client.last_login_at) return "notUsed";
  return client.must_change_password ? "mustChange" : "active";
}

export interface ClientProfileViewModel {
  status: ClientProfileStatus;
  dialog?: ClientFormDialog;
  confirm?: ClientConfirm;
  issued?: PortalAccess;
  errorMessage?: string;
  /** Set after a create, so the page can link to the new client. */
  createdId?: string;
  openCreate(): void;
  openEdit(client: ClientSummary): void;
  closeDialog(): void;
  submit(input: ClientAccountInput): Promise<void>;
  requestPortalAccess(): void;
  requestActivation(active: boolean): void;
  cancelConfirm(): void;
  confirmAction(): Promise<void>;
  closeAccess(): void;
  dismiss(): void;
}

export function useClientProfileViewModel(clientId?: string): ClientProfileViewModel {
  const { errorText } = useClientOpsText();
  const [dialog, setDialog] = useState<ClientFormDialog>();
  const [confirm, setConfirm] = useState<ClientConfirm>();
  const [issued, setIssued] = useState<PortalAccess>();
  const [errorMessage, setErrorMessage] = useState<string>();
  const [createdId, setCreatedId] = useState<string>();
  const create = useCreateClient();
  const update = useUpdateClient();
  const portal = useIssuePortalAccess();

  let status: ClientProfileStatus;
  if (create.isPending || update.isPending || portal.isPending) status = "submitting";
  else if (issued) status = "issued";
  else if (dialog) status = "editing";
  else if (confirm) status = "confirming";
  else if (errorMessage) status = "error";
  else status = "idle";

  return {
    status,
    dialog,
    confirm,
    issued,
    errorMessage,
    createdId,
    openCreate() {
      setErrorMessage(undefined);
      setCreatedId(undefined);
      setDialog({ mode: "create" });
    },
    openEdit(client) {
      setErrorMessage(undefined);
      setDialog({ mode: "edit", client });
    },
    closeDialog() {
      setDialog(undefined);
      setErrorMessage(undefined);
    },
    async submit(input) {
      if (!dialog) return;
      setErrorMessage(undefined);
      try {
        if (dialog.mode === "create") {
          const created = await create.mutateAsync(input);
          setCreatedId(created.id);
        } else {
          await update.mutateAsync({ id: dialog.client.id, changes: input });
        }
        setDialog(undefined);
      } catch (error) {
        setErrorMessage(errorText(error));
      }
    },
    requestPortalAccess() {
      setErrorMessage(undefined);
      setConfirm({ kind: "portal" });
    },
    requestActivation(active) {
      setErrorMessage(undefined);
      setConfirm({ kind: "activation", active });
    },
    cancelConfirm: () => setConfirm(undefined),
    async confirmAction() {
      if (!clientId || !confirm) return;
      try {
        if (confirm.kind === "portal") setIssued(await portal.mutateAsync({ id: clientId }));
        else await update.mutateAsync({ id: clientId, changes: { is_active: confirm.active } });
      } catch (error) {
        setErrorMessage(errorText(error));
      } finally {
        setConfirm(undefined);
      }
    },
    closeAccess: () => setIssued(undefined),
    dismiss: () => setErrorMessage(undefined),
  };
}
