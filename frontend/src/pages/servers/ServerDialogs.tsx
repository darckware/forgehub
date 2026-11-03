/** Server dialogs shared by the Servers page and Remote Access › Machines
 * (docs/architecture/REMOTE_ACCESS_SERVERS_UNIFICATION_PLAN.md, phase 3). */
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Eye, EyeOff, KeyRound, Loader2, Upload, X, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useImportServers, useInstallServerKey, type Server } from "@/hooks/useServers";
import { isValidSshPort, SshPortField } from "./SshPortField";

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
export function InstallKeyModal({ server, onClose, onInstalled }: { server: Server; onClose: () => void; onInstalled: () => void }) {
  const { t } = useTranslation("remoteAccess", { keyPrefix: "servers" });
  // The account to log in with (and create, in admin mode) is the server
  // record's own remote_user -- not re-typed here.
  const remoteUser = server.remote_user;
  const [adminUser, setAdminUser] = useState("root");
  const [sshPort, setSshPort] = useState(String(server.ssh_port ?? 22));
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  // Admin mode (default): log in with the server admin account, create the
  // registered user if needed, install the key. Off = classic ssh-copy-id as
  // the registered user itself (must already exist on the server).
  const [useAdmin, setUseAdmin] = useState(true);
  const installKey = useInstallServerKey();
  const result = installKey.data ?? null;
  const done = result?.ok === true;
  const canSubmit = Boolean(password && (!useAdmin || adminUser.trim())) && isValidSshPort(sshPort);

  function handleInstall() {
    if (installKey.isPending || !canSubmit) return;
    installKey.mutate(
      {
        id: server.id,
        password,
        admin_user: useAdmin ? adminUser.trim() : null,
        ssh_port: Number(sshPort),
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
              <div className="col-span-2">
                <SshPortField id="install-ssh-port" value={sshPort} onChange={setSshPort} disabled={installKey.isPending} />
              </div>
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
            {result.ok && result.vault && (
              <p className={`flex items-start gap-1.5 ${result.vault === "switched" ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}`}>
                {result.vault === "switched"
                  ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
                {result.vault === "switched" ? t("install.vaultSwitched") : t("install.vaultFailed", { reason: result.vault.replace(/^failed:\s*/, "") })}
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

const CSV_PLACEHOLDER = `SERVER_NAME,SERVER_IP,REMOTE_USER,DESCRIPTION
srv-app01,172.15.2.2,aegis,"Main application server"`;

export function ImportCsvModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("remoteAccess", { keyPrefix: "servers" });
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
