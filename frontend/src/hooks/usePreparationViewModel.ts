import { useMemo, useState } from "react";
import { useHostReadiness, usePrepareHost, type HostPreparation } from "@/hooks/useHostInventory";
import { useServers, type Server } from "@/hooks/useServers";

/** "Prepare station" (Machines tab): pick a station that isn't ready yet,
 * then either run the preparation over SSH as the client's administrator or
 * copy the script for RustDesk. idle -> submitting -> (copied script | execution).
 *
 * Installing ForgeHub's SSH login always needs one administrator login on the
 * machine (Marcelo, 2026-10-19): the account on record (only its password is
 * asked), or "another account", which opens login + password. Neither is
 * stored. Locking that account afterwards defaults on for a workstation and
 * off for a server -- a client server keeps its administrator. */
export interface PreparationViewModel {
  status: "idle" | "submitting" | "error" | "copy_ready";
  candidates: Server[];
  serverId: string;
  setServerId: (id: string) => void;
  selected: Server | null;
  mode: "ssh" | "copy";
  setMode: (mode: "ssh" | "copy") => void;
  /** The administrator login on record for the machine, if any. */
  registeredUser: string | null;
  account: "registered" | "other";
  setAccount: (value: "registered" | "other") => void;
  otherUser: string;
  setOtherUser: (value: string) => void;
  /** The login actually used: the one on record, or the one typed. */
  adminUser: string;
  adminPassword: string;
  setAdminPassword: (value: string) => void;
  disableAdmin: boolean;
  setDisableAdmin: (value: boolean) => void;
  canSubmit: boolean;
  submit: () => void;
  result: HostPreparation | null;
  error: string | null;
}

export function usePreparationViewModel(
  onExecution: (executionId: string) => void,
  initialServerId = "",
): PreparationViewModel {
  const { data: servers } = useServers();
  const readiness = useHostReadiness();
  const prepare = usePrepareHost();
  const [serverId, setServerIdState] = useState(initialServerId);
  const [mode, setMode] = useState<"ssh" | "copy">("ssh");
  const [accountChoice, setAccountChoice] = useState<"registered" | "other">("registered");
  const [otherUser, setOtherUser] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [disableAdminChoice, setDisableAdminChoice] = useState<boolean | null>(null);

  const notReady = useMemo(
    () => new Set((readiness.data?.entries ?? []).filter((e) => e.readiness !== "ready").map((e) => e.server_id)),
    [readiness.data],
  );
  // Stations first; any machine not Ready can be prepared.
  const candidates = useMemo(
    () => (servers ?? [])
      .filter((s) => s.os_family === "windows" || s.os_family === "linux")
      .filter((s) => notReady.has(s.id))
      .sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "workstation" ? -1 : 1)),
    [servers, notReady],
  );
  const selected = (servers ?? []).find((s) => s.id === serverId) ?? null;
  const registeredUser = selected?.admin_user && selected.admin_user.toLowerCase() !== "darckware" ? selected.admin_user : null;
  const account = registeredUser ? accountChoice : "other";
  const adminUser = (account === "registered" ? registeredUser ?? "" : otherUser).trim();
  const disableAdmin = disableAdminChoice ?? selected?.kind === "workstation";

  const status = prepare.isPending ? "submitting" : prepare.isError ? "error" : prepare.data?.script ? "copy_ready" : "idle";
  return {
    status,
    candidates,
    serverId,
    setServerId: (id) => {
      prepare.reset();
      setServerIdState(id);
      setAccountChoice("registered");
      setAdminPassword("");
      setDisableAdminChoice(null);
    },
    selected,
    mode,
    setMode: (m) => {
      prepare.reset();
      setMode(m);
    },
    registeredUser,
    account,
    setAccount: setAccountChoice,
    otherUser,
    setOtherUser,
    adminUser,
    adminPassword,
    setAdminPassword,
    disableAdmin,
    setDisableAdmin: setDisableAdminChoice,
    canSubmit: Boolean(selected) && (mode === "copy" || (adminUser.length > 0 && adminPassword.length > 0)),
    submit: () => {
      if (!selected) return;
      prepare.mutate(
        {
          serverId: selected.id,
          mode,
          admin_user: adminUser || null,
          admin_password: mode === "ssh" ? adminPassword : null,
          disable_admin: disableAdmin,
        },
        {
          onSuccess: (result) => {
            setAdminPassword("");
            if (result.execution_id) onExecution(result.execution_id);
          },
        },
      );
    },
    result: prepare.data ?? null,
    error: prepare.error?.message ?? null,
  };
}
