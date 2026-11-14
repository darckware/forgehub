import { useMemo, useState } from "react";
import { apiErrorText } from "@/lib/apiErrorText";
import { usePrepareHost, useValidatePreparation, useRecoverPreparation, type HostPreparation } from "@/hooks/useHostInventory";
import { serverFormSchema, useServers, type Server } from "@/hooks/useServers";

/** Configure machine access: select any supported enabled machine,
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
  pending: boolean;
  validated: boolean;
  validating: boolean;
  validationDetail: string | null;
  validationFailed: boolean;
  validate: () => void;
  recover: () => void;
  canUseStoredPassword: boolean;
  useStoredPassword: boolean;
  setUseStoredPassword: (value: boolean) => void;
  selfBootstrap: boolean;
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
  sshPort: string;
  setSshPort: (value: string) => void;
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
  const validation = useValidatePreparation();
  const recovery = useRecoverPreparation();
  const prepare = usePrepareHost();
  const [serverId, setServerIdState] = useState(initialServerId);
  const [mode, setMode] = useState<"ssh" | "copy">("ssh");
  const [accountChoice, setAccountChoice] = useState<"registered" | "other">("registered");
  const [otherUser, setOtherUser] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [action, setAction] = useState<"prepare" | "validate" | "recover">("prepare");
  const [storedPasswordChoice, setStoredPasswordChoice] = useState(false);
  const [sshPortChoice, setSshPort] = useState<string | null>(null);
  const [disableAdminChoice, setDisableAdminChoice] = useState<boolean | null>(null);

  // Reconfiguration is available even when the old SSH login responds.
  const candidates = useMemo(
    () => (servers ?? [])
      .filter((s) => s.access_enabled !== false && (s.os_family === "windows" || s.os_family === "linux"))
      .sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "workstation" ? -1 : 1)),
    [servers],
  );
  const selected = (servers ?? []).find((s) => s.id === serverId) ?? null;
  const registeredUser = selected?.remote_user === "darckware" ? "darckware" : selected?.admin_user || selected?.remote_user || null;
  const account = registeredUser ? accountChoice : "other";
  const adminUser = (account === "registered" ? registeredUser ?? "" : otherUser).trim();
  const selfBootstrap = adminUser.toLowerCase() === "darckware";
  const disableAdmin = selfBootstrap ? false : disableAdminChoice ?? selected?.kind === "workstation";
  const canUseStoredPassword = Boolean(selfBootstrap && selected?.remote_user === "darckware" && selected?.login_password_in_vault);
  const useStoredPassword = canUseStoredPassword && storedPasswordChoice;
  const result = recovery.data ?? prepare.data ?? null;
  const pending = Boolean(selected?.preparation_pending || result?.script);
  const validated = validation.data?.ok === true;
  const validationDetail = validation.data?.ok === false ? validation.data.detail ?? null : null;
  const sshPort = sshPortChoice ?? String(selected?.ssh_port ?? 22);
  const validPort = serverFormSchema.shape.ssh_port.safeParse(Number(sshPort)).success;

  const status = prepare.isPending || recovery.isPending ? "submitting" : prepare.isError || recovery.isError ? "error" : result?.script ? "copy_ready" : "idle";
  return {
    status,
    pending,
    validated,
    validationDetail,
    validationFailed: validation.data?.ok === false,
    validating: validation.isPending,
    validate: () => {
      if (selected && !validation.isPending && !recovery.isPending) {
        setAction("validate");
        validation.mutate(selected.id);
      }
    },
    recover: () => {
      if (selected && !recovery.isPending && !validation.isPending) {
        setAction("recover");
        validation.reset();
        recovery.mutate(selected.id);
      }
    },
    canUseStoredPassword,
    useStoredPassword,
    setUseStoredPassword: (useStored) => {
      setStoredPasswordChoice(useStored);
      setAdminPassword("");
    },
    selfBootstrap,
    candidates,
    serverId,
    setServerId: (id) => {
      prepare.reset();
      validation.reset();
      recovery.reset();
      setStoredPasswordChoice(false);
      setOtherUser("");
      setServerIdState(id);
      setAccountChoice("registered");
      setAdminPassword("");
      setDisableAdminChoice(null);
      setSshPort(null);
    },
    selected,
    mode,
    setMode: (m) => {
      prepare.reset();
      validation.reset();
      recovery.reset();
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
    sshPort,
    setSshPort,
    disableAdmin,
    setDisableAdmin: setDisableAdminChoice,
    canSubmit: !pending && !validated && candidates.some((m) => m.id === selected?.id) && !validation.isPending && (mode === "copy" || (validPort && adminUser.length > 0 && (useStoredPassword || adminPassword.length > 0))),
    submit: () => {
      if (!selected || prepare.isPending || (mode === "ssh" && !validPort)) return;
      setAction("prepare");
      validation.reset();
      prepare.mutate(
        {
          serverId: selected.id,
          ...(mode === "ssh" ? { ssh_port: Number(sshPort) } : {}),
          mode,
          admin_user: adminUser || null,
          admin_password: mode === "ssh" && !useStoredPassword ? adminPassword : null,
          ...(useStoredPassword && mode === "ssh" ? { use_stored_password: true } : {}),
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
    result,
    error: { prepare, validate: validation, recover: recovery }[action].error ? apiErrorText({ prepare, validate: validation, recover: recovery }[action].error) : null,
  };
}
