import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  Download,
  ExternalLink,
  FolderTree,
  Loader2,
  Pencil,
  ShieldAlert,
  KeyRound,
  Tag,
  Trash2,
  Users,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { TokenField } from "@/components/ui/token-field";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TelegramStatusBadge } from "@/components/TelegramStatusBadge";
import {
  isExternalRuntime,
  useAgent,
  useAgentsTelegramStatus,
  useImportAgentForgeRouterKey,
  useRemoveSkillFromAgent,
  useSkills,
  useUpdateAgent,
} from "@/hooks/useAgent";
import { PROJECT_AGENT_ROLES, useAgentMemberships } from "@/hooks/useOrchestration";
import { useProjects } from "@/hooks/useProject";
import { AgentProfileFilesCard } from "./AgentProfileFilesCard";
import { AgentAutomationCard } from "./AgentAutomationCard";
import { AgentMcpServersCard } from "./AgentMcpServersCard";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  active: "success",
  inactive: "outline",
  retired: "destructive",
};

const RISK_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  low: "outline",
  medium: "secondary",
  high: "warning",
  critical: "destructive",
};

/** The inverse of ProjectAutomationCard's "Project team" section -- which
 * projects is THIS agent actually on (2026-08-05, Software Factory
 * visibility fix: this view didn't exist before, so coordinating an
 * agent's workload across projects meant checking each project page one
 * by one). Read-only: managing membership stays on the project page. */
