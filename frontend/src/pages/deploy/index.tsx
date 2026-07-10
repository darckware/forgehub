import { useState, useEffect, useRef } from "react";
import {
  Activity,
  AlertCircle,
  Box,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  ClipboardCopy,
  Container,
  Folder,
  ExternalLink,
  HardDrive,
  Layers,
  Loader2,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  ScrollText,
  Server,
  Settings2,
  Trash2,
  X,
  Zap,
  AlertTriangle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";
import {
  useInstallations,
  useDockerContainers,
  useDockerVolumes,
  useDockerNetworks,
  useDockerImages,
  useCreateInstallation,
  useUpdateInstallation,
  useDeleteInstallation,
  useRestartContainer,
  useContainerLogs,
  useSyncFromDocker,
  useRemoveContainer,
  useRemoveVolume,
  useRemoveNetwork,
  useRemoveImage,
  useDeployGroups,
  useCreateDeployGroup,
  useUpdateDeployGroup,
  useDeleteDeployGroup,
  type DeployGroup,
  type DeployInstallation,
  type DockerContainer,
  type DockerVolume,
  type DockerNetwork,
  type DockerImage,
  type DeployInstallationCreate,
  type SyncResult,
} from "@/hooks/useDeploy";
import { useProducts } from "@/hooks/useProduct";
import { useQueryClient } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function ContainerStatusBadge({ state, health }: { state: string; health: string | null }) {
  if (state === "running" && health === "healthy") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-600">
        <CheckCircle2 className="h-3 w-3" /> Healthy
      </span>
    );
  }
  if (state === "running" && health === "unhealthy") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-500">
        <AlertCircle className="h-3 w-3" /> Unhealthy
      </span>
    );
  }
  if (state === "running" && health === "starting") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-600">
        <Loader2 className="h-3 w-3 animate-spin" /> Starting
      </span>
    );
  }
  if (state === "running") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-600">
        <Activity className="h-3 w-3" /> Running
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
      <Circle className="h-3 w-3" /> Stopped
    </span>
  );
}

function statusDot(state: string, health: string | null) {
  if (state === "running" && health === "healthy") return "bg-emerald-500";
  if (state === "running" && health === "unhealthy") return "bg-red-500";
  if (state === "running" && health === "starting") return "bg-amber-400 animate-pulse";
  if (state === "running") return "bg-blue-500";
  return "bg-muted-foreground/30";
}

// ---------------------------------------------------------------------------
// Logs modal
// ---------------------------------------------------------------------------

