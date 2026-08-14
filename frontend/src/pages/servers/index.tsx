import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Check,
  CheckCircle2,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Lock,
  Pencil,
  Plus,
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
  useCreateServer,
  useUpdateServer,
  useDeleteServer,
  useImportServers,
  useCheckServer,
  useInstallServerKey,
  useReadServerPublicKey,
  buildSshCommand,
  resolveLiveServer,
  type Server,
  type ServerCreate,
  type ServerCheckResult,
} from "@/hooks/useServers";
import { useServerKeyVaultViewModel } from "@/hooks/useServerKeyVaultViewModel";

const EMPTY_FORM: ServerCreate = {
  name: "",
  ip_address: "",
  remote_user: "",
  ssh_port: 22,
  ssh_key_path: "",
  description: "",
};

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl">
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

/** Key vault section of the edit dialog: keeps an encrypted copy of the
 * identity file on the row and pours it back when the file on the host is
 * gone. Pure render of `useServerKeyVaultViewModel` — no state of its own.
 *
 * Why it exists at all: the row only ever recorded the key's *path*, and a
 * path survives things a key does not. Recreating the Aegis profile directory
 * on 2026-07-07 left the 172.15.2.4/172.15.2.5 identity files behind in a
 * backup directory, and the Workspace terminal simply lost those servers.
 */
