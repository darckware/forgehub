import { useMemo, useState } from "react";
import { useHostReadiness, usePrepareHost, type HostPreparation } from "@/hooks/useHostInventory";
import { useServers, type Server } from "@/hooks/useServers";

/** "Prepare station" (Machines tab): pick a station that isn't ready yet,
 * then either run the preparation over SSH as the client's administrator or
 * copy the script for RustDesk. idle -> submitting -> (copied script | execution). */
export interface PreparationViewModel {
  status: "idle" | "submitting" | "error" | "copy_ready";
  candidates: Server[];
  serverId: string;
  setServerId: (id: string) => void;
  selected: Server | null;
  mode: "ssh" | "copy";
  setMode: (mode: "ssh" | "copy") => void;
  adminUser: string;
  setAdminUser: (value: string) => void;
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
  const [adminUser, setAdminUser] = useState("administrador");
  const [adminPassword, setAdminPassword] = useState("");
  const [disableAdmin, setDisableAdmin] = useState(true);

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

  const status = prepare.isPending ? "submitting" : prepare.isError ? "error" : prepare.data?.script ? "copy_ready" : "idle";
  return {
    status,
    candidates,
    serverId,
    setServerId: (id) => {
      prepare.reset();
      setServerIdState(id);
      const machine = (servers ?? []).find((s) => s.id === id);
      if (machine?.admin_user && machine.admin_user !== "darckware") setAdminUser(machine.admin_user);
    },
    selected,
    mode,
    setMode: (m) => {
      prepare.reset();
      setMode(m);
    },
    adminUser,
    setAdminUser,
    adminPassword,
    setAdminPassword,
    disableAdmin,
    setDisableAdmin,
    canSubmit: Boolean(selected) && (mode === "copy" || (adminUser.trim().length > 0 && adminPassword.length > 0)),
    submit: () => {
      if (!selected) return;
      prepare.mutate(
        {
          serverId: selected.id,
          mode,
          admin_user: adminUser.trim() || null,
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
