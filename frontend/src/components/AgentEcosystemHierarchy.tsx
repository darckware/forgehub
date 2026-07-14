import { Bot, ChevronDown, Network, Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Agent, Skill } from "@/hooks/useAgent";

function isAthos(agent: Agent) {
  return agent.profile_slug?.toLowerCase() === "athos" || agent.name.toLowerCase() === "athos";
}

function functionText(agent: Agent) {
  return agent.mission || agent.description || `${agent.agent_type} agent`;
}

function AgentNode({ agent, skills, orchestrator = false }: { agent: Agent; skills: Skill[]; orchestrator?: boolean }) {
  return (
    <div className={orchestrator ? "rounded-lg border-2 border-primary/40 bg-primary/5 p-4" : "rounded-lg border p-4"}>
      <div className="flex flex-wrap items-center gap-2">
        {orchestrator ? <Workflow className="h-5 w-5 text-primary" /> : <Bot className="h-4 w-4" />}
        <span className="font-semibold">{agent.name}</span>
        {orchestrator && <Badge>Orchestrator</Badge>}
        <Badge variant="outline">{agent.agent_type}</Badge>
        {agent.layer && <Badge variant="secondary">{agent.layer}</Badge>}
        {agent.sector && <Badge variant="outline">{agent.sector}</Badge>}
        {agent.runtime_tier && <Badge variant="outline">Tier {agent.runtime_tier}</Badge>}
        <Badge variant={agent.forgerouter_api_key_configured ? "success" : "destructive"}>
          ForgeRouter key {agent.forgerouter_api_key_configured ? "configured" : "missing"}
        </Badge>
      </div>
      <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{functionText(agent)}</p>
      <div className="mt-3">
        <div className="mb-1 text-xs font-medium text-muted-foreground">Approved skills</div>
        <div className="flex flex-wrap gap-1">
          {skills.filter((skill) => skill.is_approved).map((skill) => <Badge key={skill.id} variant="secondary">{skill.name} · v{skill.version}</Badge>)}
          {!skills.some((skill) => skill.is_approved) && <Badge variant="destructive">No approved skill coverage</Badge>}
        </div>
      </div>
      {agent.sub_agents.length > 0 && (
        <div className="ml-3 mt-3 space-y-2 border-l pl-4">
          {agent.sub_agents.map((subAgent) => (
            <div key={subAgent.id} className="rounded-md bg-muted/40 p-2 text-sm">
              <span className="font-medium">{subAgent.name}</span>
              <span className="text-muted-foreground"> — {subAgent.description || subAgent.permission_scope || "Scoped worker"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function AgentEcosystemHierarchy({ agents, skills }: { agents: Agent[]; skills: Skill[] }) {
  const athos = agents.find(isAthos);
  const mainDevelopmentAgents = agents.filter((agent) => !isAthos(agent) && agent.runtime_tier === "A");
  const specialists = agents.filter((agent) => agent.runtime_tier !== "A");
  const departments = mainDevelopmentAgents.map((leader) => ({
    name: leader.department || "Unclassified department",
    leader,
    specialists: specialists.filter((agent) => agent.reports_to_profile_slug === leader.profile_slug),
  }));
  const unassignedSpecialists = specialists.filter(
    (agent) => !departments.some((department) => department.specialists.some((member) => member.id === agent.id))
  );
  const skillsFor = (agentId: string) => skills.filter((skill) => skill.agents.some((holder) => holder.agent_id === agentId));
  const agentsWithoutApprovedSkills = agents.filter((agent) => !skillsFor(agent.id).some((skill) => skill.is_approved));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl"><Network className="h-5 w-5" /> Agent ecosystem hierarchy</CardTitle>
        <CardDescription>Company-style organization: orchestration, seven main development responsibilities, specialist groups, and scoped workers.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2 text-sm">
          <Badge variant={athos ? "success" : "destructive"}>{athos ? 1 : 0}/1 orchestrator</Badge>
          <Badge variant={mainDevelopmentAgents.length >= 7 ? "success" : "warning"}>{mainDevelopmentAgents.length} main department agents · baseline 7</Badge>
          <Badge variant="outline">{specialists.length} Tier B specialists</Badge>
          <Badge variant="outline">{agents.reduce((total, agent) => total + agent.sub_agents.length, 0)} scoped workers</Badge>
          <Badge variant={agentsWithoutApprovedSkills.length === 0 ? "success" : "destructive"}>{agentsWithoutApprovedSkills.length} agents without approved skills</Badge>
        </div>
        {(!athos || mainDevelopmentAgents.length < 7) && (
          <div className="rounded-md border border-warning/40 bg-warning/5 p-3 text-sm">
            The registered ecosystem is below the current governed baseline: 1 Athos orchestrator + 7 main development agents. Future departments may expand this baseline.
          </div>
        )}
        {athos ? <AgentNode agent={athos} skills={skillsFor(athos.id)} orchestrator /> : <div className="rounded-md border border-warning/40 p-3 text-sm">Athos orchestrator is not registered.</div>}
        {mainDevelopmentAgents.length > 0 && <div className="flex justify-center text-muted-foreground"><ChevronDown className="h-5 w-5" /></div>}
        <div className="space-y-6">
          {departments.sort((a, b) => a.name.localeCompare(b.name)).map((department) => (
            <section key={department.leader.id} className="rounded-lg border bg-muted/10 p-4">
              <div className="mb-3">
                <div className="font-semibold">Department · {department.name}</div>
                <div className="text-xs text-muted-foreground">Responsible Tier A: {department.leader.name}</div>
              </div>
              <AgentNode agent={department.leader} skills={skillsFor(department.leader.id)} />
              {department.specialists.length > 0 && (
                <>
                  <div className="flex justify-center py-2 text-muted-foreground"><ChevronDown className="h-4 w-4" /></div>
                  <div className="grid gap-3 lg:grid-cols-2">
                    {department.specialists.sort((a, b) => (a.sector || a.name).localeCompare(b.sector || b.name)).map((agent) => (
                      <div key={agent.id}>
                        <div className="mb-1 text-xs font-medium text-muted-foreground">Sector · {agent.sector || "Unclassified"}</div>
                        <AgentNode agent={agent} skills={skillsFor(agent.id)} />
                      </div>
                    ))}
                  </div>
                </>
              )}
            </section>
          ))}
          {unassignedSpecialists.length > 0 && (
            <section className="rounded-lg border border-warning/40 p-4">
              <div className="mb-2 font-semibold">Specialists without department</div>
              <div className="grid gap-3 lg:grid-cols-2">
                {unassignedSpecialists.map((agent) => <AgentNode key={agent.id} agent={agent} skills={skillsFor(agent.id)} />)}
              </div>
            </section>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