function KeyVaultSection({ server }: { server: Server }) {
  const vm = useServerKeyVaultViewModel(server);

  return (
    <div className="space-y-2 rounded-md border border-border/60 p-3">
      <div className="flex items-center justify-between">
        <Label className="flex items-center gap-1.5">
          <Lock className="h-3.5 w-3.5" />
          Key vault
        </Label>
        <Badge variant={vm.vaulted ? "default" : "outline"} className="text-[10px]">
          {vm.vaulted ? "Encrypted copy stored" : "No copy stored"}
        </Badge>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Keeps the private key encrypted in ForgeHub's database, so losing the file on the host no
        longer means losing access to the server. The key is never sent back to the browser —
        restoring writes it straight to the host at the path above.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!vm.hasKeyPath || vm.isBusy}
          title={vm.hasKeyPath ? "Read the identity file from the host and store it encrypted" : "Set an SSH key path first"}
          onClick={vm.backup}
        >
          {vm.status === "backing_up" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          {vm.vaulted ? "Update copy from host" : "Store key from host"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!vm.vaulted || !vm.hasKeyPath || vm.isBusy}
          title="Write the stored key back to the host (never overwrites an existing file)"
          onClick={vm.restore}
        >
          {vm.status === "restoring" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          Restore to host
        </Button>
        {vm.vaulted && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-destructive"
            disabled={vm.isBusy}
            onClick={vm.requestClear}
          >
            {vm.status === "clearing" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            Remove copy
          </Button>
        )}
      </div>
      <div className="space-y-1">
        <Textarea
          value={vm.pastedKey}
          onChange={(e) => vm.setPastedKey(e.target.value)}
          placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;…paste a key this host doesn't have…"
          className="min-h-[56px] font-mono text-[10px]"
          disabled={vm.isBusy}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!vm.pastedKey.trim() || vm.isBusy}
          onClick={vm.storePasted}
        >
          {vm.status === "storing" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          Store pasted key
        </Button>
      </div>
      {vm.message && <p className="text-[11px] text-emerald-600">{vm.message}</p>}
      {vm.error && <p className="text-[11px] text-destructive">{vm.error}</p>}
      <ConfirmDialog
        open={vm.status === "confirming_clear"}
        title="Remove the stored key?"
        description={`ForgeHub's encrypted copy of ${server.name}'s key is deleted. The file on the host is left untouched — but if it is ever lost, there will be no copy to restore from.`}
        confirmLabel="Remove copy"
        loading={vm.status === "clearing"}
        onConfirm={vm.confirmClear}
        onCancel={vm.cancelClear}
      />
    </div>
  );
}

function ServerFormModal({ initial, onClose }: { initial: Server | null; onClose: () => void }) {
  const [form, setForm] = useState<ServerCreate>(
    initial
      ? {
          name: initial.name,
          ip_address: initial.ip_address,
          remote_user: initial.remote_user,
          ssh_port: initial.ssh_port,
          ssh_key_path: initial.ssh_key_path ?? "",
          description: initial.description ?? "",
        }
      : EMPTY_FORM
  );
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pubKeyCopied, setPubKeyCopied] = useState(false);
  const createServer = useCreateServer();
  const updateServer = useUpdateServer();
  const readPublicKey = useReadServerPublicKey();
  const pending = createServer.isPending || updateServer.isPending;
  // `initial` is the row as it was when the dialog opened. The read-only
  // blocks below (key vault, stored public key) must show what the row *is*
  // now, or an action taken inside this dialog appears not to have happened --
  // see resolveLiveServer. The editable fields deliberately keep reading from
  // `form`, which is seeded once, so a refetch never overwrites typing.
  const { data: servers } = useServers();
  const live = initial ? resolveLiveServer(servers, initial) : null;

  function handleSave() {
    setError(null);
    if (!form.name.trim() || !form.ip_address.trim() || !form.remote_user.trim()) {
      setError("Name, IP and remote user are required.");
      return;
    }
    const payload: ServerCreate = {
      name: form.name.trim(),
      ip_address: form.ip_address.trim(),
      remote_user: form.remote_user.trim(),
      ssh_port: form.ssh_port || 22,
      ssh_key_path: form.ssh_key_path?.trim() || null,
      description: form.description?.trim() || null,
    };
    if (initial) {
      updateServer.mutate({ id: initial.id, data: payload }, { onSuccess: onClose, onError: () => setError("Could not save.") });
    } else {
      createServer.mutate(payload, { onSuccess: onClose, onError: () => setError("Could not save. The name may already exist.") });
    }
  }

  return (
    <ModalShell title={initial ? "Edit server" : "New server"} onClose={onClose}>
      <div className="space-y-4">
        <div className="space-y-1">
          <Label>Server name</Label>
          <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="srv-app01" />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2 space-y-1">
            <Label>IP address</Label>
            <Input value={form.ip_address} onChange={(e) => setForm((f) => ({ ...f, ip_address: e.target.value }))} placeholder="172.15.2.2" />
          </div>
          <div className="space-y-1">
            <Label>SSH port</Label>
            <Input
              type="number"
              value={form.ssh_port ?? 22}
              onChange={(e) => setForm((f) => ({ ...f, ssh_port: Number(e.target.value) || 22 }))}
            />
          </div>
        </div>
        <div className="space-y-1">
          <Label>Remote user</Label>
          <Input value={form.remote_user} onChange={(e) => setForm((f) => ({ ...f, remote_user: e.target.value }))} placeholder="aegis" />
        </div>
        <div className="space-y-1">
          <Label>SSH key path (identity file)</Label>
          <div className="flex items-start gap-2">
            <Input
              value={form.ssh_key_path ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, ssh_key_path: e.target.value }))}
              placeholder="/root/.ssh/id_ed25519_aegis"
              className="flex-1 font-mono text-xs"
            />
            {live?.ssh_key_path && (
              <Button
                type="button"
                variant="outline"
                size="icon"
                title="Copy the public key of this path"
                disabled={readPublicKey.isPending}
                onClick={() => {
                  readPublicKey.mutate(live.id, {
                    onSuccess: (srv) => {
                      if (srv.public_key) {
                        void navigator.clipboard.writeText(srv.public_key);
                        setPubKeyCopied(true);
                        setTimeout(() => setPubKeyCopied(false), 1500);
                      }
                    },
                  });
                }}
              >
                {readPublicKey.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : pubKeyCopied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-600" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">
            Used as <code className="font-mono">ssh -i &lt;path&gt;</code> when opening the SSH terminal. Leave blank to use the shell's default key/agent.
            {live?.ssh_key_path && " The copy button reads the public key (<path>.pub) and saves it to this record."}
          </p>
          {readPublicKey.isError && (
            <p className="text-[11px] text-destructive">{readPublicKey.error.message}</p>
          )}
        </div>
        {live && <KeyVaultSection server={live} />}
        <div className="space-y-1">
          <Label>Description</Label>
          <Textarea
            value={form.description ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="Main application server"
          />
        </div>
        {live?.public_key && (
          <div className="space-y-1">
            <Label>Public key (installed on the server)</Label>
            <div className="flex items-start gap-2">
              <Textarea readOnly value={live.public_key} className="min-h-[56px] flex-1 font-mono text-[10px]" />
              <Button
                type="button"
                variant="outline"
                size="icon"
                title="Copy public key"
                onClick={() => { void navigator.clipboard.writeText(live.public_key ?? ""); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
              >
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">Filled automatically by the "Install SSH key" action.</p>
          </div>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave} disabled={pending}>
            {pending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            Save
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

/** One-shot dedicated-key installation: asks for the server credential,
 * then the host bridge generates the ed25519 pair (idempotent), pushes the
 * .pub via ssh-copy-id and verifies BatchMode auth. Mirrors the manual
 * procedure in /root/.hermes/scripts/configure_ssh.sh, parameterized. */
function InstallKeyModal({ server, onClose, onInstalled }: { server: Server; onClose: () => void; onInstalled: () => void }) {
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
    <ModalShell title={`Install SSH key — ${server.name}`} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-xs text-muted-foreground">
          Generates a dedicated <code className="font-mono">ed25519</code> key on this host (reused if it already
          exists) and installs the public key on <code className="font-mono">{server.ip_address}</code>, then verifies
          key authentication. Passwords are used only for this installation — never stored or logged.
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
                  <span className="font-medium text-foreground">Use a server admin account</span> to create the user and
                  install the key. Enable this when <code className="font-mono">{remoteUser}</code> isn't provisioned on the
                  server yet. The admin must be <code className="font-mono">root</code> or have passwordless{" "}
                  <code className="font-mono">sudo</code>.
                </span>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>{useAdmin ? "Registered user (created if missing)" : "Registered user"}</Label>
                <Input value={remoteUser} disabled readOnly className="font-mono" />
              </div>
              {useAdmin && (
                <div className="space-y-1">
                  <Label>Admin account</Label>
                  <Input value={adminUser} onChange={(e) => setAdminUser(e.target.value)} placeholder="root" disabled={installKey.isPending} />
                </div>
              )}
              <div className={useAdmin ? "col-span-2 space-y-1" : "space-y-1"}>
                <Label>{useAdmin ? `Password for "${adminUser || "admin"}"` : `Password for "${remoteUser}"`}</Label>
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
                    title={showPassword ? "Hide password" : "Show password"}
                    aria-label={showPassword ? "Hide password" : "Show password"}
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
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Generating key, installing on the server and verifying…
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
                Failed at "{result.failed_step}": {result.error}
              </p>
            )}
            {result.ok && result.public_key && (
              <div className="space-y-1 pt-1">
                <Label className="text-[11px]">Installed public key (saved on the server record)</Label>
                <Textarea readOnly value={result.public_key} className="min-h-[64px] font-mono text-[10px]" />
              </div>
            )}
          </div>
        )}
        {installKey.isError && (
          <p className="text-xs text-destructive">{installKey.error.message}</p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>{done ? "Close" : "Cancel"}</Button>
          {!done && (
            <Button size="sm" onClick={handleInstall} disabled={installKey.isPending || !canSubmit}>
              {installKey.isPending ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <KeyRound className="mr-1.5 h-3.5 w-3.5" />}
              Install key
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
  if (checking) {
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> Checking…
      </Badge>
    );
  }
  if (!result) {
    return <span className="text-xs italic text-muted-foreground/60">not checked</span>;
  }
  if (result.status === "online") {
    return (
      <Badge variant="outline" className="gap-1 text-emerald-600 border-emerald-500/30" title={result.detail}>
        <Wifi className="h-3 w-3" /> Online
      </Badge>
    );
  }
  if (result.status === "no_key") {
    return (
      <Badge variant="outline" className="gap-1 text-amber-600 border-amber-500/30" title={result.detail}>
        <KeyRound className="h-3 w-3" /> No key
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 text-red-600 border-red-500/30" title={result.detail}>
      <WifiOff className="h-3 w-3" /> Offline
    </Badge>
  );
}

const CSV_PLACEHOLDER = `SERVER_NAME,SERVER_IP,REMOTE_USER,DESCRIPTION
srv-app01,172.15.2.2,aegis,"Main application server"`;

function ImportCsvModal({ onClose }: { onClose: () => void }) {
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
    <ModalShell title="Import servers (CSV)" onClose={onClose}>
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Paste the CSV or pick a file. Required header: <code className="font-mono">SERVER_NAME,SERVER_IP,REMOTE_USER,DESCRIPTION</code>.
          Existing servers (same name) are updated.
        </p>
        <Textarea
          value={csvText}
          onChange={(e) => setCsvText(e.target.value)}
          placeholder={CSV_PLACEHOLDER}
          className="min-h-[180px] font-mono text-xs"
        />
        <div className="flex items-center gap-2">
          <input ref={fileInputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={handlePickFile} />
          <Button type="button" variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
            <Upload className="mr-1.5 h-3.5 w-3.5" />
            Choose file
          </Button>
        </div>
        {result && (
          <div className="rounded-md border border-border bg-muted/40 p-3 text-xs">
            <p>
              Created: <strong>{result.created}</strong> · Updated: <strong>{result.updated}</strong>
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
        {importServers.isError && <p className="text-xs text-destructive">Import failed. Check the CSV format.</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
          <Button size="sm" onClick={handleImport} disabled={importServers.isPending || !csvText.trim()}>
            {importServers.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            Import
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

export default function ServersPage() {
  const navigate = useNavigate();
  const { data: servers, isLoading } = useServers();
  const deleteServer = useDeleteServer();
  const checkServer = useCheckServer();
  const [formTarget, setFormTarget] = useState<Server | null | "new">(null);
  const [importOpen, setImportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Server | null>(null);
  const [installTarget, setInstallTarget] = useState<Server | null>(null);
  const [statuses, setStatuses] = useState<Record<string, ServerCheckResult>>({});
  const [checkingIds, setCheckingIds] = useState<Set<string>>(new Set());
  const autoCheckedRef = useRef(false);

  function checkOne(id: string) {
    setCheckingIds((prev) => new Set(prev).add(id));
    // mutateAsync's returned promise is bound to this specific call, unlike
    // mutate()'s { onSuccess, onSettled } options -- those are stored on the
    // single shared mutation observer, so firing many mutate() calls back to
    // back (checkAll below) would leave only the *last* call's callbacks
    // installed, silently dropping updates for every earlier server.
    checkServer
      .mutateAsync(id)
      .then((result) => setStatuses((prev) => ({ ...prev, [id]: result })))
      .catch(() => {})
      .finally(() =>
        setCheckingIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        })
      );
  }

  function checkAll() {
    (servers ?? []).forEach((s) => checkOne(s.id));
  }

  useEffect(() => {
    if (servers && servers.length > 0 && !autoCheckedRef.current) {
      autoCheckedRef.current = true;
      checkAll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servers]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <ServerIcon className="h-5 w-5" />
            Servers
          </h1>
          <p className="text-sm text-muted-foreground">Inventory of servers with SSH access.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={checkAll} disabled={checkingIds.size > 0}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${checkingIds.size > 0 ? "animate-spin" : ""}`} />
            Check status
          </Button>
          <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
            <Upload className="mr-1.5 h-3.5 w-3.5" />
            Import CSV
          </Button>
          <Button size="sm" onClick={() => setFormTarget("new")}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            New server
          </Button>
          <AssistantToggleButton size="sm" />
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">IP</th>
              <th className="px-4 py-2">User</th>
              <th className="px-4 py-2">Port</th>
              <th className="px-4 py-2">Description</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-muted-foreground">
                  <Loader2 className="mx-auto h-4 w-4 animate-spin" />
                </td>
              </tr>
            )}
            {!isLoading && (servers ?? []).length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center italic text-muted-foreground">
                  No servers registered.
                </td>
              </tr>
            )}
            {(servers ?? []).map((s) => (
              <tr key={s.id} className="hover:bg-accent/30">
                <td className="px-4 py-2 font-mono font-medium">{s.name}</td>
                <td className="px-4 py-2 font-mono">{s.ip_address}</td>
                <td className="px-4 py-2 font-mono">{s.remote_user}</td>
                <td className="px-4 py-2 font-mono">{s.ssh_port}</td>
                <td className="max-w-xs truncate px-4 py-2 text-muted-foreground" title={s.description ?? ""}>
                  {s.description ?? "—"}
                </td>
                <td className="px-4 py-2">
                  <StatusBadge result={statuses[s.id]} checking={checkingIds.has(s.id)} />
                </td>
                <td className="px-4 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    {statuses[s.id]?.status === "online" ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-emerald-600 hover:text-emerald-500"
                        onClick={() =>
                          navigate("/workspace", {
                            state: { openSsh: { label: s.name, command: buildSshCommand(s) } },
                          })
                        }
                        title={`Open SSH terminal to ${s.name} in Workspace`}
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
                        title={`Install SSH key on ${s.name}`}
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => checkOne(s.id)}
                      disabled={checkingIds.has(s.id)}
                      title="Check status"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${checkingIds.has(s.id) ? "animate-spin" : ""}`} />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setFormTarget(s)} title="Edit">
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-destructive hover:text-destructive"
                      onClick={() => setDeleteTarget(s)}
                      title="Delete"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {formTarget !== null && (
        <ServerFormModal initial={formTarget === "new" ? null : formTarget} onClose={() => setFormTarget(null)} />
      )}
      {importOpen && <ImportCsvModal onClose={() => setImportOpen(false)} />}
      {installTarget && (
        <InstallKeyModal
          server={installTarget}
          onClose={() => setInstallTarget(null)}
          onInstalled={() => checkOne(installTarget.id)}
        />
      )}
      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete server"
        description={deleteTarget ? `Delete "${deleteTarget.name}" from the inventory?` : ""}
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
