import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Archive,
  Bot,
  ChevronDown,
  ChevronRight,
  FolderTree,
  Network,
  Pencil,
  Plug,
  Trash2,
  Workflow,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { AgentProfileFileChips } from "@/components/AgentProfileFileChips";
import { TelegramStatusBadge } from "@/components/TelegramStatusBadge";
import {
  isExternalRuntime,
  useAgentsTelegramStatus,
  useDeleteAgent,
  useDeleteSubAgent,
  type Agent,
  type AgentTelegramStatus,
  type Skill,
  type SubAgent,
} from "@/hooks/useAgent";
import { useFoundationCrons, type CronJob } from "@/hooks/useFoundationCrons";
import { useFoundationAllScripts, type FoundationScript } from "@/hooks/useFoundationScripts";

/**
 * The org chart of the agent ecosystem.
 *
 * Two things drove the 2026-07-26 rework. First, every skill grant was
 * rendered as an always-visible chip: Athos alone holds 200+ skills, so the
 * orchestrator card buried the entire rest of the chart under a wall of
 * badges. Skills now live behind a per-agent collapse with its own vertical
 * scrollbar, so the chart stays readable at any grant count.
 *
 * Second, the chart only understood the Hermes layer/tier hierarchy, which
 * left the four external CLI runtimes (Porthus/claude, Aramis/codex,
 * Dartan/agy, Vector/openclaw) either invisible or dumped into "specialists
 * without department" — they have no Hermes layer because they are not Hermes
 * profiles. The top-level split is now by runtime family, and each card shows
 * the runtime and the home directory its profile files come from.
 */

const RUNTIME_LABELS: Record<string, string> = {
  hermes: "Hermes",
  claude: "Claude Code",
  codex: "Codex CLI",
  agy: "Gemini CLI (Agy)",
  openclaw: "OpenClaw",
};

function isAthos(agent: Agent) {
  return agent.profile_slug?.toLowerCase() === "athos" || agent.name.toLowerCase() === "athos";
}

function functionText(agent: Agent) {
  return agent.mission || agent.description || `${agent.agent_type} agent`;
}

/** A collapsed section inside an agent card. Kept closed by default: the
 *  point of the card is the agent's identity and function, not its inventory. */
function CollapsibleSection({
  label,
  count,
  children,
  emptyLabel,
}: {
  label: string;
  count: number;
  children: React.ReactNode;
  emptyLabel?: string;
}) {
  const [open, setOpen] = useState(false);

  if (count === 0) {
    return emptyLabel ? (
      <p className="mt-2 text-xs italic text-muted-foreground">{emptyLabel}</p>
    ) : null;
  }

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 rounded-sm py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        {label}
        <Badge variant="outline" className="ml-1 text-[10px]">
          {count}
        </Badge>
      </button>
      {open && (
        // Own vertical scrollbar: 200+ skill chips must scroll here, never
        // stretch the card.
        <div className="mt-1 max-h-48 overflow-y-auto rounded-md border bg-muted/20 p-2">
          {children}
        </div>
      )}
    </div>
  );
}

/** Colour for a cron job's real execution health -- `status` only mirrors the
 *  enabled flag, `health` says whether it is actually running (foundation.py's
 *  _job_health). "overdue" means the scheduler is not ticking it at all. */
const CRON_HEALTH_VARIANT: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  ok: "success",
  error: "destructive",
  overdue: "destructive",
  never_ran: "warning",
  off: "outline",
};

const SCRIPT_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive"> = {
  ok: "success",
  broken: "destructive",
  unused: "warning",
};

