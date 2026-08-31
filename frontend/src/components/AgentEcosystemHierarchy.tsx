import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, ChevronDown, ChevronRight, FolderTree, Network, Pencil, Trash2, Upload, Wrench } from "lucide-react";
import { AgentAvatar, validateAgentAvatar } from "@/components/AgentAvatar";
import { AgentProfileFileChips } from "@/components/AgentProfileFileChips";
import { AgentRosterTable, type AgentSortKey, type SortDirection } from "@/components/AgentRosterTable";
import { TelegramStatusBadge } from "@/components/TelegramStatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  useAgentsTelegramStatus, useDeleteAgent, useDeleteSubAgent, useUpdateAgent,
  type Agent, type AgentTelegramStatus, type Skill, type SubAgent,
} from "@/hooks/useAgent";
import { useFoundationCrons, type CronJob } from "@/hooks/useFoundationCrons";
import { useFoundationAllScripts, type FoundationScript } from "@/hooks/useFoundationScripts";
import { useTools, type AgentTool } from "@/hooks/useTools";
import { ApiError } from "@/lib/api";

const VALID_SORT_KEYS = new Set<AgentSortKey>([
  "name", "function", "organization", "runtime", "status", "inventory",
]);
const CRON_HEALTH_VARIANT: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  ok: "success", error: "destructive", overdue: "destructive", never_ran: "warning", off: "outline",
};
const SCRIPT_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive"> = {
  ok: "success", broken: "destructive", unused: "warning",
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.body && typeof error.body === "object" && "detail" in error.body) {
    return String(error.body.detail);
  }
  return error instanceof Error ? error.message : String(error);
}

function CollapsibleSection({ label, count, children, emptyLabel }: {
  label: string; count: number; children: React.ReactNode; emptyLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  if (count === 0) {
    return emptyLabel ? <p className="mt-3 text-xs italic text-muted-foreground">{emptyLabel}</p> : null;
  }
  return (
    <div className="mt-3">
      <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}
        className="flex w-full items-center gap-1.5 rounded-sm py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        {label}<Badge variant="outline" className="ml-1 text-[10px]">{count}</Badge>
      </button>
      {open && <div className="mt-1 max-h-48 overflow-y-auto rounded-md border bg-background/70 p-2">{children}</div>}
    </div>
  );
}

function AgentPhotoEditor({ agent }: { agent: Agent }) {
  const { t } = useTranslation("agent");
  const inputRef = useRef<HTMLInputElement>(null);
  const updateAgent = useUpdateAgent(agent.id);
  const [localError, setLocalError] = useState<string | null>(null);

  const saveFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const validationError = validateAgentAvatar(file);
    if (validationError) {
      const suffix = `${validationError[0].toUpperCase()}${validationError.slice(1)}`;
      setLocalError(t(`roster.photo.error${suffix}`));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => setLocalError(t("roster.photo.errorRead"));
    reader.onload = () => {
      setLocalError(null);
      updateAgent.mutate({ avatar_data_url: String(reader.result) });
    };
    reader.readAsDataURL(file);
  };
  const mutationError = updateAgent.error
    ? t("roster.photo.errorSave", { message: errorMessage(updateAgent.error) })
    : null;

  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border bg-card p-4 text-center">
      <AgentAvatar name={agent.name} avatarDataUrl={agent.avatar_data_url}
        imageAlt={t("roster.photo.imageAlt", { name: agent.name })} size="lg" />
      <div><p className="text-sm font-semibold">{t("roster.photo.title")}</p>
        <p className="mt-1 text-xs text-muted-foreground">{t("roster.photo.hint")}</p></div>
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={saveFile} />
      <div className="flex flex-wrap justify-center gap-2">
        <Button size="sm" variant="outline" disabled={updateAgent.isPending} onClick={() => inputRef.current?.click()}>
          <Upload className="mr-1.5 h-3.5 w-3.5" />
          {agent.avatar_data_url ? t("roster.photo.replace") : t("roster.photo.choose")}
        </Button>
        {agent.avatar_data_url && <Button size="sm" variant="ghost" disabled={updateAgent.isPending}
          onClick={() => updateAgent.mutate({ avatar_data_url: null })}>{t("roster.photo.remove")}</Button>}
      </div>
      {updateAgent.isPending && <p className="text-xs text-muted-foreground">{t("roster.photo.saving")}</p>}
      {(localError || mutationError) && <p role="alert" className="text-xs text-destructive">{localError || mutationError}</p>}
    </div>
  );
}

