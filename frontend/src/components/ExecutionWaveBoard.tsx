import { useMemo, useState } from "react";
import { Activity, Loader2, PackageCheck, Play, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useActionPermission } from "@/hooks/usePermission";
import { usePlanBaselines, useProjects } from "@/hooks/useProject";
import { useTasks, type ProjectTask } from "@/hooks/useTask";
import { useRuntimeProfiles, useTaskAssignments } from "@/hooks/useOrchestration";
import { useBuildWorkPackage, useCreateExecutionWave, useExecutionWaves, usePackageAction, useWaveAction, useWorkPackages, type ExecutionWave, type WorkPackage } from "@/hooks/useExecutionRuntime";

const errorText = (value: unknown) => value instanceof Error ? value.message : "The command could not be completed.";

function TaskPackageRow({ projectId, wave, task, packages }: { projectId: string; wave: ExecutionWave; task: ProjectTask; packages: WorkPackage[] }) {
  const { data: assignments = [] } = useTaskAssignments(task.id);
  const { data: profiles = [] } = useRuntimeProfiles();
  const build = useBuildWorkPackage(projectId, wave.id, task.id);
  const command = usePackageAction(projectId, wave.id);
  const [assignmentId, setAssignmentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [allowedPaths, setAllowedPaths] = useState(".");
  const [acceptance, setAcceptance] = useState("");
  const [done, setDone] = useState("Relevant tests pass\nNo scope expansion");
  const latest = packages.find((item) => item.task_id === task.id);
  const selectedAssignment = assignments.find((item) => item.id === assignmentId);
  const availableProfiles = profiles.filter((profile) => selectedAssignment?.agent_id ? profile.agent_id === selectedAssignment.agent_id : profile.sub_agent_id === selectedAssignment?.sub_agent_id);
  const canDispatch = useActionPermission("planning.execution.dispatch");

  return <div className="space-y-3 rounded-md border p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><div><span className="font-medium">{task.title}</span> <Badge variant="outline">{task.status}</Badge></div>{latest && <span className="text-xs text-muted-foreground">Package r{latest.revision} · {latest.status}</span>}</div>
    {!latest && wave.status === "active" && <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
      <div><Label>Assignment</Label><Select value={assignmentId} onChange={(event) => { setAssignmentId(event.target.value); setProfileId(""); }}><option value="">Select active assignment</option>{assignments.filter((item) => item.status === "active" && item.membership_id).map((item) => <option key={item.id} value={item.id}>{item.id.slice(0, 8)} · {item.agent_id ? "agent" : "sub-agent"}</option>)}</Select></div>
      <div><Label>Runtime profile</Label><Select value={profileId} onChange={(event) => setProfileId(event.target.value)}><option value="">Select runtime</option>{availableProfiles.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.runtime_type}</option>)}</Select></div>
      <div><Label>Allowed paths</Label><Input value={allowedPaths} onChange={(event) => setAllowedPaths(event.target.value)} placeholder="frontend/src, backend/app" /></div>
      <div><Label>Acceptance criteria</Label><Input value={acceptance} onChange={(event) => setAcceptance(event.target.value)} placeholder="One criterion per line" /></div>
      <div><Label>Definition of Done</Label><Input value={done} onChange={(event) => setDone(event.target.value)} /></div>
      <Button className="self-end" variant="outline" disabled={!assignmentId || !profileId || !acceptance.trim() || build.isPending} onClick={() => build.mutate({ assignment_id: assignmentId, runtime_profile_id: profileId, allowed_paths: allowedPaths.split(",").map((item) => item.trim()).filter(Boolean), acceptance_criteria: acceptance.split("\n").filter(Boolean), definition_of_done: done.split("\n").filter(Boolean), verification_commands: [], idempotency_key: `ui-${wave.id}-${task.id}-${Date.now()}` })}>{build.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Build package</Button>
    </div>}
    {latest && <div className="flex flex-wrap items-center gap-2 text-xs"><span>Hash {latest.payload_hash.slice(0, 12)}</span>{latest.validation_errors.length > 0 && <span className="text-destructive">{latest.validation_errors.join(", ")}</span>}{latest.status === "validated" && canDispatch && <Button size="sm" variant="outline" disabled={command.isPending} onClick={() => command.mutate({ packageId: latest.id, action: "issue" })}><PackageCheck className="mr-1 h-3 w-3" />Issue</Button>}{latest.status === "issued" && canDispatch && <Button size="sm" disabled={command.isPending} onClick={() => command.mutate({ packageId: latest.id, action: "dispatch" })}><Play className="mr-1 h-3 w-3" />Dispatch CLI</Button>}</div>}
    {(build.error || command.error) && <p className="text-xs text-destructive">{errorText(build.error ?? command.error)}</p>}
  </div>;
}

