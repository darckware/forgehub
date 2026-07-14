import { useMemo, useState } from "react";
import { Bot, Loader2, Play, RefreshCw } from "lucide-react";
import { useAgents } from "@/hooks/useAgent";
import { useTaskExecutions, type TaskExecution } from "@/hooks/useTask";
import {
  useCreateTaskAssignment,
  useDecideExecutionReview,
  useDispatchExecutionReview,
  useDispatchTask,
  useEligibleMemberships,
  useExecutionReviews,
  useProjectLoopPolicies,
  useRefreshExecution,
  useRefreshExecutionReview,
  useRuntimeProfiles,
  useTaskAssignments,
} from "@/hooks/useOrchestration";
import { useRefreshGovernedExecution } from "@/hooks/useExecutionRuntime";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

function AutomatedExecutionRow({ taskId, execution }: { taskId: string; execution: TaskExecution }) {
  const { data: reviews = [] } = useExecutionReviews(execution.id);
  const dispatchReview = useDispatchExecutionReview(taskId);
  const refreshReview = useRefreshExecutionReview(taskId);
  const decideReview = useDecideExecutionReview(taskId);
  const activeReview = reviews.find((review) => ["running", "pending"].includes(review.status));
  return (
    <div className="space-y-2 rounded-md border p-3 text-sm">
      <div className="flex items-center justify-between">
        <div><span className="font-medium">Attempt #{execution.attempt_number}</span> · {execution.runtime_type} · loop {execution.loop_iteration}<Badge className="ml-2" variant="outline">{execution.status}</Badge></div>
        {execution.status === "completed" && execution.loop_policy_id && !activeReview && (
          <Button size="sm" variant="outline" disabled={dispatchReview.isPending} onClick={() => dispatchReview.mutate(execution.id)}>Review with loop model</Button>
        )}
      </div>
      {reviews.map((review) => (
        <div key={review.id} className="flex items-center justify-between gap-2 rounded bg-muted/50 p-2 text-xs">
          <span>Review: {review.status}{review.score != null ? ` · ${review.score}/100` : ""}</span>
          {review.status === "running" && <Button size="sm" variant="ghost" disabled={refreshReview.isPending} onClick={() => refreshReview.mutate({ reviewId: review.id, executionId: execution.id })}><RefreshCw className="mr-1 h-3 w-3" />Refresh review</Button>}
          {review.status === "pending" && review.feedback && <span className="flex gap-1"><Button size="sm" variant="outline" disabled={decideReview.isPending} onClick={() => decideReview.mutate({ reviewId: review.id, executionId: execution.id, status: "changes_requested", feedback: review.feedback ?? "Changes requested" })}>Request changes</Button><Button size="sm" disabled={decideReview.isPending} onClick={() => decideReview.mutate({ reviewId: review.id, executionId: execution.id, status: "approved", feedback: review.feedback ?? "Approved" })}>Approve</Button></span>}
        </div>
      ))}
      {(dispatchReview.error || refreshReview.error || decideReview.error) && <p className="text-xs text-destructive">{((dispatchReview.error ?? refreshReview.error ?? decideReview.error) as Error).message}</p>}
    </div>
  );
}

