/**
 * Create/edit form for the server inventory.
 *
 * Its own component and its own dialog chrome, replacing the page's shared
 * `ModalShell` for this screen (2026-08-14, Marcelo: "não use o ModalShell,
 * crie um formulario para o cadastro do servidores"). `ModalShell` is a plain
 * centered card with no height budget, so once the key vault and the key
 * fields were added the form outgrew the viewport: the title sat above the top
 * edge and Cancel/Save fell off the bottom, unreachable. Here the dialog is a
 * flex column capped at 85vh -- header and footer stay put, only the field
 * area scrolls, so the actions are always on screen no matter how long the
 * form gets.
 *
 * Validation is React Hook Form + zodResolver over `serverFormSchema`
 * (colocated in `useServers.ts`), the standard the rest of the codebase's
 * forms follow -- the previous version hand-rolled an if-chain.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Check, Copy, KeyRound, Loader2, Lock, Power, PowerOff, Trash2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TokenField } from "@/components/ui/token-field";
import {
  resolveLiveServer,
  serverFormSchema,
  useCreateServer,
  useReadServerPublicKey,
  useServer,
  useServers,
  useToggleServerAccess,
  useUpdateServer,
  type Server,
  type ServerCreate,
  type ServerFormValues,
} from "@/hooks/useServers";
import { useServerKeyVaultViewModel } from "@/hooks/useServerKeyVaultViewModel";

/** Key vault section: keeps an encrypted copy of the identity file on the row
 * and pours it back when the file on the host is gone. Pure render of
 * `useServerKeyVaultViewModel` — no state of its own.
 *
 * Why it exists at all: the row only ever recorded the key's *path*, and a
 * path survives things a key does not. Recreating the Aegis profile directory
 * on 2026-07-07 left the 172.15.2.4/172.15.2.5 identity files behind in a
 * backup directory, and the Workspace terminal simply lost those servers.
 */
function KeyVaultSection({ server }: { server: Server }) {
  const { t } = useTranslation("servers");
  const vm = useServerKeyVaultViewModel(server);

  return (
    <div className="space-y-2 rounded-md border border-border/60 p-3">
      <div className="flex items-center justify-between">
        <Label className="flex items-center gap-1.5">
          <Lock className="h-3.5 w-3.5" />
          {t("form.vault.title")}
        </Label>
        <Badge variant={vm.vaulted ? "default" : "outline"} className="text-[10px]">
          {vm.vaulted ? t("form.vault.stored") : t("form.vault.notStored")}
        </Badge>
      </div>
      <p className="text-[11px] text-muted-foreground">
        {t("form.vault.description")}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!vm.hasKeyPath || vm.isBusy}
          title={vm.hasKeyPath ? t("form.vault.storeTitle") : t("form.vault.pathRequired")}
          onClick={vm.backup}
        >
          {vm.status === "backing_up" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          {vm.vaulted ? t("form.vault.updateCopy") : t("form.vault.storeFromHost")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!vm.vaulted || !vm.hasKeyPath || vm.isBusy}
          title={t("form.vault.restoreTitle")}
          onClick={vm.restore}
        >
          {vm.status === "restoring" && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          {t("form.vault.restore")}
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
            {t("form.vault.removeCopy")}
          </Button>
        )}
      </div>
      <div className="space-y-1">
        <Textarea
          value={vm.pastedKey}
          onChange={(e) => vm.setPastedKey(e.target.value)}
          placeholder={t("form.vault.pastePlaceholder")}
          className="resize-none min-h-[56px] font-mono text-[10px]"
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
          {t("form.vault.storePasted")}
        </Button>
      </div>
      {vm.message && <p className="text-[11px] text-emerald-600">{vm.message}</p>}
      {vm.error && <p className="text-[11px] text-destructive">{vm.error}</p>}
      <ConfirmDialog
        open={vm.status === "confirming_clear"}
        title={t("form.vault.removeTitle")}
        description={t("form.vault.removeDescription", { name: server.name })}
        confirmLabel={t("form.vault.removeCopy")}
        loading={vm.status === "clearing"}
        onConfirm={vm.confirmClear}
        onCancel={vm.cancelClear}
      />
    </div>
  );
}

/** Key passphrase, built like the agent page's ForgeRouter API key card
 * (2026-08-14, Marcelo: "pode colocar o campo igual a api key do agente"):
 * a Configured/Not set badge, the current value behind an eye toggle, its own
 * Save button and a trash button that clears it after a confirmation.
 *
 * Saving here rather than with the form's Save is what makes the card work
 * like that one: the value is fetched by the admin-only single-server read
 * (`useServer`), so it does not belong to the form's seeded state, and a
 * passphrase can be stored or cleared without validating the rest of the form.
 */