function AgentDetails({ agent, skills, telegram, crons, scripts, tools, onDelete, onDeleteSubAgent }: {
  agent: Agent; skills: Skill[]; telegram?: AgentTelegramStatus; crons: CronJob[];
  scripts: FoundationScript[]; tools: AgentTool[]; onDelete: (agent: Agent) => void;
  onDeleteSubAgent: (agent: Agent, subAgent: SubAgent) => void;
}) {
  const { t } = useTranslation("agent");
  const approvedSkills = skills.filter((skill) => skill.is_approved);
  const description = agent.mission || agent.description || `${agent.agent_type} agent`;
  return (
    <div className="grid gap-5 lg:grid-cols-[13rem_minmax(0,1fr)]">
      <AgentPhotoEditor agent={agent} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Bot className="h-4 w-4" />
          <Link to={`/agents/${agent.id}`} className="font-semibold hover:underline">{agent.name}</Link>
          {agent.profile_slug && <code className="text-xs text-muted-foreground">{agent.profile_slug}</code>}
          <Badge variant="outline">{agent.agent_type}</Badge>
          <Badge variant={agent.forgerouter_api_key_configured ? "success" : "destructive"}>
            {agent.forgerouter_api_key_configured ? t("hierarchy.forgeRouterConfigured") : t("hierarchy.forgeRouterMissing")}
          </Badge>
          <TelegramStatusBadge status={telegram} />
        </div>
        <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        {(agent.department || agent.sector) && <p className="mt-1 text-xs text-muted-foreground">{[agent.department, agent.sector].filter(Boolean).join(" · ")}</p>}
        {agent.effective_home_path && <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="flex min-w-0 items-center gap-1"><FolderTree className="h-3 w-3 shrink-0" /><code className="truncate">{agent.effective_home_path}</code></span>
          <AgentProfileFileChips agent={agent} />
        </div>}
        <CollapsibleSection label={t("hierarchy.approvedSkills")} count={approvedSkills.length} emptyLabel={t("hierarchy.noApprovedSkills")}>
          <div className="flex flex-wrap gap-1">{approvedSkills.map((skill) => <Badge key={skill.id} variant="secondary" className="text-[11px]">{skill.name} · v{skill.version}</Badge>)}</div>
        </CollapsibleSection>
        <CollapsibleSection label={t("hierarchy.subAgents")} count={agent.sub_agents.length}>
          <div className="space-y-1">{agent.sub_agents.map((subAgent) => <div key={subAgent.id} className="flex items-start justify-between gap-2 rounded-md bg-background/60 p-2 text-xs">
            <p className="min-w-0"><span className="font-medium">{subAgent.name}</span><span className="text-muted-foreground"> — {subAgent.description || subAgent.permission_scope || t("hierarchy.scopedWorker")}</span></p>
            <Button size="icon" variant="ghost" className="h-6 w-6 shrink-0 text-destructive" aria-label={t("list.deleteSubAgentTooltip")} onClick={() => onDeleteSubAgent(agent, subAgent)}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>)}</div>
        </CollapsibleSection>
        <CollapsibleSection label={t("hierarchy.tools")} count={tools.length} emptyLabel={t("hierarchy.noTools")}>
          <div className="space-y-1.5">{tools.map((tool) => (
            <div key={tool.id} className="flex items-start justify-between gap-2 rounded-md bg-background/60 p-2 text-xs">
              <div className="min-w-0 flex-1 space-y-0.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <code className="font-semibold text-foreground">{tool.name}</code>
                  <Badge variant="outline" className="text-[10px] uppercase">{tool.category}</Badge>
                  <Badge variant={tool.status === "active" ? "success" : tool.status === "deprecated" ? "warning" : "outline"} className="text-[10px]">{tool.status}</Badge>
                </div>
                {tool.description && <p className="line-clamp-2 text-[11px] text-muted-foreground">{tool.description}</p>}
                {tool.file_path && <code className="block truncate text-[10px] text-muted-foreground/80">{tool.file_path}</code>}
              </div>
              <Link to={`/tools?agent=${agent.id}`} className={buttonVariants({ variant: "ghost", size: "icon" })} title={t("hierarchy.viewInToolsPanel")}><Wrench className="h-3.5 w-3.5" /></Link>
            </div>
          ))}</div>
        </CollapsibleSection>
        <CollapsibleSection label={t("hierarchy.crons")} count={crons.length}>
          <div className="space-y-1">{crons.map((job) => <div key={job.id} className="rounded-md bg-background/60 p-2 text-xs">
            <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{job.name}</span><Badge variant={CRON_HEALTH_VARIANT[job.health] ?? "outline"} className="text-[10px]">{t(`hierarchy.cronHealth.${job.health}`)}</Badge>{job.schedule_display && <code className="text-[10px] text-muted-foreground">{job.schedule_display}</code>}</div>
            {job.script && <code className="mt-0.5 block truncate text-[10px] text-muted-foreground">{job.script}</code>}
          </div>)}</div>
        </CollapsibleSection>
        <CollapsibleSection label={t("hierarchy.scripts")} count={scripts.length}>
          <div className="space-y-1">{scripts.map((script) => <div key={`${script.location}/${script.name}`} className="rounded-md bg-background/60 p-2 text-xs">
            <div className="flex flex-wrap items-center gap-2"><code className="font-medium">{script.name}</code><Badge variant={SCRIPT_STATUS_VARIANT[script.status] ?? "outline"} className="text-[10px]">{t(`hierarchy.scriptStatus.${script.status}`)}</Badge></div>
            {script.description && <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">{script.description}</p>}
          </div>)}</div>
        </CollapsibleSection>
        <div className="mt-4 flex justify-end gap-1 border-t pt-3">
          <Link to={`/agents/${agent.id}`} className={buttonVariants({ variant: "ghost", size: "icon" })} title={t("list.editAgentTooltip")} aria-label={t("list.editAgentTooltip")}><Pencil className="h-4 w-4" /></Link>
          <Button size="icon" variant="ghost" className="text-destructive" title={t("list.deleteAgentTooltip")} aria-label={t("list.deleteAgentTooltip")} onClick={() => onDelete(agent)}><Trash2 className="h-4 w-4" /></Button>
        </div>
      </div>
    </div>
  );
}

type DeleteTarget = { kind: "agent"; agent: Agent } | { kind: "sub-agent"; agent: Agent; subAgent: SubAgent };

export function AgentEcosystemHierarchy({ agents: allAgents, skills, focusedAgentId }: {
  agents: Agent[]; skills: Skill[]; focusedAgentId?: string | null;
}) {
  const { t } = useTranslation("agent");
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSort = searchParams.get("sort") as AgentSortKey | null;
  const sortKey = requestedSort && VALID_SORT_KEYS.has(requestedSort) ? requestedSort : "name";
  const sortDirection: SortDirection = searchParams.get("direction") === "desc" ? "desc" : "asc";
  const [expandedAgentId, setExpandedAgentId] = useState<string | null>(focusedAgentId ?? null);
  const [deleting, setDeleting] = useState<DeleteTarget | null>(null);
  const deleteAgent = useDeleteAgent();
  const deleteSubAgent = useDeleteSubAgent();
  useEffect(() => setExpandedAgentId(focusedAgentId ?? null), [focusedAgentId]);

  const activeAgents = allAgents.filter((agent) => agent.is_active);
  const agents = activeAgents.filter((agent) => !focusedAgentId || agent.id === focusedAgentId);
  const skillsFor = (agentId: string) => skills.filter((skill) => skill.agents.some((holder) => holder.agent_id === agentId));
  const approvedSkillCount = (agentId: string) => skillsFor(agentId).filter((skill) => skill.is_approved).length;
  const { data: telegramStatus } = useAgentsTelegramStatus();
  const telegramByAgent = new Map((telegramStatus?.agents ?? []).map((entry) => [entry.agent_id, entry]));
  const { data: cronData } = useFoundationCrons();
  const { data: scriptData } = useFoundationAllScripts();
  const { data: allTools = [] } = useTools();
  const cronsFor = (slug: string | null | undefined) => slug ? (cronData?.jobs ?? []).filter((job) => job.profile === slug) : [];
  const scriptsFor = (slug: string | null | undefined) => slug ? (scriptData ?? []).filter((script) => script.location === slug) : [];
  const toolsFor = (agentId: string) => allTools.filter((tool) => tool.agent_id === agentId);
  const handleSort = (key: AgentSortKey) => {
    const next = new URLSearchParams(searchParams);
    next.set("sort", key);
    next.set("direction", key === sortKey && sortDirection === "asc" ? "desc" : "asc");
    setSearchParams(next, { replace: true });
  };
  const deleteError = deleteAgent.error || deleteSubAgent.error;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl"><Network className="h-5 w-5" />{t("roster.title")}</CardTitle>
        <CardDescription>{t("roster.description")}</CardDescription>
        <div className="flex flex-wrap gap-2 pt-2 text-sm">
          <Badge variant="success">{t("roster.stats.active", { count: activeAgents.length })}</Badge>
          <Badge variant="outline">{t("hierarchy.stats.workers", { count: activeAgents.reduce((total, agent) => total + agent.sub_agents.length, 0) })}</Badge>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <AgentRosterTable agents={agents} sortKey={sortKey} sortDirection={sortDirection}
          expandedAgentId={expandedAgentId} onSort={handleSort}
          onToggle={(agentId) => setExpandedAgentId((current) => current === agentId ? null : agentId)}
          approvedSkillCount={approvedSkillCount}
          renderDetails={(agent) => <AgentDetails agent={agent} skills={skillsFor(agent.id)}
            telegram={telegramByAgent.get(agent.id)} crons={cronsFor(agent.profile_slug)} scripts={scriptsFor(agent.profile_slug)}
            tools={toolsFor(agent.id)}
            onDelete={(target) => { deleteAgent.reset(); setDeleting({ kind: "agent", agent: target }); }}
            onDeleteSubAgent={(target, subAgent) => { deleteSubAgent.reset(); setDeleting({ kind: "sub-agent", agent: target, subAgent }); }} />}
        />
      </CardContent>
      <ConfirmDialog open={deleting !== null}
        title={deleting?.kind === "sub-agent" ? t("list.confirmDeleteSubAgentTitle", { name: deleting.subAgent.name }) : t("list.confirmDeleteAgentTitle", { name: deleting?.agent.name ?? "" })}
        description={deleting?.kind === "sub-agent" ? t("list.confirmDeleteSubAgentDescription") : t("list.confirmDeleteAgentDescription")}
        confirmLabel={t("list.deleteConfirmLabel")} loading={deleteAgent.isPending || deleteSubAgent.isPending}
        error={deleteError ? t("roster.deleteError", { message: errorMessage(deleteError) }) : null}
        onConfirm={() => {
          if (!deleting) return;
          if (deleting.kind === "sub-agent") deleteSubAgent.mutate({ agentId: deleting.agent.id, subAgentId: deleting.subAgent.id }, { onSuccess: () => setDeleting(null) });
          else deleteAgent.mutate(deleting.agent.id, { onSuccess: () => setDeleting(null) });
        }}
        onCancel={() => { deleteAgent.reset(); deleteSubAgent.reset(); setDeleting(null); }} />
    </Card>
  );
}