function WaveCard({ projectId, wave, tasks }: { projectId: string; wave: ExecutionWave; tasks: ProjectTask[] }) {
  const action = useWaveAction(projectId);
  const { data: packages = [] } = useWorkPackages(wave.id);
  const canManage = useActionPermission("planning.execution.manage");
  const canRelease = useActionPermission("planning.execution.release");
  const links = wave.preflight_snapshot?.tasks ?? [];
  const waveTasks = tasks.filter((task) => links.some((item) => item.task_id === task.id) || packages.some((item) => item.task_id === task.id));
  const run = (name: "preflight" | "approve" | "activate" | "pause" | "resume" | "complete") => action.mutate({ waveId: wave.id, action: name });
  return <Card><CardHeader><div className="flex flex-wrap items-center justify-between gap-2"><div><CardTitle className="text-lg">{wave.name}</CardTitle><CardDescription>WIP {wave.wip_limit} · baseline {wave.baseline_id.slice(0, 8)}</CardDescription></div><Badge>{wave.status}</Badge></div></CardHeader><CardContent className="space-y-4">
    <div className="flex flex-wrap gap-2">{wave.status === "draft" && canManage && <Button size="sm" variant="outline" onClick={() => run("preflight")}>Preflight</Button>}{wave.status === "draft" && canRelease && <Button size="sm" onClick={() => run("approve")}><ShieldCheck className="mr-1 h-3 w-3" />Approve</Button>}{wave.status === "approved" && canManage && <Button size="sm" onClick={() => run("activate")}>Activate</Button>}{wave.status === "active" && canManage && <Button size="sm" variant="outline" onClick={() => run("pause")}>Pause</Button>}{wave.status === "paused" && canManage && <Button size="sm" onClick={() => run("resume")}>Resume</Button>}{["active", "paused"].includes(wave.status) && canManage && <Button size="sm" variant="outline" onClick={() => run("complete")}>Complete wave</Button>}</div>
    {links.length > 0 && <div className="space-y-1 text-xs">{links.map((item) => <div key={item.task_id} className={item.eligible ? "text-emerald-600" : "text-destructive"}>{item.task_id.slice(0, 8)} · {item.eligible ? "eligible" : item.reasons.join(", ")}</div>)}</div>}
    {waveTasks.map((task) => <TaskPackageRow key={task.id} projectId={projectId} wave={wave} task={task} packages={packages} />)}
    {action.error && <p className="text-xs text-destructive">{errorText(action.error)}</p>}
  </CardContent></Card>;
}

export function ExecutionWaveBoard() {
  const { data: projects = [] } = useProjects();
  const { data: tasks = [] } = useTasks();
  const [projectId, setProjectId] = useState("");
  const { data: baselines = [] } = usePlanBaselines(projectId || undefined);
  const { data: waves = [], isLoading } = useExecutionWaves(projectId || undefined);
  const create = useCreateExecutionWave(projectId);
  const canManage = useActionPermission("planning.execution.manage");
  const [baselineId, setBaselineId] = useState("");
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const projectTasks = useMemo(() => tasks.filter((task) => task.project_id === projectId), [tasks, projectId]);
  const planned = projectTasks.filter((task) => ["planned", "assigned"].includes(task.status));

  return <section className="space-y-4">
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Activity className="h-5 w-5" />Execution Release</CardTitle><CardDescription>Tasks remain planned until a preflighted wave is explicitly approved and activated. Athos can act only within an active delegation.</CardDescription></CardHeader><CardContent className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3"><div><Label>Project</Label><Select value={projectId} onChange={(event) => { setProjectId(event.target.value); setBaselineId(""); setSelected([]); }}><option value="">Select project</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></div><div><Label>Baseline</Label><Select value={baselineId} onChange={(event) => setBaselineId(event.target.value)}><option value="">Select baseline</option>{baselines.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></div><div><Label>Wave name</Label><Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Iteration 1 · frontend" /></div></div>
      {projectId && <div className="grid gap-2 md:grid-cols-2">{planned.map((task) => <label key={task.id} className="flex items-start gap-2 rounded border p-2 text-sm"><input type="checkbox" checked={selected.includes(task.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, task.id] : current.filter((id) => id !== task.id))} /><span>{task.title}<span className="block text-xs text-muted-foreground">{task.description || "Description missing"}</span></span></label>)}{!planned.length && <p className="text-sm text-muted-foreground">No planned tasks are available for this project.</p>}</div>}
      {canManage && <Button disabled={!projectId || !baselineId || !name.trim() || !selected.length || create.isPending} onClick={() => create.mutate({ baseline_id: baselineId, name, task_ids: selected, wip_limit: 1, idempotency_key: `ui-${projectId}-${Date.now()}` }, { onSuccess: () => { setName(""); setSelected([]); } })}>{create.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Create draft wave</Button>}
      {create.error && <p className="text-sm text-destructive">{errorText(create.error)}</p>}
    </CardContent></Card>
    {isLoading && <p className="text-sm text-muted-foreground">Loading execution waves…</p>}
    {waves.map((wave) => <WaveCard key={wave.id} projectId={projectId} wave={wave} tasks={projectTasks} />)}
  </section>;
}
