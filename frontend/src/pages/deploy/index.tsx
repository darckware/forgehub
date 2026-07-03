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
  ExternalLink,
  HardDrive,
  Loader2,
  Network,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  ScrollText,
  Server,
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
  useCreateInstallation,
  useUpdateInstallation,
  useDeleteInstallation,
  useRestartContainer,
  useContainerLogs,
  useSyncFromDocker,
  type DeployInstallation,
  type DockerContainer,
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
// Installation form (create / edit)
// ---------------------------------------------------------------------------

interface Link { label: string; url: string }

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
}: {
  initial?: DeployInstallation;
  prefillData?: Partial<DeployInstallationCreate>;
  onSave: (data: DeployInstallationCreate) => void;
  onCancel: () => void;
  isSaving: boolean;
  containers: DockerContainer[];
}) {
  const { data: products = [] } = useProducts();
  const [form, setForm] = useState<DeployInstallationCreate>(() => {
    if (initial) {
      return {
        name: initial.name,
        description: initial.description ?? "",
        group_name: initial.group_name ?? "",
        order_index: initial.order_index,
        container_name: initial.container_name ?? "",
        compose_file: initial.compose_file ?? "",
        restart_command: initial.restart_command ?? "",
        ports: initial.ports ?? [],
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
          <Label className="text-xs">Group</Label>
          <Input
            value={form.group_name ?? ""}
            onChange={(e) => f("group_name", e.target.value)}
            placeholder="ForgeHub, Infrastructure..."
            list="groups-list"
            className="h-8 text-sm"
          />
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
  onEdit,
  onDelete,
  onRestart,
  onLogs,
  restarting,
}: {
  inst: DeployInstallation;
  liveContainers: DockerContainer[];
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
          <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={onEdit} title="Edit">
            <Pencil className="h-3.5 w-3.5" />
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
              <span className="text-xs font-medium text-foreground">Produto:</span>
              <span className="inline-flex items-center gap-1 rounded bg-blue-500/10 px-2 py-0.5 text-xs text-blue-600 font-medium">
                <Box className="h-2.5 w-2.5" /> {inst.product_name}
              </span>
            </div>
          )}
          {live && (
            <div className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Status:</span> {live.status}
              {live.image && <> &nbsp;·&nbsp; <span className="font-mono">{live.image}</span></>}
            </div>
          )}

          {ports.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-foreground">Portas:</span>
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
              <span className="text-xs font-medium text-foreground">Portas (live):</span>
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
                title="Copiar comando"
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

function LiveContainersTab({ containers, onRegister }: { containers: DockerContainer[]; onRegister: (c: DockerContainer) => void }) {
  const { isLoading, isError, refetch, isFetching } = useDockerContainers();

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
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading containers...
        </div>
      ) : (
        <div className="space-y-1">
          {containers.map((c) => (
            <div key={c.name} className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2.5">
              <span className={cn("h-2 w-2 rounded-full shrink-0", statusDot(c.state, c.health))} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium">{c.name}</span>
                  <ContainerStatusBadge state={c.state} health={c.health} />
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-xs text-muted-foreground font-mono truncate">{c.image}</span>
                  {c.ports && <span className="text-xs text-muted-foreground font-mono truncate">{c.ports}</span>}
                </div>
              </div>
              <Button size="sm" variant="outline" className="h-7 text-xs shrink-0" onClick={() => onRegister(c)}>
                <Plus className="h-3 w-3 mr-1" /> Registrar
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Volumes tab
// ---------------------------------------------------------------------------

function VolumesTab() {
  const { data: volumes = [], isLoading, isError, refetch, isFetching } = useDockerVolumes();

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
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Nome</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Driver</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Scope</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Mountpoint</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Containers</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {volumes.map((v) => (
                <tr key={v.name} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <HardDrive className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                      <span className="font-mono text-xs font-medium">{v.name}</span>
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
                        {v.containers.map((c) => (
                          <span key={c} className="inline-block rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono">{c}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground/50 italic">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Networks tab
// ---------------------------------------------------------------------------

function NetworksTab() {
  const { data: networks = [], isLoading, isError, refetch, isFetching } = useDockerNetworks();
  const [expanded, setExpanded] = useState<string | null>(null);

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
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading networks...
        </div>
      ) : (
        <div className="space-y-1.5">
          {networks.map((n) => {
            const isOpen = expanded === n.id;
            return (
              <div key={n.id} className="rounded-lg border border-border bg-card overflow-hidden">
                <button
                  type="button"
                  onClick={() => setExpanded(isOpen ? null : n.id)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30 transition-colors text-left"
                >
                  {isOpen
                    ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
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
                              {n.containers.map((c, i) => (
                                <tr key={i} className="hover:bg-muted/20">
                                  <td className="px-3 py-1.5 font-mono">{c.name}</td>
                                  <td className="px-3 py-1.5 font-mono text-muted-foreground">{c.ipv4 || "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                    {n.containers.length === 0 && n.subnets.length === 0 && (
                      <p className="text-xs text-muted-foreground italic">Sem containers ou subnets configuradas.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DeployPage() {
  const qc = useQueryClient();
  const { data: installations = [], isLoading: loadingInstall } = useInstallations();
  const { data: containers = [], isError: containersOffline } = useDockerContainers();
  const { data: volumes = [], isError: volumesOffline } = useDockerVolumes();
  const { data: networks = [], isError: networksOffline } = useDockerNetworks();
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
      <div className="grid grid-cols-7 gap-3">
        {[
          { label: "Installations", value: installations.length, icon: Zap, color: "text-sky-500", tab: "installations", offline: false },
          { label: "Containers", value: bridgeOffline ? null : containers.length, icon: Box, color: "text-blue-500", tab: "live", offline: bridgeOffline },
          { label: "Rodando", value: bridgeOffline ? null : containers.filter((c) => c.state === "running").length, icon: Activity, color: "text-emerald-500", tab: "live", offline: bridgeOffline },
          { label: "Healthy", value: bridgeOffline ? null : containers.filter((c) => c.health === "healthy").length, icon: CheckCircle2, color: "text-emerald-600", tab: "live", offline: bridgeOffline },
          { label: "Problema", value: bridgeOffline ? null : containers.filter((c) => c.state === "stopped" || c.health === "unhealthy").length, icon: AlertCircle, color: "text-red-500", tab: "live", offline: bridgeOffline },
          { label: "Volumes", value: volumesOffline ? null : volumes.length, icon: HardDrive, color: "text-violet-500", tab: "volumes", offline: volumesOffline },
          { label: "Networks", value: networksOffline ? null : networks.length, icon: Network, color: "text-amber-500", tab: "networks", offline: networksOffline },
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
                    {editingId ? "Edit Installation" : "New Installation"}
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
                />
              </div>
            )}
          </div>
        </TabsContent>

        {/* Live Docker tab */}
        <TabsContent value="live" className="flex-1 min-h-0 mt-3 overflow-y-auto">
          <LiveContainersTab containers={containers} onRegister={handleRegisterFromLive} />
        </TabsContent>

        {/* Volumes tab */}
        <TabsContent value="volumes" className="flex-1 min-h-0 mt-3 overflow-y-auto">
          <VolumesTab />
        </TabsContent>

        {/* Networks tab */}
        <TabsContent value="networks" className="flex-1 min-h-0 mt-3 overflow-y-auto">
          <NetworksTab />
        </TabsContent>
      </Tabs>

      {/* Modals */}
      {logsContainer && (
        <LogsModal containerName={logsContainer} onClose={() => setLogsContainer(null)} />
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
