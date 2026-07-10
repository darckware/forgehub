import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Eye,
  Loader2,
  MessageSquare,
  Pencil,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  SKILL_ORIGINS,
  SKILL_RISK_LEVELS,
  useDeleteSkill,
  useSkills,
  useSyncHermesAgents,
  useUpdateSkill,
  type Skill,
} from "@/hooks/useAgent";
import { Textarea } from "@/components/ui/textarea";
import { useSkillFileContent, useUpdateSkillFileContent } from "@/hooks/useSkillFile";
import { apiClient } from "@/lib/api";
import { useChatHandoffStore } from "@/store/chatHandoff";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";

/** Draft seeded into the workspace chat composer, mirroring Agent Tools'
 * maintenance message: skill metadata first, then the SKILL.md source. */
function buildSkillChatMessage(skill: Skill, fileContent: string | null, filePath: string | null): string {
  const lines: string[] = [
    "I need help with this Hermes skill. Please review it and suggest improvements.",
    "",
    `Skill: ${skill.name}`,
    `Version: ${skill.version}`,
    `Risk level: ${skill.risk_level}`,
  ];
  if ((skill.agents ?? []).length > 0)
    lines.push(`Agents: ${(skill.agents ?? []).map((a) => a.agent_name).join(", ")}`);
  if (skill.description) lines.push(`Description: ${skill.description}`);
  if (filePath) lines.push(`Path: ${filePath}`);
  lines.push("");
  if (fileContent != null) {
    lines.push("```", fileContent, "```");
  } else {
    lines.push("(Could not read the SKILL.md content -- it may be missing.)");
  }
  return lines.join("\n");
}

/** Overlay showing a skill's description and its source SKILL.md file,
 * with in-place editing of the file. */
function SkillViewerOverlay({
  skill,
  startEditing,
  onClose,
}: {
  skill: Skill;
  startEditing: boolean;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error } = useSkillFileContent(skill.name);
  const updateContent = useUpdateSkillFileContent(skill.name);
  const [draft, setDraft] = useState<string | null>(null); // null = not editing
  const [pendingEdit, setPendingEdit] = useState(startEditing);

  // Opened via the Pencil action: enter edit mode as soon as the file loads.
  useEffect(() => {
    if (pendingEdit && data) {
      setDraft(data.content);
      setPendingEdit(false);
    }
  }, [pendingEdit, data]);

  function handleSave() {
    if (draft == null) return;
    updateContent.mutate(draft, { onSuccess: () => setDraft(null) });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="min-w-0">
            <h3 className="truncate font-semibold">{skill.name}</h3>
            <p className="truncate text-xs text-muted-foreground">
              {data?.path ?? `v${skill.version} · ${skill.origin} · risk ${skill.risk_level}`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {data && draft == null && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDraft(data.content)}
              >
                <Pencil className="mr-2 h-3.5 w-3.5" />
                Edit
              </Button>
            )}
            {draft != null && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={updateContent.isPending}
                  onClick={() => setDraft(null)}
                >
                  Cancel
                </Button>
                <Button size="sm" disabled={updateContent.isPending} onClick={handleSave}>
                  {updateContent.isPending && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
                  Save
                </Button>
              </>
            )}
            <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
          {skill.description && (
            <p className="shrink-0 text-sm text-muted-foreground">{skill.description}</p>
          )}
          {updateContent.isError && (
            <p className="shrink-0 text-sm text-destructive">
              Save failed: {(updateContent.error as Error)?.message}
            </p>
          )}
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-10 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading SKILL.md…
            </div>
          )}
          {isError && (
            <p className="text-sm text-destructive">
              {(error as Error)?.message ?? "Could not load the SKILL.md file."}
            </p>
          )}
          {data && draft == null && (
            <pre className="whitespace-pre-wrap break-all rounded-md bg-muted/40 p-3 text-xs">
              <code>{data.content}</code>
            </pre>
          )}
          {draft != null && (
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
              className="min-h-[45vh] flex-1 font-mono text-xs"
            />
          )}
        </div>
      </div>
    </div>
  );
}

