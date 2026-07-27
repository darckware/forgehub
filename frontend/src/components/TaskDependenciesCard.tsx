import { useState } from "react";
import { Link2, Loader2, Plus, Trash2, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  DEPENDENCY_TYPES,
  useCreateTaskDependency,
  useCreateTaskRequiredSkill,
  useDeleteTaskDependency,
  useTaskDependencies,
  useTaskRequiredSkills,
  useTasks,
} from "@/hooks/useTask";
import { useSkills } from "@/hooks/useAgent";

/**
 * Surfaces TaskDependency and TaskRequiredSkill -- both existed only at the
 * API layer before 2026-07-16 (full CRUD/list on the backend, zero UI):
 * dependencies back a real business rule (a task can't go "done" while a
 * dependency isn't itself done, see task.py's _ensure_dependencies_satisfied)
 * and required skills feed straight into the Governed CLI execution card's
 * eligibility check (TaskAutomationCard's useEligibleMemberships) -- without
 * this card there was no way to see *why* an agent showed up ineligible for
 * "missing required skills: <uuid>".
 */
export function TaskDependenciesCard({ taskId }: { taskId: string }) {
  const { data: dependencies = [] } = useTaskDependencies(taskId);
  const { data: allTasks = [] } = useTasks();
  const createDependency = useCreateTaskDependency(taskId);
  const deleteDependency = useDeleteTaskDependency(taskId);
  // Gates the "link to another task" row below Nenhum/Dependência --
  // Marcelo's framing: a task either depends on another one, or it has no
  // relation at all. Keeps the add-dependency controls hidden by default
  // instead of always showing an empty picker row.
  const [relation, setRelation] = useState<"none" | "dependency">("none");
  const [dependsOnTaskId, setDependsOnTaskId] = useState("");
  const [dependencyType, setDependencyType] = useState<(typeof DEPENDENCY_TYPES)[number]>("finish_to_start");

  const { data: skills = [] } = useSkills();
  const { data: requiredSkills = [] } = useTaskRequiredSkills(taskId);
  const createRequiredSkill = useCreateTaskRequiredSkill(taskId);
  const [skillId, setSkillId] = useState("");
  const [isMandatory, setIsMandatory] = useState(true);
  const [minimumProficiency, setMinimumProficiency] = useState("");

  const taskTitle = (id: string) => allTasks.find((t) => t.id === id)?.title ?? id.slice(0, 8) + "…";
  const skillName = (id: string) => skills.find((s) => s.id === id)?.name ?? id.slice(0, 8) + "…";
  // Excludes this task and anything it already depends on -- the backend
  // rejects a direct A->B/B->A cycle anyway, but this keeps the picker from
  // even offering the obvious dead-end choices.
  const dependencyCandidates = allTasks.filter(
    (t) => t.id !== taskId && !dependencies.some((d) => d.depends_on_task_id === t.id)
  );
  const skillCandidates = skills.filter((s) => !requiredSkills.some((rs) => rs.skill_id === s.id));

  function handleAddDependency() {
    if (!dependsOnTaskId) return;
    createDependency.mutate(
      { depends_on_task_id: dependsOnTaskId, dependency_type: dependencyType },
      { onSuccess: () => { setDependsOnTaskId(""); setRelation("none"); } }
    );
  }

  function handleAddRequiredSkill() {
    if (!skillId) return;
    createRequiredSkill.mutate(
      { skill_id: skillId, is_mandatory: isMandatory, minimum_proficiency: minimumProficiency || undefined },
      {
        onSuccess: () => {
          setSkillId("");
          setIsMandatory(true);
          setMinimumProficiency("");
        },
      }
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Link2 className="h-5 w-5" /> Dependencies &amp; required skills
        </CardTitle>
        <CardDescription>
          Dependencies block this task from going "done" until each one is itself done. Required skills
          gate which project members show up as eligible in the Governed CLI execution card below.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-3">
          <p className="text-sm font-medium">Blocked by</p>
          {dependencies.length === 0 ? (
            <p className="text-sm italic text-muted-foreground">No dependencies -- this task can complete freely.</p>
          ) : (
            <ul className="space-y-1.5">
              {dependencies.map((dep) => (
                <li key={dep.id} className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
                  <span>
                    {taskTitle(dep.depends_on_task_id)}{" "}
                    <Badge variant="outline" className="ml-1">
                      {dep.dependency_type.replace(/_/g, " ")}
                    </Badge>
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    disabled={deleteDependency.isPending}
                    onClick={() => deleteDependency.mutate(dep.id)}
                    aria-label="Remove dependency"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="space-y-2">
            <Label className="!mb-0 text-xs text-muted-foreground">Resposta</Label>
            <Select
              value={relation}
              className="sm:w-56"
              onChange={(e) => {
                const next = e.target.value as "none" | "dependency";
                setRelation(next);
                if (next === "none") setDependsOnTaskId("");
              }}
            >
              <option value="none">Nenhum</option>
              <option value="dependency">Dependência</option>
            </Select>
          </div>
          {relation === "dependency" && (
            <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
              <Select value={dependsOnTaskId} onChange={(e) => setDependsOnTaskId(e.target.value)}>
                <option value="">Select a task this one depends on…</option>
                {dependencyCandidates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.title}
                  </option>
                ))}
              </Select>
              <Select value={dependencyType} onChange={(e) => setDependencyType(e.target.value as (typeof DEPENDENCY_TYPES)[number])}>
                {DEPENDENCY_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type.replace(/_/g, " ")}
                  </option>
                ))}
              </Select>
              <Button
                size="sm"
                disabled={!dependsOnTaskId || createDependency.isPending}
                onClick={handleAddDependency}
              >
                {createDependency.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 h-4 w-4" />
                )}
                Add
              </Button>
            </div>
          )}
          {(createDependency.error || deleteDependency.error) && (
            <p className="text-sm text-destructive">
              {((createDependency.error ?? deleteDependency.error) as Error).message}
            </p>
          )}
        </div>

        <div className="space-y-3 border-t pt-5">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <Wrench className="h-4 w-4" /> Required skills
          </p>
          {requiredSkills.length === 0 ? (
            <p className="text-sm italic text-muted-foreground">
              No skill requirements -- any active project member is eligible.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {requiredSkills.map((rs) => (
                <li key={rs.id} className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
                  <span>
                    {skillName(rs.skill_id)}
                    {rs.minimum_proficiency && (
                      <span className="ml-1.5 text-xs text-muted-foreground">
                        min. {rs.minimum_proficiency}
                      </span>
                    )}
                  </span>
                  <Badge variant={rs.is_mandatory ? "warning" : "outline"}>
                    {rs.is_mandatory ? "mandatory" : "optional"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
          <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto_auto]">
            <Select value={skillId} onChange={(e) => setSkillId(e.target.value)}>
              <option value="">Select a required skill…</option>
              {skillCandidates.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
            <Input
              placeholder="Min. proficiency (optional)"
              value={minimumProficiency}
              onChange={(e) => setMinimumProficiency(e.target.value)}
              className="w-40"
            />
            <label className="flex items-center gap-1.5 whitespace-nowrap text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border border-input"
                checked={isMandatory}
                onChange={(e) => setIsMandatory(e.target.checked)}
              />
              <Label className="!mb-0">Mandatory</Label>
            </label>
            <Button size="sm" disabled={!skillId || createRequiredSkill.isPending} onClick={handleAddRequiredSkill}>
              {createRequiredSkill.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              Add
            </Button>
          </div>
          {createRequiredSkill.error && (
            <p className="text-sm text-destructive">{(createRequiredSkill.error as Error).message}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