function AgentActiveProjectsCard({ agentId }: { agentId: string }) {
  const { t } = useTranslation("agent");
  const navigate = useNavigate();
  const { data: memberships = [] } = useAgentMemberships(agentId);
  const { data: projects = [] } = useProjects();
  const projectById = new Map(projects.map((p) => [p.id, p]));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Users className="h-5 w-5" />
          {t("detail.activeProjectsTitle")}
        </CardTitle>
        <CardDescription>{t("detail.activeProjectsDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        {memberships.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("detail.activeProjectsEmpty")}</p>
        ) : (
          <ul className="space-y-2">
            {memberships.map((m) => {
              const project = projectById.get(m.project_id);
              return (
                <li
                  key={m.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
                >
                  <div className="min-w-0">
                    <Link to={`/projects/${m.project_id}`} className="truncate text-sm font-medium hover:underline">
                      {project?.name ?? m.project_id}
                    </Link>
                    <p className="text-xs capitalize text-muted-foreground">{m.role}</p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate("/workspace", { state: { openChannel: { projectId: m.project_id } } })}
                  >
                    {t("detail.openProjectChannel")}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export default function AgentDetailPage() {
  const { t } = useTranslation("agent");
  const { id } = useParams<{ id: string }>();
  const { data: agent, isLoading, isError, error, refetch: refetchAgent } = useAgent(id);
  const { data: skillsCatalog } = useSkills();
  const { data: telegramStatus } = useAgentsTelegramStatus();
  const telegram = telegramStatus?.agents.find((entry) => entry.agent_id === id);

  const removeSkill = useRemoveSkillFromAgent(id ?? "");
  const updateAgent = useUpdateAgent(id ?? "");
  const importForgeRouterKey = useImportAgentForgeRouterKey(id ?? "");

  const [isEditingDescription, setIsEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [forgeRouterApiKey, setForgeRouterApiKey] = useState("");
  // Re-syncs to the server's (admin-only, decrypted) value whenever it
  // actually changes -- covers first load, switching agents, and a refetch
  // after Import/Save. Keyed on the value itself (not just agent.id) so an
  // in-progress unsaved paste isn't clobbered by an unrelated refetch that
  // returns the same value.
  useEffect(() => {
    if (agent) setForgeRouterApiKey(agent.forgerouter_api_key ?? "");
  }, [agent?.id, agent?.forgerouter_api_key]);

  // Explicit force-sync after Import/Save/Remove, instead of trusting the
  // effect above alone: that effect only re-runs when the *server* value
  // changes, so if the operator had typed something into the field first
  // (or it changed some other way) and the real stored key turns out to
  // already match ForgeRouter (Import's "no-op, already up to date" case),
  // the value never changes and the effect never fires -- leaving the
  // typed text stuck in the field looking like the click did nothing
  // (2026-07-29, Marcelo: "quando clico no botão import dentro do agente
  // ... não carrega"). Re-fetching and setting directly here always wins,
  // regardless of whether the value actually changed.
  async function syncForgeRouterFieldFromServer() {
    const { data: fresh } = await refetchAgent();
    setForgeRouterApiKey(fresh?.forgerouter_api_key ?? "");
  }
  // null = not editing; the field is prefilled with the *effective* path so
  // registering the runtime default is one click rather than retyping it.
  const [homePathDraft, setHomePathDraft] = useState<string | null>(null);
  // Destructive actions go through the system's standard ConfirmDialog
  // (2026-07-29, Marcelo: "todo o botão de limpar ou excluir precisa ter o
  // modal de confirmação padrão do sistema") rather than firing the
  // mutation straight from the icon button's onClick.
  const [confirmRemoveKey, setConfirmRemoveKey] = useState(false);
  const [confirmRemoveSkill, setConfirmRemoveSkill] = useState<{ id: string; name: string } | null>(null);

  function handleStartEditDescription() {
    setDescriptionDraft(agent?.description ?? "");
    setIsEditingDescription(true);
  }

  function handleCancelEditDescription() {
    setIsEditingDescription(false);
  }

  function handleSaveDescription() {
    updateAgent.mutate({ description: descriptionDraft }, {
      onSuccess: () => setIsEditingDescription(false),
    });
  }

  const skillById = new Map((skillsCatalog ?? []).map((s) => [s.id, s]));

  return (
    <div className="space-y-6">
      <Link
        to="/agents"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("detail.backToAgents")}
      </Link>

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("detail.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("detail.loadError", { message: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && agent && (
        <>
          <ConfirmDialog
            open={confirmRemoveKey}
            title={t("detail.confirmRemoveKeyTitle")}
            description={t("detail.confirmRemoveKeyDescription")}
            loading={updateAgent.isPending}
            onConfirm={() =>
              updateAgent.mutate(
                { clear_forgerouter_api_key: true },
                { onSuccess: () => { syncForgeRouterFieldFromServer(); setConfirmRemoveKey(false); } }
              )
            }
            onCancel={() => setConfirmRemoveKey(false)}
          />
          <ConfirmDialog
            open={confirmRemoveSkill !== null}
            title={t("detail.confirmRemoveSkillTitle", { name: confirmRemoveSkill?.name ?? "" })}
            description={t("detail.confirmRemoveSkillDescription")}
            loading={removeSkill.isPending}
            onConfirm={() => {
              if (confirmRemoveSkill) removeSkill.mutate(confirmRemoveSkill.id, { onSuccess: () => setConfirmRemoveSkill(null) });
            }}
            onCancel={() => setConfirmRemoveSkill(null)}
          />
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{agent.name}</h1>
              {agent.mission ? (
                <p className="mt-1 max-w-2xl text-muted-foreground">{agent.mission}</p>
              ) : (
                agent.description && (
                  <p className="mt-1 max-w-2xl text-muted-foreground">{agent.description}</p>
                )
              )}
              {agent.source_path && (
                <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                  <ExternalLink className="h-3 w-3" />
                  {agent.source_path}
                </p>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              <Badge variant={STATUS_VARIANT[agent.status] ?? "outline"} className="text-sm capitalize">
                {agent.status}
              </Badge>
              <Badge variant="outline" className="text-sm capitalize">
                {agent.agent_type}
              </Badge>
              {agent.runtime_type && (
                <Badge variant={isExternalRuntime(agent.runtime_type) ? "warning" : "secondary"}>
                  {t(`runtimes.${agent.runtime_type}`)}
                </Badge>
              )}
              <TelegramStatusBadge status={telegram} showLabel />
              {agent.profile_slug && (
                <>
                  {agent.layer && <Badge variant="secondary">{agent.layer}</Badge>}
                  {agent.runtime_tier && (
                    <Badge variant="outline">{t("detail.tierBadge", { tier: agent.runtime_tier })}</Badge>
                  )}
                  {agent.telegram_required && (
                    <Badge variant="outline">{t("detail.telegramBadge")}</Badge>
                  )}
                </>
              )}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl"><KeyRound className="h-5 w-5" /> {t("detail.apiKeyTitle")}</CardTitle>
              <CardDescription>
                {t("detail.apiKeyDescription")}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2 text-sm">
                <Badge variant={agent.forgerouter_api_key_configured ? "success" : "destructive"}>
                  {agent.forgerouter_api_key_configured ? t("detail.apiKeyConfigured") : t("detail.apiKeyNotConfigured")}
                </Badge>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  disabled={importForgeRouterKey.isPending}
                  title={t("detail.importKeyHelp")}
                  onClick={() => importForgeRouterKey.mutate(undefined, { onSuccess: syncForgeRouterFieldFromServer })}
                >
                  {importForgeRouterKey.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Download className="h-3.5 w-3.5" />
                  )}
                  {t("detail.importKeyButton")}
                </Button>
              </div>
              {importForgeRouterKey.isSuccess && (
                <p className={cn("text-sm", importForgeRouterKey.data.matched ? "text-emerald-500" : "text-muted-foreground")}>
                  {importForgeRouterKey.data.matched
                    ? importForgeRouterKey.data.updated
                      ? t("detail.importKeyUpdated")
                      : t("detail.importKeyUnchanged")
                    : t("detail.importKeyNotFound")}
                </p>
              )}
              {importForgeRouterKey.isError && (
                <p className="text-sm text-destructive">{(importForgeRouterKey.error as Error)?.message}</p>
              )}
              <div className="flex gap-2">
                <div className="flex-1">
                  <TokenField value={forgeRouterApiKey} onChange={setForgeRouterApiKey} placeholder={t("detail.apiKeyPlaceholder")} />
                </div>
                <Button disabled={!forgeRouterApiKey || updateAgent.isPending} onClick={() => updateAgent.mutate({ forgerouter_api_key: forgeRouterApiKey }, { onSuccess: syncForgeRouterFieldFromServer })}>
                  {updateAgent.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <KeyRound className="mr-2 h-4 w-4" />} {t("detail.saveKeyButton")}
                </Button>
                {agent.forgerouter_api_key_configured && (
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={updateAgent.isPending}
                    title={t("detail.removeKeyButton")}
                    aria-label={t("detail.removeKeyButton")}
                    onClick={() => setConfirmRemoveKey(true)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
              {updateAgent.isError && <p className="text-sm text-destructive">{(updateAgent.error as Error)?.message}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle className="text-xl">{t("detail.descriptionTitle")}</CardTitle>
                <CardDescription>{t("detail.descriptionSubtitle")}</CardDescription>
              </div>
              {!isEditingDescription && (
                <Button variant="outline" size="sm" onClick={handleStartEditDescription}>
                  <Pencil className="mr-2 h-4 w-4" />
                  {t("detail.editButton")}
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {isEditingDescription ? (
                <>
                  <Textarea className="resize-none"
                    value={descriptionDraft}
                    onChange={(e) => setDescriptionDraft(e.target.value)}
                    placeholder={t("detail.descriptionPlaceholder")}
                    rows={4}
                  />
                  {updateAgent.isError && (
                    <p className="text-sm text-destructive">
                      {t("detail.descriptionSaveError", { message: (updateAgent.error as Error)?.message })}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <Button onClick={handleSaveDescription} disabled={updateAgent.isPending}>
                      {updateAgent.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      {t("detail.saveButton")}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleCancelEditDescription}
                      disabled={updateAgent.isPending}
                    >
                      {t("detail.cancelButton")}
                    </Button>
                  </div>
                </>
              ) : agent.description ? (
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {agent.description}
                </p>
              ) : (
                <p className="text-sm italic text-muted-foreground">{t("detail.noDescription")}</p>
              )}
            </CardContent>
          </Card>

          {/* The agent's declared specialty (2026-08-05, see
              docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md) --
              a channel only ever suggests this when adding the agent as a
              member, never imposes it; always editable here directly. */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Tag className="h-5 w-5" />
                {t("detail.defaultRoleTitle")}
              </CardTitle>
              <CardDescription>{t("detail.defaultRoleDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <Select
                className="max-w-xs"
                value={agent.default_role ?? ""}
                onChange={(e) => updateAgent.mutate({ default_role: e.target.value || null })}
                disabled={updateAgent.isPending}
              >
                <option value="">{t("detail.defaultRoleNone")}</option>
                {PROJECT_AGENT_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role.replace(/_/g, " ")}
                  </option>
                ))}
              </Select>
            </CardContent>
          </Card>

          {/* Where the agent's profile files live. Registerable per agent
              because the runtime convention cannot cover everything: a
              runtime that moves its config dir, or a second agent sharing a
              runtime, needs an explicit path (see
              backend/app/core/agent_profile_files.py). */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <FolderTree className="h-5 w-5" />
                {t("homePath.title")}
              </CardTitle>
              <CardDescription>{t("homePath.description")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {homePathDraft === null ? (
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded bg-muted px-2 py-1 text-sm">
                    {agent.effective_home_path ?? t("homePath.none")}
                  </code>
                  <Badge variant={agent.home_path ? "secondary" : "outline"}>
                    {agent.home_path ? t("homePath.registered") : t("homePath.fromRuntime")}
                  </Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setHomePathDraft(agent.effective_home_path ?? "")}
                  >
                    <Pencil className="mr-2 h-4 w-4" />
                    {t("detail.editButton")}
                  </Button>
                </div>
              ) : (
                <>
                  <Input
                    value={homePathDraft}
                    onChange={(e) => setHomePathDraft(e.target.value)}
                    placeholder="/root/.hermes/profiles/<slug>"
                    className="font-mono text-sm"
                  />
                  <p className="text-xs text-muted-foreground">{t("homePath.hint")}</p>
                  {updateAgent.isError && (
                    <p className="text-sm text-destructive">{(updateAgent.error as Error)?.message}</p>
                  )}
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={updateAgent.isPending}
                      onClick={() =>
                        updateAgent.mutate(
                          { home_path: homePathDraft },
                          { onSuccess: () => setHomePathDraft(null) }
                        )
                      }
                    >
                      {updateAgent.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      {t("detail.saveButton")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={updateAgent.isPending}
                      onClick={() => setHomePathDraft(null)}
                    >
                      {t("detail.cancelButton")}
                    </Button>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <AgentProfileFilesCard agent={agent} />

          <AgentMcpServersCard agent={agent} />

          <AgentAutomationCard agent={agent} />

          <AgentActiveProjectsCard agentId={agent.id} />

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Users className="h-5 w-5" />
                {t("detail.subAgentsTitle")}
              </CardTitle>
              <CardDescription>
                {t("detail.subAgentsSubtitle")}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {agent.sub_agents && agent.sub_agents.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("detail.subAgentsColumns.name")}</TableHead>
                      <TableHead>{t("detail.subAgentsColumns.description")}</TableHead>
                      <TableHead>{t("detail.subAgentsColumns.status")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {agent.sub_agents.map((subAgent) => (
                      <TableRow key={subAgent.id}>
                        <TableCell className="font-medium">{subAgent.name}</TableCell>
                        <TableCell className="max-w-md truncate text-sm text-muted-foreground">
                          {subAgent.description ?? "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant={STATUS_VARIANT[subAgent.status] ?? "outline"}>
                            {subAgent.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm italic text-muted-foreground">{t("detail.noSubAgents")}</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <ShieldAlert className="h-5 w-5" />
                {t("detail.skillsTitle")}
              </CardTitle>
              <CardDescription>
                {t("detail.skillsSubtitle")}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {agent.agent_skills && agent.agent_skills.length > 0 ? (
                <div className="max-h-80 overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("detail.skillsColumns.skill")}</TableHead>
                        <TableHead>{t("detail.skillsColumns.origin")}</TableHead>
                        <TableHead>{t("detail.skillsColumns.risk")}</TableHead>
                        <TableHead>{t("detail.skillsColumns.approval")}</TableHead>
                        <TableHead className="text-right">{t("detail.skillsColumns.actions")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {agent.agent_skills.map((agentSkill) => {
                        const skill = skillById.get(agentSkill.skill_id);
                        return (
                          <TableRow key={agentSkill.id}>
                            <TableCell className="font-medium">
                              {skill?.name ?? agentSkill.skill_id}
                              {skill?.version && (
                                <span className="ml-1 text-xs text-muted-foreground">
                                  v{skill.version}
                                </span>
                              )}
                            </TableCell>
                            <TableCell className="text-sm text-muted-foreground capitalize">
                              {skill?.origin?.replace("_", " ") ?? "—"}
                            </TableCell>
                            <TableCell>
                              {skill?.risk_level ? (
                                <Badge variant={RISK_VARIANT[skill.risk_level] ?? "outline"}>
                                  {skill.risk_level}
                                </Badge>
                              ) : (
                                "—"
                              )}
                            </TableCell>
                            <TableCell className="text-sm text-muted-foreground">
                              {skill?.is_approved ? t("detail.approved") : t("detail.notApproved")}
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setConfirmRemoveSkill({ id: agentSkill.id, name: skill?.name ?? agentSkill.skill_id })}
                                disabled={removeSkill.isPending}
                                aria-label={t("detail.removeSkillAriaLabel", { name: skill?.name ?? agentSkill.skill_id })}
                              >
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="text-sm italic text-muted-foreground">
                  {t("detail.noSkills")}
                </p>
              )}
            </CardContent>
          </Card>

          <div>
            <Link to="/agents" className={buttonVariants({ variant: "outline" })}>
              {t("detail.backToList")}
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