function AgentNode({
  agent,
  skills,
  telegram,
  crons,
  scripts,
  onDelete,
  onDeleteSubAgent,
  orchestrator = false,
}: {
  agent: Agent;
  skills: Skill[];
  telegram?: AgentTelegramStatus;
  crons: CronJob[];
  scripts: FoundationScript[];
  onDelete: (agent: Agent) => void;
  onDeleteSubAgent: (agent: Agent, subAgent: SubAgent) => void;
  orchestrator?: boolean;
}) {
  const { t } = useTranslation("agent");
  const approvedSkills = skills.filter((skill) => skill.is_approved);
  const runtimeLabel = agent.runtime_type ? RUNTIME_LABELS[agent.runtime_type] : null;

  return (
    <div
      className={
        orchestrator
          ? "rounded-lg border-2 border-primary/40 bg-primary/5 p-4"
          : "rounded-lg border p-4"
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        {orchestrator ? (
          <Workflow className="h-5 w-5 shrink-0 text-primary" />
        ) : (
          <Bot className="h-4 w-4 shrink-0" />
        )}
        <Link to={`/agents/${agent.id}`} className="font-semibold hover:underline">
          {agent.name}
        </Link>
        {agent.profile_slug && (
          <code className="text-xs text-muted-foreground">{agent.profile_slug}</code>
        )}
        {orchestrator && <Badge>{t("hierarchy.orchestratorBadge")}</Badge>}
        {runtimeLabel && (
          <Badge variant={isExternalRuntime(agent.runtime_type) ? "warning" : "secondary"}>
            {runtimeLabel}
          </Badge>
        )}
        <Badge variant="outline">{agent.agent_type}</Badge>
        {agent.runtime_tier && (
          <Badge variant="outline">{t("detail.tierBadge", { tier: agent.runtime_tier })}</Badge>
        )}
        <Badge variant={agent.forgerouter_api_key_configured ? "success" : "destructive"}>
          {agent.forgerouter_api_key_configured
            ? t("hierarchy.forgeRouterConfigured")
            : t("hierarchy.forgeRouterMissing")}
        </Badge>
        <TelegramStatusBadge status={telegram} />
      </div>

      {/* The agent's function — the thing this chart exists to communicate. */}
      <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{functionText(agent)}</p>

      {(agent.sector || agent.department) && (
        <p className="mt-1 text-xs text-muted-foreground">
          {[agent.department, agent.sector].filter(Boolean).join(" · ")}
        </p>
      )}

      {/* Profile directory and the files inside it, on one line: the path
          alone told an operator where to look but nothing about what is
          there. Chips are lazy -- opening one fetches that file. */}
      {agent.effective_home_path && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="flex min-w-0 items-center gap-1">
            <FolderTree className="h-3 w-3 shrink-0" />
            <code className="truncate">{agent.effective_home_path}</code>
          </span>
          <AgentProfileFileChips agent={agent} />
        </div>
      )}

      <CollapsibleSection
        label={t("hierarchy.approvedSkills")}
        count={approvedSkills.length}
        emptyLabel={t("hierarchy.noApprovedSkills")}
      >
        <div className="flex flex-wrap gap-1">
          {approvedSkills.map((skill) => (
            <Badge key={skill.id} variant="secondary" className="text-[11px]">
              {skill.name} · v{skill.version}
            </Badge>
          ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection label={t("hierarchy.subAgents")} count={agent.sub_agents.length}>
        <div className="space-y-1">
          {agent.sub_agents.map((subAgent) => (
            <div
              key={subAgent.id}
              className="flex items-start justify-between gap-2 rounded-md bg-background/60 p-2 text-xs"
            >
              <p className="min-w-0">
                <span className="font-medium">{subAgent.name}</span>
                <span className="text-muted-foreground">
                  {" — "}
                  {subAgent.description || subAgent.permission_scope || t("hierarchy.scopedWorker")}
                </span>
              </p>
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6 shrink-0 text-destructive"
                title={t("list.deleteSubAgentTooltip")}
                onClick={() => onDeleteSubAgent(agent, subAgent)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </CollapsibleSection>

      {/* Crons and scripts are per-profile on disk (<profile>/cron/jobs.json
          and <profile>/scripts/), so they belong to the agent that owns the
          profile — this is the scheduled work that agent actually performs. */}
      <CollapsibleSection label={t("hierarchy.crons")} count={crons.length}>
        <div className="space-y-1">
          {crons.map((job) => (
            <div key={job.id} className="rounded-md bg-background/60 p-2 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{job.name}</span>
                <Badge variant={CRON_HEALTH_VARIANT[job.health] ?? "outline"} className="text-[10px]">
                  {t(`hierarchy.cronHealth.${job.health}`)}
                </Badge>
                {job.schedule_display && (
                  <code className="text-[10px] text-muted-foreground">{job.schedule_display}</code>
                )}
              </div>
              {job.script && (
                <code className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                  {job.script}
                </code>
              )}
            </div>
          ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection label={t("hierarchy.scripts")} count={scripts.length}>
        <div className="space-y-1">
          {scripts.map((script) => (
            <div
              key={`${script.location}/${script.name}`}
              className="rounded-md bg-background/60 p-2 text-xs"
            >
              <div className="flex flex-wrap items-center gap-2">
                <code className="font-medium">{script.name}</code>
                <Badge
                  variant={SCRIPT_STATUS_VARIANT[script.status] ?? "outline"}
                  className="text-[10px]"
                >
                  {t(`hierarchy.scriptStatus.${script.status}`)}
                </Badge>
              </div>
              {script.description && (
                <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
                  {script.description}
                </p>
              )}
            </div>
          ))}
        </div>
      </CollapsibleSection>

      {/* Card-level actions. They used to live in a separate roster table
          below the chart; with everything about an agent now on its card,
          that table was pure duplication and was removed — so View and
          Delete had to come here or be lost. */}
      <div className="mt-3 flex justify-end gap-1 border-t pt-3">
        <Link
          to={`/agents/${agent.id}`}
          className={buttonVariants({ variant: "ghost", size: "icon" })}
          title={t("list.editAgentTooltip")}
          aria-label={t("list.editAgentTooltip")}
        >
          <Pencil className="h-4 w-4" />
        </Link>
        <Button
          size="icon"
          variant="ghost"
          className="text-destructive"
          title={t("list.deleteAgentTooltip")}
          onClick={() => onDelete(agent)}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

/** What the confirm dialog is currently pointed at. */
type DeleteTarget =
  | { kind: "agent"; agent: Agent }
  | { kind: "sub-agent"; agent: Agent; subAgent: SubAgent };

export function AgentEcosystemHierarchy({
  agents: allAgents,
  skills,
  focusedAgentId,
}: {
  /** The full roster, retired rows included — this component owns the
   *  active/inactive split now that the roster table is gone. */
  agents: Agent[];
  skills: Skill[];
  /** When set, render only that agent's card instead of the whole chart.
   *  Driven by the page's agent filter. */
  focusedAgentId?: string | null;
}) {
  const { t } = useTranslation("agent");
  const deleteAgent = useDeleteAgent();
  const deleteSubAgent = useDeleteSubAgent();
  const [deleting, setDeleting] = useState<DeleteTarget | null>(null);

  // Retired agents (e.g. the 2026-07-18 Tier B archival) are kept for audit
  // but never shown in the live org chart. They used to survive in the roster
  // table below the chart; with that table gone they get their own collapsed
  // section here rather than disappearing from the UI entirely.
  const agents = allAgents.filter((agent) => agent.is_active);
  const retiredAgents = allAgents.filter((agent) => !agent.is_active);

  // Looked up against the *full* roster: filtering to a retired agent has to
  // work, otherwise the filter silently shows nothing for those.
  const focusedAgent = focusedAgentId
    ? allAgents.find((agent) => agent.id === focusedAgentId)
    : undefined;

  const handleDeleteAgent = (agent: Agent) => setDeleting({ kind: "agent", agent });
  const handleDeleteSubAgent = (agent: Agent, subAgent: SubAgent) =>
    setDeleting({ kind: "sub-agent", agent, subAgent });

  const skillsFor = (agentId: string) =>
    skills.filter((skill) => skill.agents.some((holder) => holder.agent_id === agentId));

  // One roster-wide request, indexed here — a per-card query would fan out
  // into a systemd check per agent.
  const { data: telegramStatus } = useAgentsTelegramStatus();
  const telegramByAgent = new Map(
    (telegramStatus?.agents ?? []).map((entry) => [entry.agent_id, entry])
  );
  const telegramFor = (agentId: string) => telegramByAgent.get(agentId);

  // Crons and scripts live per-profile on disk, so they key off profile_slug
  // rather than agent id. Both are single roster-wide reads, indexed here.
  const { data: cronData } = useFoundationCrons();
  const { data: scriptData } = useFoundationAllScripts();
  const cronsFor = (profileSlug: string | null | undefined) =>
    profileSlug ? (cronData?.jobs ?? []).filter((job) => job.profile === profileSlug) : [];
  const scriptsFor = (profileSlug: string | null | undefined) =>
    profileSlug ? (scriptData ?? []).filter((script) => script.location === profileSlug) : [];

  // Top-level split: the in-house Hermes profiles (an actual layer/tier
  // hierarchy) vs the external CLI runtimes (a flat set of peers, each with
  // its own binary and config home).
  const externalAgents = agents.filter((agent) => isExternalRuntime(agent.runtime_type));
  const hermesAgents = agents.filter((agent) => !isExternalRuntime(agent.runtime_type));

  const athos = hermesAgents.find(isAthos);
  const mainDevelopmentAgents = hermesAgents.filter(
    (agent) => !isAthos(agent) && agent.runtime_tier === "A"
  );
  const specialists = hermesAgents.filter(
    (agent) => !isAthos(agent) && agent.runtime_tier !== "A"
  );
  const departments = mainDevelopmentAgents.map((leader) => ({
    name: leader.department || t("hierarchy.unclassifiedDepartment"),
    leader,
    specialists: specialists.filter(
      (agent) => agent.reports_to_profile_slug === leader.profile_slug
    ),
  }));
  const unassignedSpecialists = specialists.filter(
    (agent) =>
      !departments.some((department) =>
        department.specialists.some((member) => member.id === agent.id)
      )
  );
  const agentsWithoutApprovedSkills = agents.filter(
    (agent) => !skillsFor(agent.id).some((skill) => skill.is_approved)
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Network className="h-5 w-5" />
          {t("hierarchy.title")}
        </CardTitle>
        <CardDescription>{t("hierarchy.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Focused on one agent: the layer/tier structure and the baseline
            counters below are statements about the whole ecosystem, so they
            would be lies about a single-agent view — the card stands alone. */}
        {focusedAgent && (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="secondary">{t("hierarchy.focusedOn")}</Badge>
              <span>{t("hierarchy.focusedHint", { total: allAgents.length })}</span>
            </div>
            <AgentNode
              agent={focusedAgent}
              skills={skillsFor(focusedAgent.id)}
              telegram={telegramFor(focusedAgent.id)}
              crons={cronsFor(focusedAgent.profile_slug)}
              scripts={scriptsFor(focusedAgent.profile_slug)}
              onDelete={handleDeleteAgent}
              onDeleteSubAgent={handleDeleteSubAgent}
              orchestrator={isAthos(focusedAgent)}
            />
          </>
        )}

        {!focusedAgent && (
        <>
        <div className="flex flex-wrap gap-2 text-sm">
          <Badge variant={athos ? "success" : "destructive"}>
            {t("hierarchy.stats.orchestrator", { count: athos ? 1 : 0 })}
          </Badge>
          <Badge variant={mainDevelopmentAgents.length >= 7 ? "success" : "warning"}>
            {t("hierarchy.stats.departments", { count: mainDevelopmentAgents.length })}
          </Badge>
          <Badge variant="outline">
            {t("hierarchy.stats.specialists", { count: specialists.length })}
          </Badge>
          <Badge variant="warning">
            {t("hierarchy.stats.external", { count: externalAgents.length })}
          </Badge>
          <Badge variant="outline">
            {t("hierarchy.stats.workers", {
              count: agents.reduce((total, agent) => total + agent.sub_agents.length, 0),
            })}
          </Badge>
          <Badge variant={agentsWithoutApprovedSkills.length === 0 ? "success" : "destructive"}>
            {t("hierarchy.stats.withoutSkills", { count: agentsWithoutApprovedSkills.length })}
          </Badge>
        </div>

        {(!athos || mainDevelopmentAgents.length < 7) && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            {t("hierarchy.baselineWarning")}
          </div>
        )}

        {/* --- Hermes system agents --------------------------------------- */}
        <section className="space-y-4">
          <header className="border-b pb-2">
            <h3 className="flex items-center gap-2 font-semibold">
              <Workflow className="h-4 w-4" />
              {t("hierarchy.hermesSectionTitle")}
              <Badge variant="outline">{hermesAgents.length}</Badge>
            </h3>
            <p className="text-xs text-muted-foreground">{t("hierarchy.hermesSectionSubtitle")}</p>
          </header>

          {athos ? (
            <AgentNode
              agent={athos}
              skills={skillsFor(athos.id)}
              telegram={telegramFor(athos.id)}
              crons={cronsFor(athos.profile_slug)}
              scripts={scriptsFor(athos.profile_slug)}
              onDelete={handleDeleteAgent}
              onDeleteSubAgent={handleDeleteSubAgent}
              orchestrator
            />
          ) : (
            <div className="rounded-md border border-amber-500/40 p-3 text-sm">
              {t("hierarchy.athosMissing")}
            </div>
          )}

          {mainDevelopmentAgents.length > 0 && (
            <div className="flex justify-center text-muted-foreground">
              <ChevronDown className="h-5 w-5" />
            </div>
          )}

          {/* No outer scroll box here: capping the department list clipped
              cards mid-way, so a department card could show only its
              collapsed "Approved skills / Sub-agents" rows with its own
              header and leader scrolled out of sight. The per-card collapses
              already keep the chart short; the page scrolls as a whole. */}
          <div className="space-y-6">
            {departments
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((department) => (
                <section key={department.leader.id} className="rounded-lg border bg-muted/10 p-4">
                  <div className="mb-3">
                    <div className="font-semibold">
                      {t("hierarchy.departmentPrefix")} {department.name}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {t("hierarchy.responsibleTierA", { name: department.leader.name })}
                    </div>
                  </div>
                  <AgentNode
                    agent={department.leader}
                    skills={skillsFor(department.leader.id)}
                    telegram={telegramFor(department.leader.id)}
                    crons={cronsFor(department.leader.profile_slug)}
                    scripts={scriptsFor(department.leader.profile_slug)}
                    onDelete={handleDeleteAgent}
                    onDeleteSubAgent={handleDeleteSubAgent}
                  />
                  {department.specialists.length > 0 && (
                    <>
                      <div className="flex justify-center py-2 text-muted-foreground">
                        <ChevronDown className="h-4 w-4" />
                      </div>
                      <div className="grid gap-3 lg:grid-cols-2">
                        {department.specialists
                          .sort((a, b) => (a.sector || a.name).localeCompare(b.sector || b.name))
                          .map((agent) => (
                            <div key={agent.id}>
                              <div className="mb-1 text-xs font-medium text-muted-foreground">
                                {t("hierarchy.sectorPrefix")}{" "}
                                {agent.sector || t("hierarchy.unclassified")}
                              </div>
                              <AgentNode
                                agent={agent}
                                skills={skillsFor(agent.id)}
                                telegram={telegramFor(agent.id)}
                                crons={cronsFor(agent.profile_slug)}
                                scripts={scriptsFor(agent.profile_slug)}
                                onDelete={handleDeleteAgent}
                                onDeleteSubAgent={handleDeleteSubAgent}
                              />
                            </div>
                          ))}
                      </div>
                    </>
                  )}
                </section>
              ))}

            {unassignedSpecialists.length > 0 && (
              <section className="rounded-lg border border-amber-500/40 p-4">
                <div className="mb-2 font-semibold">{t("hierarchy.specialistsNoDepartment")}</div>
                <div className="grid gap-3 lg:grid-cols-2">
                  {unassignedSpecialists.map((agent) => (
                    <AgentNode
                      key={agent.id}
                      agent={agent}
                      skills={skillsFor(agent.id)}
                      telegram={telegramFor(agent.id)}
                      crons={cronsFor(agent.profile_slug)}
                      scripts={scriptsFor(agent.profile_slug)}
                      onDelete={handleDeleteAgent}
                      onDeleteSubAgent={handleDeleteSubAgent}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        </section>

        {/* --- External CLI runtimes -------------------------------------- */}
        {externalAgents.length > 0 && (
          <section className="space-y-3">
            <header className="border-b pb-2">
              <h3 className="flex items-center gap-2 font-semibold">
                <Plug className="h-4 w-4" />
                {t("hierarchy.externalSectionTitle")}
                <Badge variant="outline">{externalAgents.length}</Badge>
              </h3>
              <p className="text-xs text-muted-foreground">
                {t("hierarchy.externalSectionSubtitle")}
              </p>
            </header>
            <div className="grid gap-3 lg:grid-cols-2">
              {externalAgents
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((agent) => (
                  <AgentNode
                      key={agent.id}
                      agent={agent}
                      skills={skillsFor(agent.id)}
                      telegram={telegramFor(agent.id)}
                      crons={cronsFor(agent.profile_slug)}
                      scripts={scriptsFor(agent.profile_slug)}
                      onDelete={handleDeleteAgent}
                      onDeleteSubAgent={handleDeleteSubAgent}
                    />
                ))}
            </div>
          </section>
        )}

        {/* --- Retired / inactive ----------------------------------------- */}
        {retiredAgents.length > 0 && (
          <section className="space-y-3">
            <header className="border-b pb-2">
              <h3 className="flex items-center gap-2 font-semibold text-muted-foreground">
                <Archive className="h-4 w-4" />
                {t("hierarchy.retiredSectionTitle")}
                <Badge variant="outline">{retiredAgents.length}</Badge>
              </h3>
              <p className="text-xs text-muted-foreground">
                {t("hierarchy.retiredSectionSubtitle")}
              </p>
            </header>
            <div className="grid gap-3 opacity-70 lg:grid-cols-2">
              {retiredAgents
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((agent) => (
                  <AgentNode
                    key={agent.id}
                    agent={agent}
                    skills={skillsFor(agent.id)}
                    telegram={telegramFor(agent.id)}
                    crons={cronsFor(agent.profile_slug)}
                    scripts={scriptsFor(agent.profile_slug)}
                    onDelete={handleDeleteAgent}
                    onDeleteSubAgent={handleDeleteSubAgent}
                  />
                ))}
            </div>
          </section>
        )}
        </>
        )}
      </CardContent>

      <ConfirmDialog
        open={deleting !== null}
        title={
          deleting?.kind === "sub-agent"
            ? t("list.confirmDeleteSubAgentTitle", { name: deleting.subAgent.name })
            : t("list.confirmDeleteAgentTitle", { name: deleting?.agent.name ?? "" })
        }
        description={
          deleting?.kind === "sub-agent"
            ? t("list.confirmDeleteSubAgentDescription")
            : t("list.confirmDeleteAgentDescription")
        }
        confirmLabel={t("list.deleteConfirmLabel")}
        loading={deleteAgent.isPending || deleteSubAgent.isPending}
        onConfirm={() => {
          if (!deleting) return;
          if (deleting.kind === "sub-agent") {
            deleteSubAgent.mutate(
              { agentId: deleting.agent.id, subAgentId: deleting.subAgent.id },
              { onSuccess: () => setDeleting(null) }
            );
          } else {
            deleteAgent.mutate(deleting.agent.id, { onSuccess: () => setDeleting(null) });
          }
        }}
        onCancel={() => setDeleting(null)}
      />
    </Card>
  );
}
