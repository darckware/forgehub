import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  ExternalLink,
  Loader2,
  Pencil,
  ShieldAlert,
  KeyRound,
  Trash2,
  Users,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAgent, useRemoveSkillFromAgent, useSkills, useUpdateAgent } from "@/hooks/useAgent";
import { ProfileFilesCard } from "./ProfileFilesCard";

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

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: agent, isLoading, isError, error } = useAgent(id);
  const { data: skillsCatalog } = useSkills();

  const removeSkill = useRemoveSkillFromAgent(id ?? "");
  const updateAgent = useUpdateAgent(id ?? "");

  const [isEditingDescription, setIsEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [forgeRouterApiKey, setForgeRouterApiKey] = useState("");

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
        Back to agents
      </Link>

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading agent…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load agent: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && agent && (
        <>
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
              {agent.profile_slug && (
                <>
                  {agent.layer && <Badge variant="secondary">{agent.layer}</Badge>}
                  {agent.runtime_tier && <Badge variant="outline">Tier {agent.runtime_tier}</Badge>}
                  {agent.telegram_required && <Badge variant="outline">Telegram</Badge>}
                </>
              )}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl"><KeyRound className="h-5 w-5" /> ForgeRouter API key</CardTitle>
              <CardDescription>
                Individual credential used only when this agent runs Claude, Codex, or Agy. The saved value is encrypted and never displayed again.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2 text-sm">
                <Badge variant={agent.forgerouter_api_key_configured ? "success" : "destructive"}>
                  {agent.forgerouter_api_key_configured ? "Configured" : "Not configured"}
                </Badge>
              </div>
              <div className="flex gap-2">
                <Input type="password" autoComplete="new-password" value={forgeRouterApiKey} onChange={(e) => setForgeRouterApiKey(e.target.value)} placeholder="Paste this agent's ForgeRouter key" />
                <Button disabled={!forgeRouterApiKey || updateAgent.isPending} onClick={() => updateAgent.mutate({ forgerouter_api_key: forgeRouterApiKey }, { onSuccess: () => setForgeRouterApiKey("") })}>
                  {updateAgent.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <KeyRound className="mr-2 h-4 w-4" />} Save key
                </Button>
                {agent.forgerouter_api_key_configured && <Button variant="outline" disabled={updateAgent.isPending} onClick={() => updateAgent.mutate({ clear_forgerouter_api_key: true })}>Remove</Button>}
              </div>
              {updateAgent.isError && <p className="text-sm text-destructive">{(updateAgent.error as Error)?.message}</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle className="text-xl">Description</CardTitle>
                <CardDescription>Manual description for this agent.</CardDescription>
              </div>
              {!isEditingDescription && (
                <Button variant="outline" size="sm" onClick={handleStartEditDescription}>
                  <Pencil className="mr-2 h-4 w-4" />
                  Edit
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {isEditingDescription ? (
                <>
                  <Textarea
                    value={descriptionDraft}
                    onChange={(e) => setDescriptionDraft(e.target.value)}
                    placeholder="Describe this agent…"
                    rows={4}
                  />
                  {updateAgent.isError && (
                    <p className="text-sm text-destructive">
                      Failed to save description: {(updateAgent.error as Error)?.message}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <Button onClick={handleSaveDescription} disabled={updateAgent.isPending}>
                      {updateAgent.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      Save
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleCancelEditDescription}
                      disabled={updateAgent.isPending}
                    >
                      Cancel
                    </Button>
                  </div>
                </>
              ) : agent.description ? (
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                  {agent.description}
                </p>
              ) : (
                <p className="text-sm italic text-muted-foreground">No description yet.</p>
              )}
            </CardContent>
          </Card>

          {agent.profile_slug && <ProfileFilesCard profileSlug={agent.profile_slug} />}

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Users className="h-5 w-5" />
                Sub-agents
              </CardTitle>
              <CardDescription>
                Subordinate agents with scoped permissions and skills, inherited from this agent.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {agent.sub_agents && agent.sub_agents.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Status</TableHead>
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
                <p className="text-sm italic text-muted-foreground">No sub-agents yet.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <ShieldAlert className="h-5 w-5" />
                Skills
              </CardTitle>
              <CardDescription>
                Versioned, governed capabilities associated with this agent, with risk level and
                permission boundaries.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {agent.agent_skills && agent.agent_skills.length > 0 ? (
                <div className="max-h-80 overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Skill</TableHead>
                        <TableHead>Origin</TableHead>
                        <TableHead>Risk</TableHead>
                        <TableHead>Approval</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
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
                              {skill?.is_approved ? "Approved" : "Not approved"}
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => removeSkill.mutate(agentSkill.id)}
                                disabled={removeSkill.isPending}
                                aria-label={`Remove skill ${skill?.name ?? agentSkill.skill_id}`}
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
                  No skills associated with this agent yet.
                </p>
              )}
            </CardContent>
          </Card>

          <div>
            <Link to="/agents" className={buttonVariants({ variant: "outline" })}>
              Back to list
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
