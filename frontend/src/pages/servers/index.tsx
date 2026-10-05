import { Fragment, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  Power,
  PowerOff,
  RefreshCw,
  Server as ServerIcon,
  SquareTerminal,
  Trash2,
  Upload,
  Wifi,
  WifiOff,
  X,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import {
  useServers,
  useDeleteServer,
  useImportServers,
  useServerStatusProbe,
  useInstallServerKey,
  useToggleServerAccess,
  buildSshCommand,
  type Server,
  type ServerCheckResult,
} from "@/hooks/useServers";
import { serverHome } from "@/pages/workspace/workspaceState";
import { ServerForm } from "./ServerForm";
import { ServerServicesPanel } from "./ServerServicesPanel";

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 my-auto w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{title}</h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** One-shot dedicated-key installation: asks for the server credential,
 * then the host bridge generates the ed25519 pair (idempotent), pushes the
 * .pub via ssh-copy-id and verifies BatchMode auth. Mirrors the manual
 * procedure in /root/.hermes/scripts/configure_ssh.sh, parameterized. */
function InstallKeyModal({ server, onClose, onInstalled }: { server: Server; onClose: () => void; onInstalled: () => void }) {
  const { t } = useTranslation("servers");
  // The account to log in with (and create, in admin mode) is the server
  // record's own remote_user -- not re-typed here.
  const remoteUser = server.remote_user;
  const [adminUser, setAdminUser] = useState("root");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  // Admin mode (default): log in with the server admin account, create the
  // registered user if needed, install the key. Off = classic ssh-copy-id as
  // the registered user itself (must already exist on the server).
  const [useAdmin, setUseAdmin] = useState(true);
  const installKey = useInstallServerKey();
  const result = installKey.data ?? null;
  const done = result?.ok === true;
  const canSubmit = Boolean(password && (!useAdmin || adminUser.trim()));

  function handleInstall() {
    if (installKey.isPending || !canSubmit) return;
    installKey.mutate(
      {
        id: server.id,
        password,
        admin_user: useAdmin ? adminUser.trim() : null,
      },
      { onSuccess: (res) => { if (res.ok) onInstalled(); } }
    );
  }

  return (
    <ModalShell title={t("install.title", { name: server.name })} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-xs text-muted-foreground">
          {t("install.description", { ip: server.ip_address })}
        </p>

        {!done && (
          <>
            <div className="rounded-md border border-border bg-muted/30 p-3">
              <label className="flex cursor-pointer items-start gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={useAdmin}
                  onChange={(e) => setUseAdmin(e.target.checked)}
                  disabled={installKey.isPending}
                  className="mt-0.5"
                />
                <span>
                  {t("install.adminDescription", { user: remoteUser })}
                </span>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>{useAdmin ? t("install.registeredUserCreate") : t("install.registeredUser")}</Label>
                <Input value={remoteUser} disabled readOnly className="font-mono" />
              </div>
              {useAdmin && (
                <div className="space-y-1">
                  <Label>{t("install.adminAccount")}</Label>
                  <Input value={adminUser} onChange={(e) => setAdminUser(e.target.value)} placeholder="root" disabled={installKey.isPending} />
                </div>
              )}
              <div className={useAdmin ? "col-span-2 space-y-1" : "space-y-1"}>
                <Label>{t("install.passwordFor", { user: useAdmin ? (adminUser || "admin") : remoteUser })}</Label>
                <div className="relative">
                  <Input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleInstall(); }}
                    className="pr-9"
                    autoFocus
                    disabled={installKey.isPending}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((s) => !s)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    tabIndex={-1}
                    title={showPassword ? t("install.hidePassword") : t("install.showPassword")}
                    aria-label={showPassword ? t("install.hidePassword") : t("install.showPassword")}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}

        {installKey.isPending && (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> {t("install.installing")}
          </p>
        )}

        {result && (
          <div className="space-y-2 rounded-md border border-border bg-muted/40 p-3 text-xs">
            {result.steps.map((step, i) => (
              <p key={i} className="flex items-start gap-1.5 text-muted-foreground">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" /> {step}
              </p>
            ))}
            {!result.ok && (
              <p className="flex items-start gap-1.5 text-destructive">
                <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {t("install.failedAt", { step: result.failed_step, error: result.error })}
              </p>
            )}
            {result.ok && result.public_key && (
              <div className="space-y-1 pt-1">
                <Label className="text-[11px]">{t("install.installedPublicKey")}</Label>
                <Textarea readOnly value={result.public_key} className="resize-none min-h-[64px] font-mono text-[10px]" />
              </div>
            )}
          </div>
        )}
        {installKey.isError && (
          <p className="text-xs text-destructive">{installKey.error.message}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>{done ? t("page.close") : t("form.cancel")}</Button>
          {!done && (
            <Button size="sm" onClick={handleInstall} disabled={installKey.isPending || !canSubmit}>
              {installKey.isPending ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <KeyRound className="mr-1.5 h-3.5 w-3.5" />}
              {t("install.action")}
            </Button>
          )}
        </div>
      </div>
    </ModalShell>
  );
}

/** Renders the live SSH probe result: online (key auth ok), offline
 * (unreachable or key rejected), no_key (no ssh_key_path configured), or
 * "checking"/unknown while a probe is in flight or hasn't run yet. */
function StatusBadge({ result, checking }: { result: ServerCheckResult | undefined; checking: boolean }) {
  const { t } = useTranslation("servers");
  if (checking) {
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> {t("status.checking")}
      </Badge>
    );
  }
  if (!result) {
    return <span className="text-xs italic text-muted-foreground/60">{t("status.notChecked")}</span>;
  }
  if (result.status === "disabled") {
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground" title={result.detail}>
        <PowerOff className="h-3 w-3" /> {t("status.off")}
      </Badge>
    );
  }
  if (result.status === "online") {
    return (
      <Badge variant="outline" className="gap-1 text-emerald-600 border-emerald-500/30" title={result.detail}>
        <Wifi className="h-3 w-3" /> {t("status.online")}
      </Badge>
    );
  }
  if (result.status === "no_key") {
    return (
      <Badge variant="outline" className="gap-1 text-amber-600 border-amber-500/30" title={result.detail}>
        <KeyRound className="h-3 w-3" /> {t("status.noKey")}
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 text-red-600 border-red-500/30" title={result.detail}>
      <WifiOff className="h-3 w-3" /> {t("status.offline")}
    </Badge>
  );
}

const CSV_PLACEHOLDER = `SERVER_NAME,SERVER_IP,REMOTE_USER,DESCRIPTION
srv-app01,172.15.2.2,aegis,"Main application server"`;

function ImportCsvModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("servers");
  const [csvText, setCsvText] = useState("");
  const [result, setResult] = useState<{ created: number; updated: number; errors: string[] } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importServers = useImportServers();

  function handlePickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setCsvText(String(reader.result ?? ""));
    reader.readAsText(file);
  }

  function handleImport() {
    if (!csvText.trim()) return;
    importServers.mutate(csvText, { onSuccess: (res) => setResult(res) });
  }

  return (
    <ModalShell title={t("import.title")} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">
          {t("import.description")}
        </p>
        <Textarea
          value={csvText}
          onChange={(e) => setCsvText(e.target.value)}
          placeholder={CSV_PLACEHOLDER}
          className="resize-none min-h-[180px] font-mono text-xs"
        />
        <div className="flex items-center gap-2">
          <input ref={fileInputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={handlePickFile} />
          <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
            <Upload className="mr-1.5 h-3.5 w-3.5" />
            {t("import.chooseFile")}
          </Button>
        </div>
        {result && (
          <div className="rounded-md border border-border bg-muted/40 p-3 text-xs">
            <p>
              {t("import.created", { count: result.created })} · {t("import.updated", { count: result.updated })}
            </p>
            {result.errors.length > 0 && (
              <ul className="mt-1 list-disc pl-4 text-destructive">
                {result.errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {importServers.isError && <p className="text-xs text-destructive">{t("import.failed")}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t("page.close")}
          </Button>
          <Button size="sm" onClick={handleImport} disabled={importServers.isPending || !csvText.trim()}>
            {importServers.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {t("import.action")}
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

export default function ServersPage() {
  const { t } = useTranslation("servers");
  const navigate = useNavigate();
  const { data: servers, isLoading } = useServers();
  const deleteServer = useDeleteServer();
  const toggleAccess = useToggleServerAccess();
  // Probe state lives in a shared hook so the Workspace SSH menu shows the
  // same live status this table does, without a second copy of the
  // bookkeeping (see useServerStatusProbe).
  const probe = useServerStatusProbe();
  const [formTarget, setFormTarget] = useState<Server | null | "new">(null);
  const [importOpen, setImportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Server | null>(null);
  const [installTarget, setInstallTarget] = useState<Server | null>(null);
  // Which row has its services panel open. One at a time: the panel is a
  // detail view of the row above it, and several open at once turns the
  // inventory into a wall of forms.
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const autoCheckedRef = useRef(false);

  function handleToggleAccess(server: Server) {
    toggleAccess.mutate(server.id, {
      onSuccess: (updated) => {
        // A stale reading would outlive the switch it contradicts: show "Off"
        // immediately, and on the way back drop the old result and re-probe,
        // so the row never claims a state nobody checked.
        if (updated.access_enabled) {
          probe.clearStatus(server.id);
          probe.checkOne(server.id);
        } else {
          probe.markDisabled(server.id);
        }
      },
    });
  }

  useEffect(() => {
    if (servers && servers.length > 0 && !autoCheckedRef.current) {
      autoCheckedRef.current = true;
      probe.checkAll(servers);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servers]);

  const [environmentFilter, setEnvironmentFilter] = useState<"all" | "vps" | "semed">("all");

  const vpsServers = (servers ?? []).filter((s) => s.environment === "vps");
  const semedServers = (servers ?? []).filter((s) => s.environment !== "vps");

  const filteredServers =
    environmentFilter === "all"
      ? (servers ?? [])
      : environmentFilter === "vps"
        ? vpsServers
        : semedServers;

  return (
    <div className="space-y-6 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <ServerIcon className="h-5 w-5" />
            {t("page.title")}
          </h1>
          <p className="text-sm text-muted-foreground">{t("page.description")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => probe.checkAll(servers ?? [])} disabled={probe.isChecking}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${probe.isChecking ? "animate-spin" : ""}`} />
            {t("page.checkStatus")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
            <Upload className="mr-1.5 h-3.5 w-3.5" />
            {t("page.importCsv")}
          </Button>
          <Button size="sm" onClick={() => setFormTarget("new")}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            {t("form.newTitle")}
          </Button>
          <AssistantToggleButton size="sm" />
        </div>
      </div>

      {/* Tabs para classificação / separação de responsabilidades */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-2">
        <Button
          variant={environmentFilter === "all" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setEnvironmentFilter("all")}
          className="text-xs font-medium"
        >
          {t("page.allCount", { count: servers?.length ?? 0 })}
        </Button>
        <Button
          variant={environmentFilter === "vps" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setEnvironmentFilter("vps")}
          className="text-xs font-medium gap-1.5"
        >
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          {t("page.vpsCount", { count: vpsServers.length })}
        </Button>
        <Button
          variant={environmentFilter === "semed" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setEnvironmentFilter("semed")}
          className="text-xs font-medium gap-1.5"
        >
          <span className="h-2 w-2 rounded-full bg-blue-500" />
          {t("page.semedCount", { count: semedServers.length })}
        </Button>
      </div>

      {/* overflow-x-auto, not hidden: on a phone the columns past IP were
          cut off with no way to reach them. */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-2">{t("page.columns.group")}</th>
              <th className="px-4 py-2">{t("page.columns.name")}</th>
              <th className="px-4 py-2">IP</th>
              <th className="px-4 py-2">{t("page.columns.user")}</th>
              <th className="px-4 py-2">{t("page.columns.port")}</th>
              <th className="px-4 py-2">{t("page.columns.description")}</th>
              <th className="px-4 py-2">{t("page.columns.status")}</th>
              <th className="px-4 py-2 text-right">{t("page.columns.actions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-muted-foreground">
                  <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                </td>
              </tr>
            )}
            {!isLoading && filteredServers.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center italic text-muted-foreground">
                  {t("page.emptyGroup")}
                </td>
              </tr>
            )}
            {filteredServers.map((s) => (
              <Fragment key={s.id}>
              <tr
                className={`cursor-pointer hover:bg-accent/30 ${s.access_enabled ? "" : "opacity-50"} ${
                  expandedId === s.id ? "bg-accent/20" : ""
                }`}
                onClick={() => setExpandedId((prev) => (prev === s.id ? null : s.id))}
                title={t("page.showServices")}
              >
                <td className="px-4 py-2">
                  <Badge variant="outline" className={`text-[10px] ${s.environment === "vps" ? "border-emerald-500/40 text-emerald-600 bg-emerald-500/5" : "border-blue-500/40 text-blue-600 bg-blue-500/5"}`}>
                    {s.environment === "vps" ? "VPS" : "SEMED"}
                  </Badge>
                </td>
                <td className="px-4 py-2 font-mono font-medium">{s.name}</td>
                <td className="px-4 py-2 font-mono">{s.ip_address}</td>
                <td className="px-4 py-2 font-mono">{s.remote_user}</td>
                <td className="px-4 py-2 font-mono">{s.ssh_port}</td>
                <td className="max-w-xs truncate px-4 py-2 text-muted-foreground" title={s.description ?? ""}>
                  {s.description ?? "—"}
                </td>
                <td className="px-4 py-2">
                  <StatusBadge result={probe.statuses[s.id]} checking={probe.checkingIds.has(s.id)} />
                </td>
                {/* Actions are buttons inside a clickable row: without
                    stopPropagation, every one of them would also toggle the
                    services panel. */}
                <td className="px-4 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className={`h-7 w-7 ${s.access_enabled ? "text-emerald-600 hover:text-emerald-500" : "text-muted-foreground"}`}
                      onClick={() => handleToggleAccess(s)}
                      disabled={toggleAccess.isPending}
                      title={
                        s.access_enabled
                          ? t("page.turnOffNamed", { name: s.name })
                          : t("page.turnOnNamed", { name: s.name })
                      }
                    >
                      {s.access_enabled ? <Power className="h-3.5 w-3.5" /> : <PowerOff className="h-3.5 w-3.5" />}
                    </Button>
                    {!s.access_enabled ? null : probe.statuses[s.id]?.status === "online" ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-emerald-600 hover:text-emerald-500"
                        onClick={() =>
                          navigate("/workspace", {
                            state: {
                              openSsh: {
                                label: s.name,
                                command: buildSshCommand(s),
                                server: { id: s.id, name: s.name, home: serverHome(s.remote_user) },
                              },
                            },
                          })
                        }
                        title={t("page.openSshNamed", { name: s.name })}
                      >
                        <SquareTerminal className="h-3.5 w-3.5" />
                      </Button>
                    ) : (
                      // Enabled in every non-online state (No key, Offline,
                      // not checked): "Offline" may just be ICMP/TCP-probe
                      // blocking, while SSH with a password still works.
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-amber-500 hover:text-amber-400"
                        onClick={() => setInstallTarget(s)}
                        title={t("page.installKeyNamed", { name: s.name })}
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => probe.checkOne(s.id)}
                      disabled={probe.checkingIds.has(s.id) || !s.access_enabled}
                      title={s.access_enabled ? t("page.checkStatus") : t("page.accessOff")}
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${probe.checkingIds.has(s.id) ? "animate-spin" : ""}`} />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setFormTarget(s)} title={t("page.edit")}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget(s)}
                      title={t("page.delete")}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
              {expandedId === s.id && (
                <tr>
                  <td colSpan={7} className="p-0">
                    <ServerServicesPanel server={s} />
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {formTarget !== null && (
        <ServerForm initial={formTarget === "new" ? null : formTarget} onClose={() => setFormTarget(null)} />
      )}
      {importOpen && <ImportCsvModal onClose={() => setImportOpen(false)} />}
      {installTarget && (
        <InstallKeyModal
          server={installTarget}
          onClose={() => setInstallTarget(null)}
          onInstalled={() => probe.checkOne(installTarget.id)}
        />
      )}
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("page.deleteTitle")}
        description={deleteTarget ? t("page.deleteDescription", { name: deleteTarget.name }) : ""}
        confirmLabel={t("page.delete")}
        loading={deleteServer.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteServer.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