function LogsModal({
  containerName,
  onClose,
}: {
  containerName: string;
  onClose: () => void;
}) {
  const [lines, setLines] = useState(200);
  const { data, isLoading, refetch } = useContainerLogs(containerName, lines);
  const ref = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [data]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex w-full max-w-4xl flex-col rounded-xl border border-border bg-card shadow-2xl" style={{ maxHeight: "85vh" }}>
        <div className="h-1 w-full rounded-t-xl bg-blue-500" />
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <ScrollText className="h-4 w-4 text-blue-500" />
            <span className="font-semibold text-sm">{containerName}</span>
            <span className="text-xs text-muted-foreground">— last {lines} lines</span>
          </div>
          <div className="flex items-center gap-2">
            <select
              className="rounded border border-border bg-background px-2 py-1 text-xs"
              value={lines}
              onChange={(e) => setLines(Number(e.target.value))}
            >
              {[50, 100, 200, 500, 1000].map((n) => (
                <option key={n} value={n}>{n} lines</option>
              ))}
            </select>
            <Button size="sm" variant="ghost" onClick={() => refetch()}>
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
            <Button size="sm" variant="ghost" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <pre
          ref={ref}
          className="flex-1 overflow-auto p-4 text-xs font-mono text-foreground/90 bg-black/20 rounded-b-xl whitespace-pre-wrap break-all"
          style={{ minHeight: "300px" }}
        >
          {isLoading ? "Loading logs..." : data?.logs ?? "No logs available."}
        </pre>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Groups management modal (create / rename / delete)
// ---------------------------------------------------------------------------

function GroupsModal({ groups, onClose }: { groups: DeployGroup[]; onClose: () => void }) {
  const createMut = useCreateDeployGroup();
  const updateMut = useUpdateDeployGroup();
  const deleteMut = useDeleteDeployGroup();

  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [deleting, setDeleting] = useState<DeployGroup | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return false;
    }
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    if (await run(() => createMut.mutateAsync({ name }))) setNewName("");
  };

  const handleRename = async (group: DeployGroup) => {
    const name = editName.trim();
    if (!name || name === group.name) {
      setEditingId(null);
      return;
    }
    if (await run(() => updateMut.mutateAsync({ id: group.id, data: { name } }))) {
      setEditingId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    if (await run(() => deleteMut.mutateAsync(deleting.id))) setDeleting(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex w-full max-w-md flex-col rounded-xl border border-border bg-card shadow-2xl" style={{ maxHeight: "80vh" }}>
        <div className="h-1 w-full rounded-t-xl bg-blue-500" />
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <Settings2 className="h-4 w-4 text-blue-500" />
            <span className="font-semibold text-sm">Groups</span>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Create */}
          <div className="flex gap-2">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), handleCreate())}
              placeholder="New group name"
              className="h-8 text-sm flex-1"
            />
            <Button size="sm" className="h-8" onClick={handleCreate} disabled={createMut.isPending || !newName.trim()}>
              {createMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            </Button>
          </div>

          {error && (
            <p className="text-xs text-red-500 rounded bg-red-500/10 px-3 py-2">{error}</p>
          )}

          {/* Table */}
          {groups.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">No groups created.</p>
          ) : (
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40">
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Name</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground w-24">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {groups.map((g) => (
                    <tr key={g.id} className="hover:bg-muted/20 transition-colors">
                      <td className="px-3 py-2">
                        {editingId === g.id ? (
                          <Input
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") { e.preventDefault(); handleRename(g); }
                              if (e.key === "Escape") setEditingId(null);
                            }}
                            autoFocus
                            className="h-7 text-sm"
                          />
                        ) : (
                          <span className="font-medium">{g.name}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center justify-end gap-1">
                          {editingId === g.id ? (
                            <>
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => handleRename(g)} disabled={updateMut.isPending} title="Save">
                                {updateMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setEditingId(null)} title="Cancel">
                                <X className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          ) : (
                            <>
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => { setEditingId(g.id); setEditName(g.name); }} title="Rename">
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive hover:text-destructive" onClick={() => setDeleting(g)} title="Delete">
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Renaming a group updates its installations. Deleting a group leaves its installations ungrouped.
          </p>
        </div>
      </div>

      <ConfirmDialog
        open={!!deleting}
        title="Delete group"
        description={`Delete group "${deleting?.name}"? Installations in this group will become ungrouped.`}
        confirmLabel="Delete"
        loading={deleteMut.isPending}
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Installation form (create / edit)
// ---------------------------------------------------------------------------

interface Link { label: string; url: string }

// Parse live docker ps ports ("0.0.0.0:8000->8000/tcp, ...") into ["8000:8000"]
// — same normalization the backend sync endpoint applies.
function parseLivePorts(raw: string | undefined): string[] {
  if (!raw) return [];
  const out: string[] = [];
  for (const seg of raw.split(",")) {
    const s = seg.trim();
    if (!s.includes("->")) continue;
    const [hostPart, containerPart] = s.split("->");
    const hostPort = hostPart.split(":").pop() ?? "";
    const containerPort = containerPart.split("/")[0];
    const mapping = `${hostPort}:${containerPort}`;
    if (hostPort && !out.includes(mapping)) out.push(mapping);
  }
  return out;
}

function defaultForm(): DeployInstallationCreate {
  return {
    name: "",
    description: "",
    group_name: "",
    order_index: 0,
    container_name: "",
    compose_file: "",
    restart_command: "",
    ports: [],
    links: [],
    notes: "",
    product_id: null,
  };
}

function InstallationForm({
  initial,
  prefillData,
  onSave,
  onCancel,
  isSaving,
  containers,
  volumes,
  networks,
  groups,
  onManageGroups,
}: {
  initial?: DeployInstallation;
  prefillData?: Partial<DeployInstallationCreate>;
  onSave: (data: DeployInstallationCreate) => void;
  onCancel: () => void;
  isSaving: boolean;
  containers: DockerContainer[];
  volumes: DockerVolume[];
  networks: DockerNetwork[];
  groups: DeployGroup[];
  onManageGroups: () => void;
}) {
  const { data: products = [] } = useProducts();
  const [form, setForm] = useState<DeployInstallationCreate>(() => {
    if (initial) {
      // Fill gaps with live Docker data from the server (ports, restart
      // command) — sync-created records start with these fields empty.
      const live = containers.find((c) => c.name === initial.container_name);
      return {
        name: initial.name,
        description: initial.description ?? "",
        group_name: initial.group_name ?? "",
        order_index: initial.order_index,
        container_name: initial.container_name ?? "",
        compose_file: initial.compose_file ?? "",
        restart_command:
          initial.restart_command ||
          (initial.container_name ? `docker restart ${initial.container_name}` : ""),
        ports: initial.ports?.length ? initial.ports : parseLivePorts(live?.ports),
        links: (initial.links as Link[] | null) ?? [],
        notes: initial.notes ?? "",
        product_id: initial.product_id ?? null,
      };
    }
    return { ...defaultForm(), ...prefillData };
  });

  const [portInput, setPortInput] = useState("");
  const [linkLabel, setLinkLabel] = useState("");
  const [linkUrl, setLinkUrl] = useState("");

  const f = (field: keyof DeployInstallationCreate, value: unknown) =>
    setForm((p) => ({ ...p, [field]: value }));

  // Auto-fill restart command when container name is chosen
  const handleContainerChange = (name: string) => {
    f("container_name", name);
    if (name && !form.restart_command) {
      f("restart_command", `docker restart ${name}`);
    }
  };

  const addPort = () => {
    const v = portInput.trim();
    if (v) {
      f("ports", [...(form.ports ?? []), v]);
      setPortInput("");
    }
  };

  const removePort = (i: number) =>
    f("ports", (form.ports ?? []).filter((_, idx) => idx !== i));

  const addLink = () => {
    if (linkLabel && linkUrl) {
      f("links", [...((form.links as Link[] | null) ?? []), { label: linkLabel, url: linkUrl }]);
      setLinkLabel("");
      setLinkUrl("");
    }
  };

  const removeLink = (i: number) =>
    f("links", ((form.links as Link[] | null) ?? []).filter((_, idx) => idx !== i));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      ...form,
      ports: form.ports?.filter(Boolean) ?? null,
      links: (form.links as Link[] | null)?.filter((l) => l.label && l.url) ?? null,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Name + group row */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Name *</Label>
          <Input
            value={form.name}
            onChange={(e) => f("name", e.target.value)}
            placeholder="ForgeHub Backend"
            required
            className="h-8 text-sm"
          />
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Group</Label>
            <button
              type="button"
              onClick={onManageGroups}
              className="text-muted-foreground hover:text-foreground"
              title="Manage groups"
            >
              <Settings2 className="h-3.5 w-3.5" />
            </button>
          </div>
          <select
            className="h-8 w-full rounded-md border border-border bg-background px-3 text-sm"
            value={form.group_name ?? ""}
            onChange={(e) => f("group_name", e.target.value || null)}
          >
            <option value="">— no group —</option>
            {/* Keep a legacy group_name selectable even if its group row is gone */}
            {form.group_name && !groups.some((g) => g.name === form.group_name) && (
              <option value={form.group_name}>{form.group_name}</option>
            )}
            {groups.map((g) => (
              <option key={g.id} value={g.name}>{g.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-xs">Description</Label>
        <Input
          value={form.description ?? ""}
          onChange={(e) => f("description", e.target.value)}
          placeholder="Brief service description"
          className="h-8 text-sm"
        />
      </div>

      {/* Container + order */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Docker Container</Label>
          <select
            className="h-8 w-full rounded-md border border-border bg-background px-3 text-sm"
            value={form.container_name ?? ""}
            onChange={(e) => handleContainerChange(e.target.value)}
          >
            <option value="">— none —</option>
            {containers.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Order</Label>
          <Input
            type="number"
            value={form.order_index}
            onChange={(e) => f("order_index", Number(e.target.value))}
            className="h-8 text-sm"
          />
        </div>
      </div>

      {/* Live Docker info: all data of the selected container */}
      {form.container_name && (() => {
        const live = containers.find((c) => c.name === form.container_name);
        const mounts = volumes.filter((v) => v.containers.includes(form.container_name!));
        const vols = mounts.filter((v) => v.driver !== "bind");
        const sharedFolders = mounts.filter((v) => v.driver === "bind");
        const nets = networks.filter((n) => n.containers.some((nc) => nc.name === form.container_name));
        return (
          <div className="rounded-md border border-border bg-muted/20 px-3 py-2 space-y-1.5">
            {live ? (
              <>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-foreground shrink-0">
                    <Container className="h-3 w-3 text-blue-500" /> Container:
                  </span>
                  <span className="text-[10px] font-mono">{live.name}</span>
                  {live.id && <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono" title="Container ID">{live.id}</span>}
                  <ContainerStatusBadge state={live.state} health={live.health} />
                </div>
                <div className="flex items-start gap-2 flex-wrap">
                  <span className="text-xs font-medium text-foreground shrink-0">Image:</span>
                  <span className="text-[10px] font-mono text-muted-foreground break-all">{live.image}</span>
                </div>
                <div className="flex items-start gap-2 flex-wrap">
                  <span className="text-xs font-medium text-foreground shrink-0">Status:</span>
                  <span className="text-[10px] font-mono text-muted-foreground">{live.status}</span>
                </div>
                {live.ports && (
                  <div className="flex items-start gap-2 flex-wrap">
                    <span className="text-xs font-medium text-foreground shrink-0">Ports:</span>
                    <span className="text-[10px] font-mono text-muted-foreground break-all">{live.ports}</span>
                  </div>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground italic">Container offline or not found on the host.</p>
            )}
            <div className="flex items-start gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1 text-xs font-medium text-foreground shrink-0">
                <HardDrive className="h-3 w-3 text-violet-500" /> Volumes:
              </span>
              {vols.length > 0 ? (
                vols.map((v) => (
                  <span key={v.name} className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono break-all" title={v.mountpoint}>
                    {v.name}
                  </span>
                ))
              ) : (
                <span className="text-xs text-muted-foreground italic">none</span>
              )}
            </div>
            <div className="flex items-start gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1 text-xs font-medium text-foreground shrink-0">
                <Folder className="h-3 w-3 text-amber-500" /> Folders:
              </span>
              {sharedFolders.length > 0 ? (
                sharedFolders.map((v) => (
                  <span key={v.name} className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono break-all">
                    {v.name}
                  </span>
                ))
              ) : (
                <span className="text-xs text-muted-foreground italic">none</span>
              )}
            </div>
            <div className="flex items-start gap-2 flex-wrap">
              <span className="inline-flex items-center gap-1 text-xs font-medium text-foreground shrink-0">
                <Network className="h-3 w-3 text-amber-500" /> Network:
              </span>
              {nets.length > 0 ? (
                nets.map((n) => {
                  const ip = n.containers.find((nc) => nc.name === form.container_name)?.ipv4;
                  return (
                    <span key={n.id} className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono">
                      {n.name}
                      {ip && <span className="text-muted-foreground"> · {ip}</span>}
                    </span>
                  );
                })
              ) : (
                <span className="text-xs text-muted-foreground italic">none</span>
              )}
            </div>
          </div>
        );
      })()}

      {/* Restart command */}
      <div className="space-y-1">
        <Label className="text-xs">Restart command</Label>
        <Input
          value={form.restart_command ?? ""}
          onChange={(e) => f("restart_command", e.target.value)}
          placeholder="docker restart container-name"
          className="h-8 text-sm font-mono"
        />
      </div>

      {/* Compose file */}
      <div className="space-y-1">
        <Label className="text-xs">docker-compose.yml path</Label>
        <Input
          value={form.compose_file ?? ""}
          onChange={(e) => f("compose_file", e.target.value)}
          placeholder="/root/project/forgehub/docker-compose.yml"
          className="h-8 text-sm font-mono"
        />
      </div>

      {/* Product association */}
      <div className="space-y-1">
        <Label className="text-xs">ForgeHub Product (optional)</Label>
        <select
          className="h-8 w-full rounded-md border border-border bg-background px-3 text-sm"
          value={form.product_id ?? ""}
          onChange={(e) => f("product_id", e.target.value || null)}
        >
          <option value="">— none —</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* Ports */}
      <div className="space-y-1">
        <Label className="text-xs">Exposed ports</Label>
        <div className="flex gap-2">
          <Input
            value={portInput}
            onChange={(e) => setPortInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addPort())}
            placeholder="8000:8000"
            className="h-8 text-sm font-mono flex-1"
          />
          <Button type="button" size="sm" variant="outline" onClick={addPort} className="h-8">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        {(form.ports ?? []).length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {(form.ports ?? []).map((p, i) => (
              <span key={i} className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs font-mono">
                {p}
                <button type="button" onClick={() => removePort(i)} className="text-muted-foreground hover:text-foreground">
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Links */}
      <div className="space-y-1">
        <Label className="text-xs">Links</Label>
        <div className="flex gap-2">
          <Input
            value={linkLabel}
            onChange={(e) => setLinkLabel(e.target.value)}
            placeholder="Label"
            className="h-8 text-sm w-28"
          />
          <Input
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addLink())}
            placeholder="http://localhost:8000"
            className="h-8 text-sm flex-1"
          />
          <Button type="button" size="sm" variant="outline" onClick={addLink} className="h-8">
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        {((form.links as Link[] | null) ?? []).length > 0 && (
          <div className="space-y-1 pt-1">
            {((form.links as Link[] | null) ?? []).map((l, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="w-20 truncate font-medium">{l.label}</span>
                <span className="flex-1 truncate text-muted-foreground font-mono">{l.url}</span>
                <button type="button" onClick={() => removeLink(i)} className="text-muted-foreground hover:text-foreground">
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Notes */}
      <div className="space-y-1">
        <Label className="text-xs">Notes</Label>
        <Textarea
          value={form.notes ?? ""}
          onChange={(e) => f("notes", e.target.value)}
          placeholder="Notes, credentials, references..."
          rows={2}
          className="text-sm resize-none"
        />
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={isSaving}>
          {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Save className="h-3.5 w-3.5 mr-1" />}
          {initial ? "Save" : "Register"}
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Installation card (row in the list)
// ---------------------------------------------------------------------------

function InstallCard({
  inst,
  liveContainers,
  volumes,
  networks,
  images,
  onEdit,
  onDelete,
  onRestart,
  onLogs,
  restarting,
}: {
  inst: DeployInstallation;
  liveContainers: DockerContainer[];
  volumes: DockerVolume[];
  networks: DockerNetwork[];
  images: DockerImage[];
  onEdit: () => void;
  onDelete: () => void;
  onRestart: () => void;
  onLogs: () => void;
  restarting: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const live = liveContainers.find((c) => c.name === inst.container_name);

  const links = (inst.links as { label: string; url: string }[] | null) ?? [];
  const ports = inst.ports ?? [];
  const containerVolumes = inst.container_name
    ? volumes.filter((v) => v.containers.includes(inst.container_name!))
    : [];
  const containerNetworks = inst.container_name
    ? networks.filter((n) => n.containers.some((nc) => nc.name === inst.container_name))
    : [];
  // `docker ps`'s Image column is "repo:tag" (or a bare ID for untagged
  // images) -- match against either form to associate the running
  // container with its full entry (size, in-use/dangling status) from the
  // Images tab.
  const containerImage = live?.image
    ? images.find((img) => `${img.repository}:${img.tag}` === live.image || img.id === live.image)
    : undefined;

  return (
    <div className={cn(
      "rounded-lg border border-border bg-card transition-colors",
      live?.state === "running" ? "border-l-2 border-l-emerald-500/60" : "border-l-2 border-l-muted-foreground/20"
    )}>
      {/* Header row */}
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          type="button"
          onClick={() => setExpanded((p) => !p)}
          className="text-muted-foreground hover:text-foreground"
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>

        {/* Status dot */}
        <span className={cn("h-2 w-2 rounded-full shrink-0", live ? statusDot(live.state, live.health) : "bg-muted-foreground/20")} />

        {/* Name + group */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm truncate">{inst.name}</span>
            {inst.group_name && (
              <Badge variant="outline" className="text-[10px] py-0 h-4">{inst.group_name}</Badge>
            )}
            {inst.product_name && (
              <span className="inline-flex items-center gap-0.5 rounded bg-blue-500/10 px-1.5 py-0 text-[10px] text-blue-600 font-medium h-4">
                <Box className="h-2 w-2" /> {inst.product_name}
              </span>
            )}
          </div>
          {inst.description && (
            <p className="text-xs text-muted-foreground truncate">{inst.description}</p>
          )}
        </div>

        {/* Live status */}
        {live ? (
          <ContainerStatusBadge state={live.state} health={live.health} />
        ) : inst.container_name ? (
          <span className="text-xs text-muted-foreground italic">offline</span>
        ) : null}

        {/* Quick links */}
        {links.slice(0, 2).map((l) => (
          <a
            key={l.url}
            href={l.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground"
            title={l.label}
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ))}

        {/* Actions */}
        <div className="flex items-center gap-1">
          {inst.container_name && (
            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onLogs} title="Ver logs">
              <ScrollText className="h-3.5 w-3.5" />
            </Button>
          )}
          {inst.container_name && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 w-7 p-0"
              onClick={onRestart}
              disabled={restarting}
              title="Restart container"
            >
              {restarting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCcw className="h-3.5 w-3.5" />
              )}
            </Button>
          )}
          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onEdit} title="Container registration (Docker data)">
            <Container className="h-3.5 w-3.5" />
          </Button>
          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-destructive hover:text-destructive" onClick={onDelete} title="Remove">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border px-4 py-3 space-y-2">
          {inst.product_name && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-foreground">Product:</span>
              <span className="inline-flex items-center gap-1 rounded bg-blue-500/10 px-2 py-0.5 text-xs text-blue-600 font-medium">
                <Box className="h-2.5 w-2.5" /> {inst.product_name}
              </span>
            </div>
          )}
          {live && (
            <div className="flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
              <Container className="h-3.5 w-3.5 shrink-0 text-blue-500" />
              <span className="font-medium text-foreground">Container:</span>
              <span className="font-mono">{live.name}</span>
              {live.id && <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">{live.id}</span>}
              <span>{live.status}</span>
            </div>
          )}

          {live?.image && (
            <div className="flex items-center gap-2 flex-wrap">
              <Layers className="h-3.5 w-3.5 shrink-0 text-cyan-500" />
              <span className="text-xs font-medium text-foreground">Image:</span>
              {containerImage ? (
                <>
                  <span className="rounded bg-muted px-2 py-0.5 text-xs font-mono">
                    {containerImage.repository}:{containerImage.tag}
                  </span>
                  <span className="text-xs text-muted-foreground">{containerImage.size}</span>
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-600">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> In use
                  </span>
                </>
              ) : (
                <span className="rounded bg-muted px-2 py-0.5 text-xs font-mono text-muted-foreground">{live.image}</span>
              )}
            </div>
          )}

          {containerVolumes.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <HardDrive className="h-3.5 w-3.5 shrink-0 text-violet-500" />
              <span className="text-xs font-medium text-foreground">Volumes:</span>
              {containerVolumes.map((v) => (
                <span key={v.name} className="rounded bg-muted px-2 py-0.5 text-xs font-mono" title={v.mountpoint}>
                  {v.name}
                </span>
              ))}
            </div>
          )}

          {containerNetworks.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <Network className="h-3.5 w-3.5 shrink-0 text-amber-500" />
              <span className="text-xs font-medium text-foreground">Networks:</span>
              {containerNetworks.map((n) => {
                const ip = n.containers.find((nc) => nc.name === inst.container_name)?.ipv4;
                return (
                  <span key={n.id} className="rounded bg-muted px-2 py-0.5 text-xs font-mono">
                    {n.name}
                    {ip && <span className="text-muted-foreground"> · {ip}</span>}
                  </span>
                );
              })}
            </div>
          )}

          {ports.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-foreground">Ports:</span>
              {ports.map((p) => (
                <span key={p} className="rounded bg-muted px-2 py-0.5 text-xs font-mono">{p}</span>
              ))}
              {live?.ports && !ports.length && (
                <span className="text-xs font-mono text-muted-foreground">{live.ports}</span>
              )}
            </div>
          )}
          {!ports.length && live?.ports && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-foreground">Ports (live):</span>
              <span className="text-xs font-mono text-muted-foreground">{live.ports}</span>
            </div>
          )}

          {links.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-foreground">Links:</span>
              {links.map((l) => (
                <a
                  key={l.url}
                  href={l.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs text-blue-500 hover:underline"
                >
                  <ExternalLink className="h-2.5 w-2.5" />
                  {l.label}
                </a>
              ))}
            </div>
          )}

          {inst.restart_command && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-foreground">Restart:</span>
              <code className="text-xs bg-muted rounded px-2 py-0.5 font-mono flex-1">{inst.restart_command}</code>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(inst.restart_command!)}
                className="text-muted-foreground hover:text-foreground"
                title="Copy command"
              >
                <ClipboardCopy className="h-3 w-3" />
              </button>
            </div>
          )}

          {inst.compose_file && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-foreground">Compose:</span>
              <code className="text-xs text-muted-foreground font-mono">{inst.compose_file}</code>
            </div>
          )}

          {inst.notes && (
            <p className="text-xs text-muted-foreground whitespace-pre-wrap rounded bg-muted/50 px-3 py-2">
              {inst.notes}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live Docker container table
// ---------------------------------------------------------------------------

function LiveContainersTab({
  containers,
  installations,
  onRegister,
  onOpenInstance,
}: {
  containers: DockerContainer[];
  installations: DeployInstallation[];
  onRegister: (c: DockerContainer) => void;
  onOpenInstance: (inst: DeployInstallation) => void;
}) {
  const { isLoading, isError, refetch, isFetching } = useDockerContainers();
  const removeMut = useRemoveContainer();
  const [confirmRemove, setConfirmRemove] = useState<DockerContainer | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const handleRemove = async () => {
    if (!confirmRemove) return;
    setRemoveError(null);
    try {
      await removeMut.mutateAsync(confirmRemove.name);
      setConfirmRemove(null);
    } catch (err) {
      setConfirmRemove(null);
      setRemoveError(err instanceof Error ? err.message : String(err));
    }
  };

  if (isError) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 flex items-start gap-3">
        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
        <div className="text-sm">
          <p className="font-medium">Host-bridge did not respond</p>
          <p className="text-muted-foreground text-xs mt-1">
            Reinicie o host-bridge para ativar o controle Docker ao vivo. Execute no terminal:
          </p>
          <code className="mt-2 block bg-muted rounded px-3 py-2 text-xs font-mono">
            kill $(pgrep -f "host-bridge") ; cd /root/project/forgehub/host-bridge ; source /root/project/forgehub/.env ; nohup /usr/local/lib/hermes-agent/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8910 &gt; /tmp/host-bridge.log 2&gt;&amp;1 &amp;
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{containers.length} container(s) no host</p>
        <Button size="sm" variant="ghost" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={cn("h-3.5 w-3.5 mr-1", isFetching && "animate-spin")} /> Refresh
        </Button>
      </div>
      {removeError && (
        <p className="text-xs text-red-500 rounded bg-red-500/10 px-3 py-2">{removeError}</p>
      )}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading containers...
        </div>
      ) : (
        <div className="space-y-1">
          {containers.map((c) => {
            const inst = installations.find((i) => i.container_name === c.name);
            const removing = removeMut.isPending && removeMut.variables === c.name;
            return (
              <div key={c.id || c.name} className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5">
                <span className={cn("h-2 w-2 rounded-full shrink-0", statusDot(c.state, c.health))} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-medium">{c.name}</span>
                    <ContainerStatusBadge state={c.state} health={c.health} />
                    {c.id && <span className="text-[10px] text-muted-foreground font-mono">{c.id}</span>}
                  </div>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span className="text-xs text-muted-foreground font-mono truncate">{c.image}</span>
                    {c.ports && <span className="text-xs text-muted-foreground font-mono truncate">{c.ports}</span>}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 w-7 p-0 shrink-0"
                  onClick={() => (inst ? onOpenInstance(inst) : onRegister(c))}
                  title={inst ? `Open instance "${inst.name}"` : "Register instance"}
                >
                  <Container className="h-3.5 w-3.5" />
                </Button>
                {!inst && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0 shrink-0 text-destructive hover:text-destructive"
                    onClick={() => setConfirmRemove(c)}
                    disabled={removing}
                    title="Delete container"
                  >
                    {removing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmRemove}
        title="Delete container"
        description={`Remove the container "${confirmRemove?.name}" from Docker and from the installation database? This action cannot be undone (volumes are not removed).`}
        confirmLabel="Delete"
        loading={removeMut.isPending}
        onConfirm={handleRemove}
        onCancel={() => setConfirmRemove(null)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Volumes tab
// ---------------------------------------------------------------------------

function VolumesTab({
  installations,
  liveContainers,
  onOpenInstance,
  onRegister,
}: {
  installations: DeployInstallation[];
  liveContainers: DockerContainer[];
  onOpenInstance: (inst: DeployInstallation) => void;
  onRegister: (c: DockerContainer) => void;
}) {
  const { data: volumes = [], isLoading, isError, refetch, isFetching } = useDockerVolumes();
  const removeVolMut = useRemoveVolume();
  const [confirmRemoveVol, setConfirmRemoveVol] = useState<string | null>(null);
  const [removeVolError, setRemoveVolError] = useState<string | null>(null);

  const handleRemoveVolume = async () => {
    if (!confirmRemoveVol) return;
    setRemoveVolError(null);
    try {
      await removeVolMut.mutateAsync(confirmRemoveVol);
      setConfirmRemoveVol(null);
    } catch (err) {
      setConfirmRemoveVol(null);
      setRemoveVolError(err instanceof Error ? err.message : String(err));
    }
  };

  if (isError) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 flex items-start gap-3">
        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
        <p className="text-sm text-muted-foreground">Host-bridge offline — volumes unavailable.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{volumes.length} volume(s)</p>
        <Button size="sm" variant="ghost" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={cn("h-3.5 w-3.5 mr-1", isFetching && "animate-spin")} /> Refresh
        </Button>
      </div>
      {removeVolError && (
        <p className="text-xs text-red-500 rounded bg-red-500/10 px-3 py-2">{removeVolError}</p>
      )}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading volumes...
        </div>
      ) : volumes.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">No volumes found.</div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Driver</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Scope</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Mountpoint</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Containers</th>
                <th className="px-4 py-2.5 w-12" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {volumes.map((v) => {
                const usedByRunning = v.containers.some((c) =>
                  liveContainers.some((lc) => lc.name === c && lc.state === "running")
                );
                return (
                <tr key={v.name} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full shrink-0",
                          usedByRunning ? "bg-emerald-500" : "bg-muted-foreground/30"
                        )}
                        title={usedByRunning ? "Active — in use by a running container" : "Inactive — no running container"}
                      />
                      {v.driver === "bind" ? (
                        <Folder className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                      ) : (
                        <HardDrive className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                      )}
                      <span className="font-mono text-xs font-medium break-all">{v.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge variant="outline" className="text-[10px] font-mono">{v.driver}</Badge>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{v.scope}</td>
                  <td className="px-4 py-2.5">
                    <code className="text-[10px] text-muted-foreground break-all">{v.mountpoint}</code>
                  </td>
                  <td className="px-4 py-2.5">
                    {v.containers.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {v.containers.map((cname) => {
                          const inst = installations.find((i) => i.container_name === cname);
                          const live = liveContainers.find((lc) => lc.name === cname);
                          return (
                            <button
                              key={cname}
                              type="button"
                              onClick={() => {
                                if (inst) onOpenInstance(inst);
                                else if (live) onRegister(live);
                              }}
                              disabled={!inst && !live}
                              className={cn(
                                "inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono",
                                (inst || live) ? "hover:bg-accent hover:text-foreground transition-colors" : "cursor-default"
                              )}
                              title={inst ? `Open instance "${inst.name}"` : live ? "Register instance" : undefined}
                            >
                              <Container className="h-3 w-3 text-blue-500" />
                              {cname}
                            </button>
                          );
                        })}
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground/50 italic">—</span>
                    )}
                  </td>
                  <td className="px-2 py-2.5">
                    {v.driver !== "bind" &&
                      !v.containers.some((c) => installations.some((i) => i.container_name === c)) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                        onClick={() => setConfirmRemoveVol(v.name)}
                        disabled={removeVolMut.isPending && removeVolMut.variables === v.name}
                        title="Delete volume"
                      >
                        {removeVolMut.isPending && removeVolMut.variables === v.name ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmRemoveVol}
        title="Delete volume"
        description={`Remove the volume "${confirmRemoveVol}" from Docker? Data stored in it will be lost. This action cannot be undone.`}
        confirmLabel="Delete"
        loading={removeVolMut.isPending}
        onConfirm={handleRemoveVolume}
        onCancel={() => setConfirmRemoveVol(null)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Networks tab
// ---------------------------------------------------------------------------

const PREDEFINED_NETWORKS = ["bridge", "host", "none"];

function NetworksTab({
  installations,
  liveContainers,
  onOpenInstance,
  onRegister,
}: {
  installations: DeployInstallation[];
  liveContainers: DockerContainer[];
  onOpenInstance: (inst: DeployInstallation) => void;
  onRegister: (c: DockerContainer) => void;
}) {
  const { data: networks = [], isLoading, isError, refetch, isFetching } = useDockerNetworks();
  const [expanded, setExpanded] = useState<string | null>(null);
  const removeNetMut = useRemoveNetwork();
  const [confirmRemoveNet, setConfirmRemoveNet] = useState<string | null>(null);
  const [removeNetError, setRemoveNetError] = useState<string | null>(null);

  const handleRemoveNetwork = async () => {
    if (!confirmRemoveNet) return;
    setRemoveNetError(null);
    try {
      await removeNetMut.mutateAsync(confirmRemoveNet);
      setConfirmRemoveNet(null);
    } catch (err) {
      setConfirmRemoveNet(null);
      setRemoveNetError(err instanceof Error ? err.message : String(err));
    }
  };

  if (isError) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 flex items-start gap-3">
        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
        <p className="text-sm text-muted-foreground">Host-bridge offline — networks unavailable.</p>
      </div>
    );
  }

  const driverColor: Record<string, string> = {
    bridge: "text-blue-600 bg-blue-500/10",
    host: "text-violet-600 bg-violet-500/10",
    overlay: "text-emerald-600 bg-emerald-500/10",
    macvlan: "text-amber-600 bg-amber-500/10",
    none: "text-muted-foreground bg-muted",
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{networks.length} network(s)</p>
        <Button size="sm" variant="ghost" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={cn("h-3.5 w-3.5 mr-1", isFetching && "animate-spin")} /> Refresh
        </Button>
      </div>
      {removeNetError && (
        <p className="text-xs text-red-500 rounded bg-red-500/10 px-3 py-2">{removeNetError}</p>
      )}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading networks...
        </div>
      ) : (
        <div className="space-y-1.5">
          {networks.map((n) => {
            const isOpen = expanded === n.id;
            const active = n.containers.some((nc) =>
              liveContainers.some((lc) => lc.name === nc.name && lc.state === "running")
            );
            const hasInstance = n.containers.some((nc) =>
              installations.some((i) => i.container_name === nc.name)
            );
            const removing = removeNetMut.isPending && removeNetMut.variables === n.name;
            return (
              <div key={n.id} className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="flex items-center gap-3 px-4 py-2.5">
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : n.id)}
                    className="flex flex-1 min-w-0 items-center gap-3 hover:opacity-80 transition-opacity text-left"
                  >
                    {isOpen
                      ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
                    <span
                      className={cn("h-2 w-2 rounded-full shrink-0", active ? "bg-emerald-500" : "bg-muted-foreground/30")}
                      title={active ? "Ativa — container rodando conectado" : "Inativa — sem container rodando"}
                    />
                    <Network className="h-3.5 w-3.5 shrink-0 text-violet-500" />
                    <span className="font-mono text-sm font-medium flex-1">{n.name}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{n.id}</span>
                    <span className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-medium",
                      driverColor[n.driver] ?? "text-muted-foreground bg-muted"
                    )}>{n.driver}</span>
                    <Badge variant="outline" className="text-[10px]">{n.scope}</Badge>
                    {n.internal && <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-600">internal</Badge>}
                    {n.containers.length > 0 && (
                      <span className="text-xs text-muted-foreground">{n.containers.length} container(s)</span>
                    )}
                  </button>
                  {!hasInstance && !PREDEFINED_NETWORKS.includes(n.name) && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0 shrink-0 text-destructive hover:text-destructive"
                      onClick={() => setConfirmRemoveNet(n.name)}
                      disabled={removing}
                      title="Delete network"
                    >
                      {removing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                    </Button>
                  )}
                </div>
                {isOpen && (
                  <div className="border-t border-border px-4 py-3 space-y-3 bg-muted/10">
                    {n.subnets.length > 0 && (
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-medium text-foreground w-20">Subnets</span>
                        <div className="flex gap-2 flex-wrap">
                          {n.subnets.map((s) => (
                            <code key={s} className="rounded bg-muted px-2 py-0.5 text-xs font-mono">{s}</code>
                          ))}
                        </div>
                      </div>
                    )}
                    {n.containers.length > 0 && (
                      <div>
                        <span className="text-xs font-medium text-foreground">Containers conectados</span>
                        <div className="mt-1.5 rounded border border-border overflow-hidden">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="bg-muted/40 border-b border-border">
                                <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Container</th>
                                <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">IPv4</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                              {n.containers.map((c, i) => {
                                const inst = installations.find((inst) => inst.container_name === c.name);
                                const live = liveContainers.find((lc) => lc.name === c.name);
                                return (
                                  <tr key={i} className="hover:bg-muted/20">
                                    <td className="px-3 py-1.5">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          if (inst) onOpenInstance(inst);
                                          else if (live) onRegister(live);
                                        }}
                                        disabled={!inst && !live}
                                        className={cn(
                                          "inline-flex items-center gap-1.5 font-mono",
                                          (inst || live) ? "hover:text-blue-500 transition-colors" : "cursor-default"
                                        )}
                                        title={inst ? `Open instance "${inst.name}"` : live ? "Register instance" : undefined}
                                      >
                                        <Container className="h-3 w-3 text-blue-500" />
                                        {c.name}
                                      </button>
                                    </td>
                                    <td className="px-3 py-1.5 font-mono text-muted-foreground">{c.ipv4 || "—"}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {n.containers.length === 0 && n.subnets.length === 0 && (
                      <p className="text-xs text-muted-foreground italic">No containers or subnets configured.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <ConfirmDialog
        open={!!confirmRemoveNet}
        title="Delete network"
        description={`Remove the network "${confirmRemoveNet}" from Docker? This action cannot be undone.`}
        confirmLabel="Delete"
        loading={removeNetMut.isPending}
        onConfirm={handleRemoveNetwork}
        onCancel={() => setConfirmRemoveNet(null)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Images tab
// ---------------------------------------------------------------------------

function ImagesTab() {
  const { data: images = [], isLoading, isError, refetch, isFetching } = useDockerImages();
  const removeImgMut = useRemoveImage();
  const [confirmRemoveImg, setConfirmRemoveImg] = useState<string | null>(null);
  const [removeImgError, setRemoveImgError] = useState<string | null>(null);

  const unusedCount = images.filter((i) => !i.in_use).length;

  const handleRemoveImage = async () => {
    if (!confirmRemoveImg) return;
    setRemoveImgError(null);
    try {
      await removeImgMut.mutateAsync(confirmRemoveImg);
      setConfirmRemoveImg(null);
    } catch (err) {
      setConfirmRemoveImg(null);
      setRemoveImgError(err instanceof Error ? err.message : String(err));
    }
  };

  if (isError) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 flex items-start gap-3">
        <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
        <p className="text-sm text-muted-foreground">Host-bridge offline — images unavailable.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {images.length} image(s){unusedCount > 0 && ` · ${unusedCount} unused`}
        </p>
        <Button size="sm" variant="ghost" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={cn("h-3.5 w-3.5 mr-1", isFetching && "animate-spin")} /> Refresh
        </Button>
      </div>
      {removeImgError && (
        <p className="text-xs text-red-500 rounded bg-red-500/10 px-3 py-2">{removeImgError}</p>
      )}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading images...
        </div>
      ) : images.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">No images found.</div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Repository</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Tag</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">ID</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Tamanho</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Criada</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-2.5 w-12" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {images.map((img) => {
                // Two repo:tag rows can share the same underlying image ID
                // (e.g. one re-tagged from the other) -- Docker refuses
                // `docker rmi <id>` in that case ("referenced in multiple
                // repositories"), so deletion always targets the specific
                // tag, never the bare ID. Dangling images have no tag, so
                // the ID is the only valid reference for those.
                const ref = img.dangling ? img.id : `${img.repository}:${img.tag}`;
                const removing = removeImgMut.isPending && removeImgMut.variables === ref;
                return (
                  <tr key={ref} className="hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <Layers className="h-3.5 w-3.5 shrink-0 text-cyan-500" />
                        <span className="font-mono text-xs font-medium break-all">{img.repository}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant="outline" className="text-[10px] font-mono">{img.tag}</Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <code className="text-[10px] text-muted-foreground">{img.id}</code>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{img.size}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{img.created_since}</td>
                    <td className="px-4 py-2.5">
                      {img.dangling ? (
                        <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-600 bg-amber-500/10">
                          Dangling
                        </Badge>
                      ) : img.in_use ? (
                        <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-emerald-600">
                          <span className="h-2 w-2 rounded-full bg-emerald-500" /> Em uso
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground">
                          <span className="h-2 w-2 rounded-full bg-muted-foreground/30" /> Unused
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2.5">
                      {!img.in_use && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                          onClick={() => setConfirmRemoveImg(ref)}
                          disabled={removing}
                          title="Delete image"
                        >
                          {removing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmRemoveImg}
        title="Delete image"
        description={`Remove the image "${confirmRemoveImg}" from Docker? This action cannot be undone.`}
        confirmLabel="Delete"
        loading={removeImgMut.isPending}
        onConfirm={handleRemoveImage}
        onCancel={() => setConfirmRemoveImg(null)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DeployPage() {
  const qc = useQueryClient();
  const { data: installations = [], isLoading: loadingInstall } = useInstallations();
  const { data: groups = [] } = useDeployGroups();
  const { data: containers = [], isError: containersOffline } = useDockerContainers();
  const { data: volumes = [], isError: volumesOffline } = useDockerVolumes();
  const { data: networks = [], isError: networksOffline } = useDockerNetworks();
  const { data: images = [], isError: imagesOffline } = useDockerImages();
  const bridgeOffline = containersOffline;

  const createMut = useCreateInstallation();
  const updateMut = useUpdateInstallation();
  const deleteMut = useDeleteInstallation();
  const restartMut = useRestartContainer();
  const syncMut = useSyncFromDocker();

  const [activeTab, setActiveTab] = useState("installations");
  const [showForm, setShowForm] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [logsContainer, setLogsContainer] = useState<string | null>(null);
  const [restartingId, setRestartingId] = useState<string | null>(null);
  const [confirmRestart, setConfirmRestart] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<Partial<DeployInstallationCreate> | null>(null);
  const [showGroupsModal, setShowGroupsModal] = useState(false);

  const editingInst = editingId ? installations.find((i) => i.id === editingId) : undefined;
  const deletingInst = deletingId ? installations.find((i) => i.id === deletingId) : undefined;

  // Group installations
  const grouped = installations.reduce<Record<string, DeployInstallation[]>>((acc, inst) => {
    const g = inst.group_name ?? "Sem grupo";
    (acc[g] ??= []).push(inst);
    return acc;
  }, {});

  const handleSave = async (data: DeployInstallationCreate) => {
    if (editingId) {
      await updateMut.mutateAsync({ id: editingId, data });
      setEditingId(null);
    } else {
      await createMut.mutateAsync(data);
      setShowForm(false);
      setPrefill(null);
    }
  };

  const handleDelete = async () => {
    if (!deletingId) return;
    try {
      await deleteMut.mutateAsync(deletingId);
      setDeletingId(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Error removing installation: ${msg}`);
      setDeletingId(null);
    }
  };

  const handleRestart = async (containerName: string) => {
    setRestartingId(containerName);
    setConfirmRestart(null);
    try {
      await restartMut.mutateAsync(containerName);
    } finally {
      setRestartingId(null);
    }
  };

  const handleOpenInstance = (inst: DeployInstallation) => {
    setPrefill(null);
    setShowForm(false);
    setEditingId(inst.id);
    setActiveTab("installations");
  };

  const handleRegisterFromLive = (c: DockerContainer) => {
    const portsList = c.ports
      ? c.ports.split(", ").filter(Boolean)
      : [];
    setPrefill({
      name: c.name,
      container_name: c.name,
      restart_command: `docker restart ${c.name}`,
      ports: portsList,
    });
    setEditingId(null);
    setShowForm(true);
    setActiveTab("installations");
  };

  const isSaving = createMut.isPending || updateMut.isPending;

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <Server className="h-5 w-5 text-blue-500" /> Deploy Control
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Monitoring and control of Docker installations
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Sync result toast */}
          {syncResult && (
            <div className={cn(
              "flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs font-medium",
              syncResult.created > 0 || syncResult.updated > 0
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
                : "border-border bg-muted text-muted-foreground"
            )}>
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              {syncResult.created > 0 && <span>{syncResult.created} criado(s)</span>}
              {syncResult.updated > 0 && <span>{syncResult.updated} atualizado(s)</span>}
              {syncResult.created === 0 && syncResult.updated === 0 && <span>Registry already up to date</span>}
              <button type="button" onClick={() => setSyncResult(null)} className="ml-1 opacity-60 hover:opacity-100">
                <X className="h-3 w-3" />
              </button>
            </div>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={syncMut.isPending}
            onClick={async () => {
              setSyncResult(null);
              try {
                const r = await syncMut.mutateAsync();
                setSyncResult(r);
                qc.invalidateQueries({ queryKey: ["deploy"] });
                // Auto-dismiss after 6 s
                setTimeout(() => setSyncResult(null), 6000);
              } catch {
                // host-bridge offline — still refresh cache
                qc.invalidateQueries({ queryKey: ["deploy"] });
              }
            }}
          >
            {syncMut.isPending
              ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
              : <RefreshCw className="h-3.5 w-3.5 mr-1" />}
            Sync Docker
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setEditingId(null);
              setPrefill(null);
              setShowForm(true);
            }}
          >
            <Plus className="h-3.5 w-3.5 mr-1" /> New Installation
          </Button>
        </div>
      </div>

      {/* Summary stats — clickable cards navigate to the corresponding tab */}
      <div className="grid grid-cols-8 gap-3">
        {[
          { label: "Installations", value: installations.length, icon: Zap, color: "text-sky-500", tab: "installations", offline: false },
          { label: "Containers", value: bridgeOffline ? null : containers.length, icon: Box, color: "text-blue-500", tab: "live", offline: bridgeOffline },
          { label: "Running", value: bridgeOffline ? null : containers.filter((c) => c.state === "running").length, icon: Activity, color: "text-emerald-500", tab: "live", offline: bridgeOffline },
          { label: "Healthy", value: bridgeOffline ? null : containers.filter((c) => c.health === "healthy").length, icon: CheckCircle2, color: "text-emerald-600", tab: "live", offline: bridgeOffline },
          { label: "Issues", value: bridgeOffline ? null : containers.filter((c) => c.state === "stopped" || c.health === "unhealthy").length, icon: AlertCircle, color: "text-red-500", tab: "live", offline: bridgeOffline },
          { label: "Volumes", value: volumesOffline ? null : volumes.length, icon: HardDrive, color: "text-violet-500", tab: "volumes", offline: volumesOffline },
          { label: "Networks", value: networksOffline ? null : networks.length, icon: Network, color: "text-amber-500", tab: "networks", offline: networksOffline },
          { label: "Images", value: imagesOffline ? null : images.length, icon: Layers, color: "text-cyan-500", tab: "images", offline: imagesOffline },
        ].map(({ label, value, icon: Icon, color, tab, offline }) => (
          <button
            key={label}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={cn("text-left w-full rounded-lg border bg-card shadow-none transition-colors hover:bg-accent/50", offline && "opacity-50", activeTab === tab && "ring-1 ring-ring")}
          >
            <div className="p-3 flex items-center gap-3">
              <Icon className={cn("h-5 w-5 shrink-0", color)} />
              <div>
                <div className={cn("text-lg font-bold leading-none", value === null && "text-muted-foreground")}>
                  {value === null ? "—" : value}
                </div>
                <div className="text-xs text-muted-foreground">{label}</div>
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* Bridge offline banner */}
      {bridgeOffline && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-2.5 flex items-center gap-3">
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
          <p className="text-sm text-muted-foreground flex-1">
            Host-bridge offline — Docker data unavailable. Restart with:
          </p>
          <code className="text-[10px] bg-muted rounded px-2 py-1 font-mono text-foreground select-all">
            kill $(pgrep -f host-bridge); cd /root/project/forgehub/host-bridge && source /root/project/forgehub/.env && nohup /usr/local/lib/hermes-agent/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8910 &gt; /tmp/host-bridge.log 2&gt;&1 &amp;
          </code>
        </div>
      )}

      {/* Main tabs — navigation via stat cards above */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 min-h-0 flex flex-col">
        {/* Installations tab */}
        <TabsContent value="installations" className="flex-1 min-h-0 mt-3">
          <div className={cn("flex gap-4 h-full", showForm || editingId ? "" : "")}>
            {/* List */}
            <div className="flex-1 min-w-0 overflow-y-auto space-y-4">
              {loadingInstall ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading...
                </div>
              ) : installations.length === 0 ? (
                <div className="flex flex-col items-center gap-3 py-16 text-center">
                  <Server className="h-10 w-10 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">No installations registered.</p>
                  <p className="text-xs text-muted-foreground">
                    Use "New Installation" or register directly from the Live Docker tab.
                  </p>
                </div>
              ) : (
                Object.entries(grouped).map(([group, items]) => (
                  <div key={group}>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                      {group}
                    </h3>
                    <div className="space-y-2">
                      {items.map((inst) => (
                        <InstallCard
                          key={inst.id}
                          inst={inst}
                          liveContainers={containers}
                          volumes={volumes}
                          networks={networks}
                          images={images}
                          onEdit={() => { setEditingId(inst.id); setShowForm(false); }}
                          onDelete={() => setDeletingId(inst.id)}
                          onRestart={() => setConfirmRestart(inst.container_name!)}
                          onLogs={() => setLogsContainer(inst.container_name)}
                          restarting={restartingId === inst.container_name}
                        />
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Side form */}
            {(showForm || editingId) && (
              <div className="w-96 shrink-0 rounded-xl border border-border bg-card p-5 overflow-y-auto">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold text-sm">
                    {editingId ? "Container" : "New Installation"}
                  </h2>
                  <button
                    type="button"
                    onClick={() => { setShowForm(false); setEditingId(null); setPrefill(null); }}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <InstallationForm
                  key={editingId ?? "new"}
                  initial={editingInst}
                  prefillData={prefill ?? undefined}
                  onSave={handleSave}
                  onCancel={() => { setShowForm(false); setEditingId(null); setPrefill(null); }}
                  isSaving={isSaving}
                  containers={containers}
                  volumes={volumes}
                  networks={networks}
                  groups={groups}
                  onManageGroups={() => setShowGroupsModal(true)}
                />
              </div>
            )}
          </div>
        </TabsContent>

        {/* Live Docker tab */}
        <TabsContent value="live" className="flex-1 min-h-0 mt-3 overflow-y-auto">
          <LiveContainersTab
            containers={containers}
            installations={installations}
            onRegister={handleRegisterFromLive}
            onOpenInstance={handleOpenInstance}
          />
        </TabsContent>

        {/* Volumes tab */}
        <TabsContent value="volumes" className="flex-1 min-h-0 mt-3 overflow-y-auto">
          <VolumesTab
            installations={installations}
            liveContainers={containers}
            onOpenInstance={handleOpenInstance}
            onRegister={handleRegisterFromLive}
          />
        </TabsContent>

        {/* Networks tab */}
        <TabsContent value="networks" className="flex-1 min-h-0 mt-3 overflow-y-auto">
          <NetworksTab
            installations={installations}
            liveContainers={containers}
            onOpenInstance={handleOpenInstance}
            onRegister={handleRegisterFromLive}
          />
        </TabsContent>

        {/* Images tab */}
        <TabsContent value="images" className="flex-1 min-h-0 mt-3 overflow-y-auto">
          <ImagesTab />
        </TabsContent>
      </Tabs>

      {/* Modals */}
      {logsContainer && (
        <LogsModal containerName={logsContainer} onClose={() => setLogsContainer(null)} />
      )}

      {showGroupsModal && (
        <GroupsModal groups={groups} onClose={() => setShowGroupsModal(false)} />
      )}

      <ConfirmDialog
        open={!!deletingId}
        title="Remove installation"
        description={`Remove "${deletingInst?.name}" from the registry? The Docker container will not be affected.`}
        confirmLabel="Remove"
        loading={deleteMut.isPending}
        onConfirm={handleDelete}
        onCancel={() => setDeletingId(null)}
      />

      <ConfirmDialog
        open={!!confirmRestart}
        title="Restart container"
        description={`Restart container "${confirmRestart}"? The service will be offline for a few seconds.`}
        confirmLabel="Restart"
        cancelLabel="Cancel"
        variant="default"
        onConfirm={() => confirmRestart && handleRestart(confirmRestart)}
        onCancel={() => setConfirmRestart(null)}
      />
    </div>
  );
}
