import { useState } from "react";
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

const MODULE_LABELS: Record<string, string> = {
  product: "Products",
  projects: "Projects",
  pipeline: "Pipelines",
  backlog: "Planning",
  tasks: "Execution",
  agents: "Agents",
  artifacts: "Artifacts",
  governance: "Governance",
  forgerouter: "ForgeRouter",
  obsidian: "Knowledge Base",
  foundation: "Foundation",
  crons: "Crons",
  deploy: "Deploy Control",
  servers: "Servers",
  database: "Database",
  users: "Users",
  profiles: "Profiles",
};

const SENSITIVE_ACTIONS = [
  ["planning.concept.view", "View concept details"],
  ["planning.concept.edit", "Create and revise concepts"],
  ["planning.concept.submit", "Submit concepts for approval"],
  ["planning.concept.decide", "Legacy concept decision (disabled)"],
  ["planning.blueprint.edit", "Edit System Maps"],
  ["planning.blueprint.approve", "Approve System Maps"],
  ["planning.delivery.authorize", "Authorize delivery planning"],
  ["planning.progress.view", "View project progress and checkpoints"],
  ["planning.progress.manage", "Manage checkpoints and recovery"],
  ["planning.stage.complete", "Complete pipeline stages"],
  ["planning.execution.view", "View execution waves and runner state"],
  ["planning.execution.manage", "Create and manage execution waves"],
  ["planning.execution.release", "Approve execution waves"],
  ["planning.execution.dispatch", "Issue and dispatch work packages"],
  ["planning.execution.cancel", "Cancel and reconcile CLI executions"],
  ["governance.approval.view", "View governed approvals"],
  ["governance.approval.decide", "Decide governed approvals"],
  ["governance.delegation.manage", "Manage Athos delegations"],
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
  const [name, setName] = useState(profile?.name ?? "");
  const [description, setDescription] = useState(profile?.description ?? "");
  const [perms, setPerms] = useState<Record<string, PermRow>>(
    profile ? profileToPerms(profile) : defaultPerms()
  );
  const [actions, setActions] = useState<Record<string, boolean>>(() => Object.fromEntries(
    SENSITIVE_ACTIONS.map(([key]) => [key, profile?.action_permissions?.find((item) => item.action_key === key)?.allowed ?? false])
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

  const OPS: { key: PermOp; label: string }[] = [
    { key: "can_view", label: "View" },
    { key: "can_query", label: "Query" },
    { key: "can_write", label: "Write" },
    { key: "can_delete", label: "Delete" },
  ];

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <Label>Name *</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="E.g. Developer" />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Description</Label>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional description" />
        </div>
      </div>

      <div className="rounded-md border border-border p-3">
        <p className="mb-2 text-sm font-medium">Sensitive command permissions</p>
        <p className="mb-3 text-xs text-muted-foreground">These actions are denied by default and are checked by the backend.</p>
        <div className="grid gap-2 md:grid-cols-2">
          {SENSITIVE_ACTIONS.map(([key, label]) => <label key={key} className="flex items-start gap-2 rounded border p-2 text-xs">
            <input type="checkbox" checked={actions[key]} onChange={() => setActions((value) => ({ ...value, [key]: !value[key] }))} className="mt-0.5 h-3.5 w-3.5" />
            <span><span className="block font-medium">{label}</span><code className="text-[10px] text-muted-foreground">{key}</code></span>
          </label>)}
        </div>
      </div>

      {/* Permissions matrix */}
      <div className="rounded-md border border-border overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-muted/50">
              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Module</th>
              {OPS.map(({ key, label }) => (
                <th key={key} className="px-3 py-2 text-center font-medium text-muted-foreground">
                  <button type="button" className="hover:text-foreground transition-colors" onClick={() => toggleColumn(key)}>
                    {label}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30">
            {MODULES.map((m) => (
              <tr key={m} className="hover:bg-muted/20">
                <td className="px-3 py-1.5 font-mono">{MODULE_LABELS[m] ?? m}</td>
                {OPS.map(({ key }) => (
                  <td key={key} className="px-3 py-1.5 text-center">
                    <input
                      type="checkbox"
                      checked={perms[m][key]}
                      onChange={() => toggle(m, key)}
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
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <Button type="submit" size="sm" disabled={isPending || !name} className="gap-1.5">
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          Save
        </Button>
      </div>
    </form>
  );
}
