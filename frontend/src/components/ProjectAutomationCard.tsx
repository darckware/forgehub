import { useMemo, useState } from "react";
import { Bot, BrainCircuit, Loader2, Plus, Repeat2 } from "lucide-react";
import { useAgents } from "@/hooks/useAgent";
import {
  LOOP_PHASES,
  FORGEROUTER_ROUTING_GROUPS,
  PROJECT_AGENT_ROLES,
  RUNTIME_TYPES,
  useCreateProjectLoopPolicy,
  useCreateProjectMembership,
  useCreateRuntimeProfile,
  useProjectLoopPolicies,
  useProjectMemberships,
  useRuntimeProfiles,
} from "@/hooks/useOrchestration";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

export function ProjectAutomationCard({ projectId }: { projectId: string }) {
  const { data: agents = [] } = useAgents();
  const { data: memberships = [] } = useProjectMemberships(projectId);
  const { data: profiles = [] } = useRuntimeProfiles();
  const { data: policies = [] } = useProjectLoopPolicies(projectId);
  const createMembership = useCreateProjectMembership(projectId);
  const createProfile = useCreateRuntimeProfile();
  const createPolicy = useCreateProjectLoopPolicy(projectId);

  const activeAgents = agents.filter((agent) => agent.is_active && agent.status === "active");
  const [memberAgentId, setMemberAgentId] = useState("");
  const [memberRole, setMemberRole] = useState("developer");
  const [profileAgentId, setProfileAgentId] = useState("");
  const [profileName, setProfileName] = useState("");
  const [runtimeType, setRuntimeType] = useState("codex");
  const [modelRef, setModelRef] = useState("forgerouter/auto");
  const [routingGroup, setRoutingGroup] = useState("auto");
  const [purpose, setPurpose] = useState("implementation");
  const [policyName, setPolicyName] = useState("");
  const [phase, setPhase] = useState("implementation");
  const [producerMembershipId, setProducerMembershipId] = useState("");
  const [reviewerMembershipId, setReviewerMembershipId] = useState("");
  const [producerProfileId, setProducerProfileId] = useState("");
  const [reviewerProfileId, setReviewerProfileId] = useState("");
  const [maxIterations, setMaxIterations] = useState(3);
  const [minScore, setMinScore] = useState(80);
  const [autoDispatch, setAutoDispatch] = useState(false);
  const [requiresHumanApproval, setRequiresHumanApproval] = useState(true);

  const agentName = (id?: string | null) => agents.find((a) => a.id === id)?.name ?? "Unknown agent";
  const memberById = useMemo(
    () => new Map(memberships.map((membership) => [membership.id, membership])),
    [memberships]
  );

  const mutationError = createMembership.error ?? createProfile.error ?? createPolicy.error;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <BrainCircuit className="h-5 w-5" /> Agent automation &amp; engineering loops
        </CardTitle>
        <CardDescription>
          ForgeRouter remains the model gateway. ForgeHub authorizes project agents, records which
          Claude/Codex/Agy runtime they use, and bounds producer/reviewer correction loops.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section className="space-y-3">
          <div className="flex items-center gap-2 font-medium"><Bot className="h-4 w-4" /> Project team</div>
          <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
            <Select value={memberAgentId} onChange={(e) => setMemberAgentId(e.target.value)}>
              <option value="">Select registered agent</option>
              {activeAgents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
            </Select>
            <Select value={memberRole} onChange={(e) => setMemberRole(e.target.value)}>
              {PROJECT_AGENT_ROLES.map((role) => <option key={role} value={role}>{role.replace(/_/g, " ")}</option>)}
            </Select>
            <Button
              disabled={!memberAgentId || createMembership.isPending}
              onClick={() => createMembership.mutate({
                agent_id: memberAgentId,
                role: memberRole,
                allowed_runtimes: [...RUNTIME_TYPES],
                can_review: ["reviewer", "qa", "security_reviewer", "architect"].includes(memberRole),
                can_approve: ["coordinator", "release_manager"].includes(memberRole),
              }, { onSuccess: () => setMemberAgentId("") })}
            >
              {createMembership.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
              Add
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {memberships.map((membership) => (
              <Badge key={membership.id} variant={membership.status === "active" ? "secondary" : "outline"}>
                {agentName(membership.agent_id)} · {membership.role.replace(/_/g, " ")}
                {membership.can_review ? " · reviewer" : ""}
              </Badge>
            ))}
            {!memberships.length && <p className="text-sm text-muted-foreground">No registered agents assigned yet.</p>}
          </div>
        </section>

        <section className="space-y-3 border-t pt-5">
          <div className="font-medium">ForgeRouter runtime profiles</div>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div><Label>Agent</Label><Select value={profileAgentId} onChange={(e) => setProfileAgentId(e.target.value)}><option value="">Select agent</option>{activeAgents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</Select></div>
            <div><Label>Profile name</Label><Input value={profileName} onChange={(e) => setProfileName(e.target.value)} placeholder="Fast draft / Deep review" /></div>
            <div><Label>CLI runtime</Label><Select value={runtimeType} onChange={(e) => setRuntimeType(e.target.value)}>{RUNTIME_TYPES.map((runtime) => <option key={runtime} value={runtime}>{runtime}</option>)}</Select></div>
            <div><Label>ForgeRouter routing class</Label><Select value={routingGroup} onChange={(e) => setRoutingGroup(e.target.value)}>{FORGEROUTER_ROUTING_GROUPS.map((group) => <option key={group} value={group}>{group}</option>)}</Select></div>
            <div><Label>Specific model override</Label><Input value={modelRef} onChange={(e) => setModelRef(e.target.value)} /></div>
            <div><Label>Purpose</Label><Select value={purpose} onChange={(e) => setPurpose(e.target.value)}>{["general", "draft", "review", "implementation", "testing"].map((p) => <option key={p} value={p}>{p}</option>)}</Select></div>
          </div>
          <Button
            variant="outline"
            disabled={!profileAgentId || !profileName || createProfile.isPending}
            onClick={() => createProfile.mutate({ agent_id: profileAgentId, name: profileName, runtime_type: runtimeType, model_ref: modelRef, routing_group: routingGroup, purpose }, { onSuccess: () => setProfileName("") })}
          >
            {createProfile.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save runtime profile
          </Button>
          <div className="grid gap-2 md:grid-cols-2">
            {profiles.map((profile) => (
              <div key={profile.id} className="rounded-md border p-3 text-sm">
                <span className="font-medium">{profile.name}</span> · {agentName(profile.agent_id)}
                <p className="text-muted-foreground">{profile.runtime_type} → ForgeRouter/{profile.routing_group}{profile.model_ref !== "forgerouter/auto" ? ` → ${profile.model_ref}` : ""}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-3 border-t pt-5">
          <div className="flex items-center gap-2 font-medium"><Repeat2 className="h-4 w-4" /> Bounded producer/reviewer loop</div>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div><Label>Name</Label><Input value={policyName} onChange={(e) => setPolicyName(e.target.value)} placeholder="Implementation correction loop" /></div>
            <div><Label>Phase</Label><Select value={phase} onChange={(e) => setPhase(e.target.value)}>{LOOP_PHASES.map((p) => <option key={p} value={p}>{p}</option>)}</Select></div>
            <div><Label>Producer</Label><Select value={producerMembershipId} onChange={(e) => setProducerMembershipId(e.target.value)}><option value="">Select member</option>{memberships.map((m) => <option key={m.id} value={m.id}>{agentName(m.agent_id)} · {m.role}</option>)}</Select></div>
            <div><Label>Producer runtime</Label><Select value={producerProfileId} onChange={(e) => setProducerProfileId(e.target.value)}><option value="">Select profile</option>{profiles.filter((p) => p.agent_id === memberById.get(producerMembershipId)?.agent_id).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></div>
            <div><Label>Reviewer</Label><Select value={reviewerMembershipId} onChange={(e) => setReviewerMembershipId(e.target.value)}><option value="">Select reviewer</option>{memberships.filter((m) => m.can_review).map((m) => <option key={m.id} value={m.id}>{agentName(m.agent_id)} · {m.role}</option>)}</Select></div>
            <div><Label>Reviewer runtime</Label><Select value={reviewerProfileId} onChange={(e) => setReviewerProfileId(e.target.value)}><option value="">Select profile</option>{profiles.filter((p) => p.agent_id === memberById.get(reviewerMembershipId)?.agent_id).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></div>
            <div><Label>Maximum iterations</Label><Input type="number" min={1} max={20} value={maxIterations} onChange={(e) => setMaxIterations(Number(e.target.value))} /></div>
            <div><Label>Minimum review score</Label><Input type="number" min={0} max={100} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} /></div>
            <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" checked={autoDispatch} onChange={(e) => setAutoDispatch(e.target.checked)} /> Auto-dispatch corrections</label>
            <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" checked={requiresHumanApproval} onChange={(e) => setRequiresHumanApproval(e.target.checked)} /> Require human final approval</label>
          </div>
          <Button
            disabled={!policyName || !producerMembershipId || !reviewerMembershipId || !producerProfileId || !reviewerProfileId || createPolicy.isPending}
            onClick={() => createPolicy.mutate({ name: policyName, phase, producer_membership_id: producerMembershipId, reviewer_membership_id: reviewerMembershipId, producer_runtime_profile_id: producerProfileId, reviewer_runtime_profile_id: reviewerProfileId, max_iterations: maxIterations, min_review_score: minScore, requires_human_approval: requiresHumanApproval, auto_dispatch: autoDispatch }, { onSuccess: () => setPolicyName("") })}
          >
            {createPolicy.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Create loop policy
          </Button>
          <div className="space-y-2">
            {policies.map((policy) => <div key={policy.id} className="rounded-md border p-3 text-sm"><span className="font-medium">{policy.name}</span> · {policy.phase}<p className="text-muted-foreground">Up to {policy.max_iterations} iterations · score ≥ {policy.min_review_score} · human approval {policy.requires_human_approval ? "required" : "optional"}</p></div>)}
          </div>
        </section>

        {mutationError && <p className="text-sm text-destructive">{(mutationError as Error).message}</p>}
      </CardContent>
    </Card>
  );
}