export function TaskAutomationCard({ taskId, projectId }: { taskId: string; projectId?: string }) {
  const { data: agents = [] } = useAgents();
  const { data: eligibility = [] } = useEligibleMemberships(taskId);
  const { data: assignments = [] } = useTaskAssignments(taskId);
  const { data: profiles = [] } = useRuntimeProfiles();
  const { data: policies = [] } = useProjectLoopPolicies(projectId);
  const { data: executions = [] } = useTaskExecutions(taskId);
  const createAssignment = useCreateTaskAssignment(taskId);
  const dispatch = useDispatchTask(taskId);
  const refresh = useRefreshExecution(taskId);
  const refreshGoverned = useRefreshGovernedExecution(taskId);
  const [membershipId, setMembershipId] = useState("");
  const [assignmentId, setAssignmentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [policyId, setPolicyId] = useState("");
  const [mode, setMode] = useState("execute");
  const [addendum, setAddendum] = useState("");

  const eligibleMemberships = eligibility.filter((item) => item.eligible);
  const memberMap = useMemo(
    () => new Map(eligibility.map((item) => [item.membership.id, item.membership])),
    [eligibility]
  );
  const selectedAssignment = assignments.find((item) => item.id === assignmentId);
  const selectedMembership = selectedAssignment?.membership_id
    ? memberMap.get(selectedAssignment.membership_id)
    : undefined;
  const availableProfiles = profiles.filter((profile) =>
    selectedMembership?.agent_id
      ? profile.agent_id === selectedMembership.agent_id
      : profile.sub_agent_id === selectedMembership?.sub_agent_id
  );
  const agentName = (id?: string | null) => agents.find((agent) => agent.id === id)?.name ?? "Agent";
  const error = createAssignment.error ?? dispatch.error ?? refresh.error ?? refreshGoverned.error;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl"><Bot className="h-5 w-5" /> Governed CLI execution</CardTitle>
        <CardDescription>
          Assign an eligible registered agent, then run Claude, Codex, or Agy through this project's existing ForgeRouter configuration.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 md:grid-cols-[1fr_auto]">
          <div>
            <Label>Eligible project member</Label>
            <Select value={membershipId} onChange={(event) => setMembershipId(event.target.value)}>
              <option value="">Select agent membership</option>
              {eligibleMemberships.map(({ membership }) => (
                <option key={membership.id} value={membership.id}>
                  {agentName(membership.agent_id)} · {membership.role.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </div>
          <Button
            className="self-end"
            variant="outline"
            disabled={!membershipId || createAssignment.isPending}
            onClick={() => {
              const member = memberMap.get(membershipId);
              if (!member) return;
              createAssignment.mutate({ membership_id: member.id, agent_id: member.agent_id, sub_agent_id: member.sub_agent_id });
            }}
          >
            {createAssignment.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Assign
          </Button>
        </div>
        {eligibility.some((item) => !item.eligible) && (
          <details className="text-xs text-muted-foreground">
            <summary>Why some project agents are not eligible</summary>
            <ul className="mt-2 space-y-1">
              {eligibility.filter((item) => !item.eligible).map((item) => (
                <li key={item.membership.id}>{agentName(item.membership.agent_id)}: {item.reasons.join("; ")}</li>
              ))}
            </ul>
          </details>
        )}

        <div className="grid gap-3 border-t pt-5 md:grid-cols-2 lg:grid-cols-4">
          <div><Label>Active assignment</Label><Select value={assignmentId} onChange={(event) => { setAssignmentId(event.target.value); setProfileId(""); }}><option value="">Select assignment</option>{assignments.filter((a) => a.status === "active" && a.membership_id).map((a) => <option key={a.id} value={a.id}>{agentName(a.agent_id)}</option>)}</Select></div>
          <div><Label>ForgeRouter runtime profile</Label><Select value={profileId} onChange={(event) => setProfileId(event.target.value)}><option value="">Select runtime</option>{availableProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name} · {profile.runtime_type} · {profile.routing_group}</option>)}</Select></div>
          <div><Label>Loop policy</Label><Select value={policyId} onChange={(event) => setPolicyId(event.target.value)}><option value="">Single execution</option>{policies.filter((p) => p.is_active).map((policy) => <option key={policy.id} value={policy.id}>{policy.name}</option>)}</Select></div>
          <div><Label>Mode</Label><Select value={mode} onChange={(event) => setMode(event.target.value)}><option value="execute">Execute/edit</option><option value="plan">Plan/read-only</option></Select></div>
        </div>
        <div><Label>Additional governed instructions (optional)</Label><Textarea value={addendum} onChange={(event) => setAddendum(event.target.value)} placeholder="Task-specific constraints; never paste secrets." /></div>
        <Button
          disabled
        >
          {dispatch.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
          Use Planning &gt; Execution Release to dispatch
        </Button>

        {executions.filter((execution) => execution.runtime_session_ref).length > 0 && (
          <div className="space-y-2 border-t pt-5">
            <p className="text-sm font-medium">Automated runs</p>
            {executions.filter((execution) => execution.runtime_session_ref).map((execution) => (
              <div key={execution.id} className="space-y-2">
                {execution.status === "running" && <div className="flex justify-end"><Button size="sm" variant="outline" disabled={refresh.isPending || refreshGoverned.isPending} onClick={() => execution.work_package_id ? refreshGoverned.mutate(execution.id) : refresh.mutate(execution.id)}><RefreshCw className="mr-2 h-4 w-4" />Refresh execution</Button></div>}
                <AutomatedExecutionRow taskId={taskId} execution={execution} />
              </div>
            ))}
          </div>
        )}
        {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}
      </CardContent>
    </Card>
  );
}
