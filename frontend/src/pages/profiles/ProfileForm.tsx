import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Profile, ProfilePermission } from "@/hooks/useAuth";
import { useCreateProfile, useUpdateProfile } from "@/hooks/useAuth";

const MODULES = [
  "product", "projects", "pipeline", "backlog", "tasks", "agents",
  "artifacts", "governance", "forgerouter", "obsidian",
  "foundation", "crons", "deploy", "servers", "database", "users", "profiles",
];

const SENSITIVE_ACTIONS = [
  "planning.concept.view", "planning.concept.edit", "planning.concept.submit",
  "planning.concept.decide", "planning.blueprint.edit", "planning.blueprint.approve",
  "planning.delivery.authorize", "planning.progress.view", "planning.progress.manage",
  "planning.stage.complete", "planning.execution.view", "planning.execution.manage",
  "planning.execution.release", "planning.execution.dispatch", "planning.execution.cancel",
  "governance.approval.view", "governance.approval.decide", "governance.delegation.manage",
] as const;

type PermOp = "can_view" | "can_query" | "can_write" | "can_delete";
type PermRow = Record<PermOp, boolean>;

function defaultPerms(): Record<string, PermRow> {
  return Object.fromEntries(
    MODULES.map((m) => [m, { can_view: true, can_query: true, can_write: false, can_delete: false }])
  );
}

function profileToPerms(profile: Profile): Record<string, PermRow> {
  const base = defaultPerms();
  for (const p of profile.permissions) {
    base[p.module] = { can_view: p.can_view, can_query: p.can_query, can_write: p.can_write, can_delete: p.can_delete };
  }
  return base;
}

interface Props {
  profile?: Profile;
  onClose: () => void;
}

export default function ProfileForm({ profile, onClose }: Props) {
  const { t } = useTranslation("profiles");
  const [name, setName] = useState(profile?.name ?? "");
  const [description, setDescription] = useState(profile?.description ?? "");
  const [perms, setPerms] = useState<Record<string, PermRow>>(
    profile ? profileToPerms(profile) : defaultPerms()
  );
  const [actions, setActions] = useState<Record<string, boolean>>(() => Object.fromEntries(
    SENSITIVE_ACTIONS.map((key) => [key, profile?.action_permissions?.find((item) => item.action_key === key)?.allowed ?? false])
  ));

  const createMut = useCreateProfile();
  const updateMut = useUpdateProfile();
  const isPending = createMut.isPending || updateMut.isPending;
  const error = createMut.error ?? updateMut.error;

  const toggle = (module: string, op: PermOp) => {
    setPerms((prev) => ({
      ...prev,
      [module]: { ...prev[module], [op]: !prev[module][op] },
    }));
  };

  // Selecting a column: toggle all modules for that op
  const toggleColumn = (op: PermOp) => {
    const allOn = MODULES.every((m) => perms[m][op]);
    setPerms((prev) => {
      const next = { ...prev };
      for (const m of MODULES) next[m] = { ...next[m], [op]: !allOn };
      return next;
    });
  };

  const toPayload = (): ProfilePermission[] =>
    MODULES.map((m) => ({ module: m, ...perms[m] }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (profile) {
        await updateMut.mutateAsync({ id: profile.id, body: { name, description: description || undefined, permissions: toPayload(), action_permissions: Object.entries(actions).map(([action_key, allowed]) => ({ action_key, allowed })) } });
      } else {
        await createMut.mutateAsync({ name, description: description || undefined, permissions: toPayload(), action_permissions: Object.entries(actions).map(([action_key, allowed]) => ({ action_key, allowed })) });
      }
      onClose();
    } catch {
      // shown below
    }
  };

  const OPS: PermOp[] = ["can_view", "can_query", "can_write", "can_delete"];

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="profile-name">{t("profiles.form.name")} *</Label>
          <Input id="profile-name" value={name} onChange={(e) => setName(e.target.value)} required placeholder={t("profiles.form.namePlaceholder")} />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="profile-description">{t("profiles.form.description")}</Label>
          <Input id="profile-description" value={description} onChange={(e) => setDescription(e.target.value)} placeholder={t("profiles.form.descriptionPlaceholder")} />
        </div>
      </div>

      <div className="rounded-md border border-border p-3">
        <p className="mb-2 text-sm font-medium">{t("profiles.form.sensitiveTitle")}</p>
        <p className="mb-3 text-xs text-muted-foreground">{t("profiles.form.sensitiveHelp")}</p>
        <div className="grid gap-2 md:grid-cols-2">
          {SENSITIVE_ACTIONS.map((key) => <label key={key} className="flex items-start gap-2 rounded border p-2 text-xs">
            <input type="checkbox" checked={actions[key]} onChange={() => setActions((value) => ({ ...value, [key]: !value[key] }))} className="mt-0.5 h-3.5 w-3.5" />
            <span><span className="block font-medium">{t(`profiles.form.actions.${key.replace(/\./g, "_")}`)}</span><code className="text-[10px] text-muted-foreground">{key}</code></span>
          </label>)}
        </div>
      </div>

      {/* Permissions matrix */}
      <div className="rounded-md border border-border overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-muted/50">
              <th className="px-3 py-2 text-left font-medium text-muted-foreground">{t("profiles.permissions.column.module")}</th>
              {OPS.map((key) => (
                <th key={key} className="px-3 py-2 text-center font-medium text-muted-foreground">
                  <button type="button" className="hover:text-foreground transition-colors" onClick={() => toggleColumn(key)}>
                    {t(`profiles.form.operations.${key}`)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30">
            {MODULES.map((m) => (
              <tr key={m} className="hover:bg-muted/20">
                <td className="px-3 py-1.5">{t(`profiles.form.modules.${m}`)}</td>
                {OPS.map((key) => (
                  <td key={key} className="px-3 py-1.5 text-center">
                    <input
                      type="checkbox"
                      checked={perms[m][key]}
                      onChange={() => toggle(m, key)}
                      aria-label={t("profiles.form.permissionAria", { operation: t(`profiles.form.operations.${key}`), module: t(`profiles.form.modules.${m}`) })}
                      className="h-3.5 w-3.5"
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && <p className="text-xs text-destructive">{error.message}</p>}

      <div className="flex gap-2 justify-end">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>{t("profiles.form.cancel")}</Button>
        <Button type="submit" size="sm" disabled={isPending || !name} className="gap-1.5">
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          {t("profiles.form.save")}
        </Button>
      </div>
    </form>
  );
}