/** Modal editing the skill's registry metadata (DB row, not the file).
 * The backend rejects edits on already-approved skills. */
function SkillFormModal({ skill, onClose }: { skill: Skill; onClose: () => void }) {
  const updateSkill = useUpdateSkill();
  const [form, setForm] = useState({
    name: skill.name,
    version: skill.version,
    description: skill.description ?? "",
    origin: skill.origin,
    risk_level: skill.risk_level,
  });

  function handleSave() {
    updateSkill.mutate(
      {
        skillId: skill.id,
        updates: {
          name: form.name,
          version: form.version,
          description: form.description || null,
          origin: form.origin,
          risk_level: form.risk_level,
        },
      },
      { onSuccess: onClose }
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-border bg-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="font-semibold">Edit skill: {skill.name}</h3>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="space-y-4 p-4">
          {updateSkill.isError && (
            <p className="text-sm text-destructive">{(updateSkill.error as Error)?.message}</p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Name</label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Version</label>
              <Input
                value={form.version}
                onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Origin</label>
              <Select
                value={form.origin}
                onChange={(e) => setForm((f) => ({ ...f, origin: e.target.value as Skill["origin"] }))}
              >
                {SKILL_ORIGINS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Risk level</label>
              <Select
                value={form.risk_level}
                onChange={(e) =>
                  setForm((f) => ({ ...f, risk_level: e.target.value as Skill["risk_level"] }))
                }
              >
                {SKILL_RISK_LEVELS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Description</label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              rows={3}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={updateSkill.isPending}>
              {updateSkill.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

const RISK_VARIANT: Record<
  Skill["risk_level"],
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  low: "outline",
  medium: "secondary",
  high: "warning",
  critical: "destructive",
};

/** How many holder badges to show inline before collapsing into "+N". */
const MAX_AGENT_BADGES = 5;

export default function SkillsPage() {
  const { data: skills, isLoading, isError, error } = useSkills();
  const syncHermes = useSyncHermesAgents();
  const deleteSkill = useDeleteSkill();
  const navigate = useNavigate();
  const setChatDraft = useChatHandoffStore((s) => s.setDraft);
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [viewing, setViewing] = useState<{ skill: Skill; editing: boolean } | null>(null);
  const [formSkill, setFormSkill] = useState<Skill | null>(null);
  const [deleting, setDeleting] = useState<Skill | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);

  async function handleSendToChat(skill: Skill) {
    setSendingId(skill.id);
    try {
      let content: string | null = null;
      let path: string | null = null;
      try {
        const file = await apiClient.get<{ content: string; path: string }>(
          `/api/v1/foundation/skills/${encodeURIComponent(skill.name)}/content`
        );
        content = file.content;
        path = file.path;
      } catch {
        // no SKILL.md found -- send the metadata anyway
      }
      setChatDraft(buildSkillChatMessage(skill, content, path));
      navigate("/workspace");
    } finally {
      setSendingId(null);
    }
  }

  const agentOptions = [
    ...new Set((skills ?? []).flatMap((s) => (s.agents ?? []).map((a) => a.agent_name))),
  ].sort((a, b) => a.localeCompare(b));

  const term = search.trim().toLowerCase();
  const filtered = (skills ?? []).filter(
    (s) =>
      (!term ||
        s.name.toLowerCase().includes(term) ||
        (s.description ?? "").toLowerCase().includes(term)) &&
      (!agentFilter || (s.agents ?? []).some((a) => a.agent_name === agentFilter))
  );

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col gap-4 p-6">
      {viewing && (
        <SkillViewerOverlay
          key={`${viewing.skill.id}-${viewing.editing}`}
          skill={viewing.skill}
          startEditing={viewing.editing}
          onClose={() => setViewing(null)}
        />
      )}
      {formSkill && <SkillFormModal skill={formSkill} onClose={() => setFormSkill(null)} />}
      <ConfirmDialog
        open={deleting !== null}
        title={`Delete "${deleting?.name ?? ""}"`}
        description="Removes the skill from the registry (agent grants included). The SKILL.md file in the profile is untouched, so a later Sync re-imports it."
        loading={deleteSkill.isPending}
        onConfirm={() => {
          if (deleting) deleteSkill.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
        onCancel={() => setDeleting(null)}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Sparkles className="h-5 w-5" /> Skills
          {skills && (
            <span className="text-sm font-normal text-muted-foreground">
              {skills.length} registered
            </span>
          )}
        </h1>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            title="Sync skills and grants from Hermes Foundation"
            disabled={syncHermes.isPending}
            onClick={() => syncHermes.mutate()}
          >
            {syncHermes.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Sync
          </Button>
          <AssistantToggleButton size="sm" />
        </div>
      </div>

      {syncHermes.isError && (
        <p className="text-sm text-destructive">
          Hermes sync failed: {(syncHermes.error as Error)?.message}
        </p>
      )}
      {syncHermes.isSuccess && syncHermes.data && (
        <p className="text-xs text-muted-foreground">
          Sync: {syncHermes.data.skills.created} skills created, {syncHermes.data.skills.updated}{" "}
          updated, {syncHermes.data.agent_skills.created} grants created.
          {syncHermes.data.warnings.length > 0 && (
            <span className="text-destructive"> {syncHermes.data.warnings.join("; ")}</span>
          )}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or description…"
            className="w-72 pl-8"
          />
        </div>
        <Select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="w-48"
          aria-label="Filter by agent"
        >
          <option value="">All agents</option>
          {agentOptions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </Select>
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load skills: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && (skills ?? []).length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
            No skills registered yet. Use “Sync from Hermes Foundation” to import the catalog.
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && (skills ?? []).length > 0 && filtered.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No skills match the selected filters.
          </CardContent>
        </Card>
      )}

      {filtered.length > 0 && (
        <Card className="min-h-0 flex-1 overflow-hidden">
          <CardContent className="h-full overflow-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Skill</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Risk</TableHead>
                  <TableHead>Agents</TableHead>
                  <TableHead className="w-16 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((skill) => {
                  const holders = skill.agents ?? [];
                  const shown = holders.slice(0, MAX_AGENT_BADGES);
                  const hidden = holders.slice(MAX_AGENT_BADGES);
                  return (
                    <TableRow key={skill.id}>
                      <TableCell>
                        <p className="font-medium">{skill.name}</p>
                        {skill.description ? (
                          <p
                            className="max-w-md truncate text-xs text-muted-foreground"
                            title={skill.description}
                          >
                            {skill.description}
                          </p>
                        ) : (
                          <p className="text-xs italic text-muted-foreground">No description.</p>
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {skill.version}
                      </TableCell>
                      <TableCell>
                        <Badge variant={RISK_VARIANT[skill.risk_level] ?? "outline"}>
                          {skill.risk_level}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {holders.length === 0 ? (
                          <span className="text-sm text-muted-foreground">—</span>
                        ) : (
                          <div className="flex max-w-md flex-wrap gap-1">
                            {shown.map((a) => (
                              <Badge key={a.agent_id} variant="outline" className="text-xs">
                                {a.agent_name}
                              </Badge>
                            ))}
                            {hidden.length > 0 && (
                              <Badge
                                variant="secondary"
                                className="text-xs"
                                title={hidden.map((a) => a.agent_name).join(", ")}
                              >
                                +{hidden.length}
                              </Badge>
                            )}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-0.5">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Send ${skill.name} to chat`}
                            title="Send data and SKILL.md to chat"
                            disabled={sendingId === skill.id}
                            onClick={() => handleSendToChat(skill)}
                          >
                            {sendingId === skill.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <MessageSquare className="h-4 w-4" />
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`View ${skill.name}`}
                            title="View description and SKILL.md"
                            onClick={() => setViewing({ skill, editing: false })}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Edit ${skill.name} file`}
                            title="Edit SKILL.md"
                            onClick={() => setViewing({ skill, editing: true })}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Edit ${skill.name} registry entry`}
                            title="Edit registry entry"
                            onClick={() => setFormSkill(skill)}
                          >
                            <Settings2 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Delete ${skill.name}`}
                            title="Delete registry entry"
                            className="text-destructive"
                            onClick={() => setDeleting(skill)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