function PassphraseSection({ server }: { server: Server }) {
  const { t } = useTranslation("servers");
  const { data: detail, isLoading } = useServer(server.id);
  const updateServer = useUpdateServer();
  const [value, setValue] = useState("");
  const [seededFor, setSeededFor] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  // Seed once per server, and again whenever a save brings a new stored value
  // back -- but never on every render, or typing would be overwritten by the
  // value already on file.
  const seedKey = `${server.id}:${detail?.key_passphrase ?? ""}`;
  if (detail && seededFor !== seedKey) {
    setSeededFor(seedKey);
    setValue(detail.key_passphrase ?? "");
  }

  function save(next: string) {
    updateServer.mutate({ id: server.id, data: { key_passphrase: next } });
  }

  return (
    <div className="space-y-2 rounded-md border border-border/60 p-3">
      <div className="flex items-center justify-between">
        <Label className="flex items-center gap-1.5">
          <KeyRound className="h-3.5 w-3.5" />
          {t("form.passphrase.title")}
        </Label>
        <Badge variant={server.key_passphrase_stored ? "default" : "outline"} className="text-[10px]">
          {server.key_passphrase_stored ? t("form.passphrase.configured") : t("form.passphrase.notSet")}
        </Badge>
      </div>
      <p className="text-[11px] text-muted-foreground">
        {t("form.passphrase.description")}
      </p>
      <div className="flex gap-2">
        <div className="flex-1">
          <TokenField
            value={value}
            onChange={setValue}
            placeholder={isLoading ? t("form.loading") : t("form.passphrase.leaveBlank")}
            disabled={isLoading || updateServer.isPending}
          />
        </div>
        <Button
          type="button"
          size="sm"
          disabled={!value || updateServer.isPending}
          onClick={() => save(value)}
        >
          {updateServer.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <KeyRound className="mr-1.5 h-3.5 w-3.5" />
          )}
          {t("form.save")}
        </Button>
        {server.key_passphrase_stored && (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-9 w-9"
            title={t("form.passphrase.remove")}
            aria-label={t("form.passphrase.remove")}
            disabled={updateServer.isPending}
            onClick={() => setConfirmRemove(true)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
      {updateServer.isError && <p className="text-[11px] text-destructive">{updateServer.error.message}</p>}
      <ConfirmDialog
        open={confirmRemove}
        title={t("form.passphrase.removeTitle")}
        description={t("form.passphrase.removeDescription", { name: server.name })}
        confirmLabel={t("form.passphrase.removeAction")}
        loading={updateServer.isPending}
        onConfirm={() => {
          save("");
          setValue("");
          setConfirmRemove(false);
        }}
        onCancel={() => setConfirmRemove(false)}
      />
    </div>
  );
}

/** The access switch, mirroring the row-level icon in the list. Its own
 * mutation rather than part of the form submit: parking a server is one click
 * with nothing to validate, and it must work whether or not the rest of the
 * form is currently valid. */
function AccessSection({ server }: { server: Server }) {
  const { t } = useTranslation("servers");
  const toggleAccess = useToggleServerAccess();
  const enabled = server.access_enabled;

  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-border/60 p-3">
      <div className="space-y-0.5">
        <Label className="flex items-center gap-1.5">
          {enabled ? <Power className="h-3.5 w-3.5 text-emerald-500" /> : <PowerOff className="h-3.5 w-3.5 text-muted-foreground" />}
          {t("form.access.title")}
        </Label>
        <p className="text-[11px] text-muted-foreground">
          {enabled
            ? t("form.access.enabledDescription")
            : t("form.access.disabledDescription")}
        </p>
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={toggleAccess.isPending}
        onClick={() => toggleAccess.mutate(server.id)}
      >
        {toggleAccess.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
        {enabled ? t("form.access.turnOff") : t("form.access.turnOn")}
      </Button>
    </div>
  );
}

export function ServerForm({ initial, onClose }: { initial: Server | null; onClose: () => void }) {
  const { t } = useTranslation("servers");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pubKeyCopied, setPubKeyCopied] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [passphraseTouched, setPassphraseTouched] = useState(false);

  const createServer = useCreateServer();
  const updateServer = useUpdateServer();
  const readPublicKey = useReadServerPublicKey();
  const pending = createServer.isPending || updateServer.isPending;

  // `initial` is the row as it was when the dialog opened. The read-only
  // blocks below (key vault, access switch, stored public key) must show what
  // the row *is* now, or an action taken inside this dialog appears not to
  // have happened -- see resolveLiveServer. The editable fields keep their own
  // form state, seeded once, so a refetch never overwrites typing.
  const { data: servers } = useServers();
  const live = initial ? resolveLiveServer(servers, initial) : null;

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ServerFormValues>({
    resolver: zodResolver(serverFormSchema),
    defaultValues: {
      name: initial?.name ?? "",
      ip_address: initial?.ip_address ?? "",
      remote_user: initial?.remote_user ?? "",
      ssh_port: initial?.ssh_port ?? 22,
      ssh_key_path: initial?.ssh_key_path ?? "",
      environment: (initial?.environment as "vps" | "semed") ?? "semed",
      description: initial?.description ?? "",
    },
  });

  function onSubmit(values: ServerFormValues) {
    setSaveError(null);
    const payload: ServerCreate = {
      name: values.name,
      ip_address: values.ip_address,
      remote_user: values.remote_user,
      ssh_port: values.ssh_port,
      ssh_key_path: values.ssh_key_path?.trim() || null,
      environment: values.environment,
      description: values.description?.trim() || null,
    };
    // Only send the passphrase when the field was actually touched: an
    // untouched field is empty because the form never receives the stored
    // value, and sending "" would clear a passphrase nobody meant to remove.
    if (passphraseTouched) payload.key_passphrase = passphrase;

    if (initial) {
      updateServer.mutate(
        { id: initial.id, data: payload },
        { onSuccess: onClose, onError: () => setSaveError(t("form.saveFailed")) },
      );
    } else {
      createServer.mutate(payload, {
        onSuccess: onClose,
        onError: () => setSaveError(t("form.createFailed")),
      });
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      {/* Capped height + a single scrolling region: the header and the actions
          must stay reachable however long the form grows. */}
      <form noValidate
        onSubmit={handleSubmit(onSubmit)}
        className="relative z-10 flex max-h-[85vh] w-full max-w-md flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold">{initial ? t("form.editTitle") : t("form.newTitle")}</h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
          <div className="space-y-1">
            <Label>{t("form.name")}</Label>
            <Input {...register("name")} placeholder="srv-app01" />
            {errors.name && <p className="text-[11px] text-destructive">{errors.name.message}</p>}
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2 space-y-1">
              <Label>{t("form.ipAddress")}</Label>
              <Input {...register("ip_address")} placeholder="172.15.2.2" />
              {errors.ip_address && <p className="text-[11px] text-destructive">{errors.ip_address.message}</p>}
            </div>
            <div className="space-y-1">
              <Label>{t("form.sshPort")}</Label>
              <Input type="number" {...register("ssh_port", { valueAsNumber: true })} />
              {errors.ssh_port && <p className="text-[11px] text-destructive">{errors.ssh_port.message}</p>}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>{t("form.remoteUser")}</Label>
              <Input {...register("remote_user")} placeholder="aegis" />
              {errors.remote_user && <p className="text-[11px] text-destructive">{errors.remote_user.message}</p>}
            </div>
            <div className="space-y-1">
              <Label>{t("form.group")}</Label>
              <select
                {...register("environment")}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="vps">{t("form.groups.vps")}</option>
                <option value="semed">{t("form.groups.semed")}</option>
              </select>
              {errors.environment && <p className="text-[11px] text-destructive">{errors.environment.message}</p>}
            </div>
          </div>

          <div className="space-y-1">
            <Label>{t("form.sshKeyPath")}</Label>
            <div className="flex items-start gap-2">
              <Input
                {...register("ssh_key_path")}
                placeholder="/root/.ssh/id_ed25519_aegis"
                className="flex-1 font-mono text-xs"
              />
              {live?.ssh_key_path && (
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  title={t("form.copyPathPublicKey")}
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
              {t("form.sshKeyHelpBefore")} <code className="font-mono">ssh -i &lt;path&gt;</code> {t("form.sshKeyHelpAfter")}
              {live?.ssh_key_path && ` ${t("form.sshKeyCopyHelp")}`}
            </p>
            {readPublicKey.isError && <p className="text-[11px] text-destructive">{readPublicKey.error.message}</p>}
          </div>

          {live ? <PassphraseSection server={live} /> : (
            // No row yet, so there is nothing to save a passphrase against --
            // it rides along with the create payload instead.
            <div className="space-y-1">
              <Label className="flex items-center gap-1.5">
                <KeyRound className="h-3.5 w-3.5" />
                {t("form.passphrase.title")}
              </Label>
              <TokenField
                value={passphrase}
                onChange={(v) => {
                  setPassphrase(v);
                  setPassphraseTouched(true);
                }}
                placeholder={t("form.passphrase.leaveBlank")}
                disabled={pending}
              />
              <p className="text-[11px] text-muted-foreground">{t("form.passphrase.encrypted")}</p>
            </div>
          )}

          {live && <AccessSection server={live} />}
          {live && <KeyVaultSection server={live} />}

          <div className="space-y-1">
            <Label>{t("form.description")}</Label>
            <Textarea className="resize-none" {...register("description")} placeholder={t("form.descriptionExample")} />
          </div>

          {live?.public_key && (
            <div className="space-y-1">
              <Label>{t("form.publicKey")}</Label>
              <div className="flex items-start gap-2">
                <Textarea readOnly value={live.public_key} className="resize-none min-h-[56px] flex-1 font-mono text-[10px]" />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  title={t("form.copyPublicKey")}
                  onClick={() => {
                    void navigator.clipboard.writeText(live.public_key ?? "");
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                {t("form.publicKeyHelp")}
              </p>
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border px-6 py-4">
          {saveError && <p className="mr-auto text-xs text-destructive">{saveError}</p>}
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            {t("form.cancel")}
          </Button>
          <Button type="submit" size="sm" disabled={pending}>
            {pending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {t("form.save")}
          </Button>
        </div>
      </form>
    </div>
  );
}
