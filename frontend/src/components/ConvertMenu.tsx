import { useState } from "react";
import { ArrowRightCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  CONVERT_TARGET_LABELS,
  CONVERT_TARGETS,
  type ConvertPayload,
  type ConvertResult,
  type ConvertTarget,
} from "@/hooks/useDemands";
import { PLANNING_ITEM_TYPES, usePlanningItems } from "@/hooks/useBacklog";
import { ARTIFACT_TYPES } from "@/hooks/useArtifact";
import { useProjects } from "@/hooks/useProject";

const PROJECT_SCOPED_TARGETS: ConvertTarget[] = ["planning_item", "project_doc", "quick_task"];
const ITEM_TYPE_TARGETS: ConvertTarget[] = ["planning_item", "quick_task"];

/**
 * "Converter em: Task | Documento | Artefato | Knowledge Base" -- the one
 * menu shared by the demand inbox and the Docs page for any note, since
 * both "demandas ou anotações" convert into the same four things via the
 * same backend helpers (core/conversions.py).
 */
export function ConvertMenu({
  defaultTitle,
  excludeTargets,
  initialTarget,
  onConvert,
  isPending,
  error,
}: {
  defaultTitle: string;
  /** e.g. ["doc"] when converting a doc that's already a doc's own copy
   * action would be confusing to hide -- callers can still allow it. */
  excludeTargets?: ConvertTarget[];
  /** Preselects the target -- e.g. after a drag-and-drop onto a "Projeto"
   * drop zone in the inbox. Callers that want this to actually reset the
   * form when it changes should remount via a `key` prop (React won't
   * re-run useState's initializer on a prop change alone). */
  initialTarget?: ConvertTarget;
  onConvert: (payload: ConvertPayload) => void;
  isPending: boolean;
  error?: string | null;
}) {
  const targets = CONVERT_TARGETS.filter((t) => !excludeTargets?.includes(t));
  const [target, setTarget] = useState<ConvertTarget>(initialTarget ?? targets[0]);
  const [title, setTitle] = useState(defaultTitle);
  const [planningItemId, setPlanningItemId] = useState("");
  const [path, setPath] = useState("");
  const [artifactType, setArtifactType] = useState<string>("reference_doc");
  const [projectId, setProjectId] = useState("");
  const [itemType, setItemType] = useState<string>("documentation");
  const { data: planningItems, isLoading: planningLoading } = usePlanningItems();
  const { data: projects, isLoading: projectsLoading } = useProjects();

  const isProjectScoped = PROJECT_SCOPED_TARGETS.includes(target);

  function handleSubmit() {
    const payload: ConvertPayload = { target, title };
    if (target === "task") payload.planning_item_id = planningItemId;
    if (target === "doc" || target === "knowledge_base") payload.path = path || undefined;
    if (target === "artifact") {
      payload.artifact_type = artifactType;
      if (path) payload.path = path;
    }
    if (isProjectScoped) payload.project_id = projectId;
    if (ITEM_TYPE_TARGETS.includes(target)) payload.item_type = itemType;
    if (target === "project_doc" && path) payload.path = path;
    onConvert(payload);
  }

  const canSubmit =
    (target !== "task" || Boolean(planningItemId)) &&
    (target !== "knowledge_base" || Boolean(path)) &&
    (!isProjectScoped || Boolean(projectId));

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <ArrowRightCircle className="h-3.5 w-3.5" /> Converter em…
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Select value={target} className="h-8 w-40 text-xs" onChange={(e) => setTarget(e.target.value as ConvertTarget)}>
          {targets.map((t) => (
            <option key={t} value={t}>
              {CONVERT_TARGET_LABELS[t]}
            </option>
          ))}
        </Select>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Título"
          className="h-8 w-48 text-xs"
        />
        {target === "task" && (
          <Select
            value={planningItemId}
            className="h-8 w-56 text-xs"
            disabled={planningLoading}
            onChange={(e) => setPlanningItemId(e.target.value)}
          >
            <option value="">{planningLoading ? "Carregando…" : "Selecione o Planning…"}</option>
            {(planningItems ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </Select>
        )}
        {target === "artifact" && (
          <Select
            value={artifactType}
            className="h-8 w-40 text-xs"
            onChange={(e) => setArtifactType(e.target.value)}
          >
            {ARTIFACT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        )}
        {isProjectScoped && (
          <Select
            value={projectId}
            className="h-8 w-56 text-xs"
            disabled={projectsLoading}
            onChange={(e) => setProjectId(e.target.value)}
          >
            <option value="">{projectsLoading ? "Carregando…" : "Selecione o Projeto…"}</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        )}
        {ITEM_TYPE_TARGETS.includes(target) && (
          <Select value={itemType} className="h-8 w-40 text-xs" onChange={(e) => setItemType(e.target.value)}>
            {PLANNING_ITEM_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        )}
        {(target === "doc" || target === "knowledge_base" || target === "artifact" || target === "project_doc") && (
          <Input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={
              target === "knowledge_base"
                ? "caminho no vault (obrigatório).md"
                : "caminho (opcional).md"
            }
            className="h-8 w-64 text-xs"
          />
        )}
        <Button size="sm" disabled={!canSubmit || isPending} onClick={handleSubmit}>
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Converter"}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function convertResultMessage(result: ConvertResult): string {
  switch (result.entity_type) {
    case "task":
      return "Task criada com sucesso.";
    case "doc":
      return `Documento salvo em ${result.reference}.`;
    case "artifact":
      return "Artefato criado com sucesso.";
    case "knowledge_base":
      return `Nota salva na Base de Conhecimento em ${result.reference}.`;
    case "planning_item":
      return "Item adicionado ao planejamento do projeto.";
    case "project_doc":
      return `Documento vinculado ao projeto em ${result.reference}.`;
    case "quick_task":
      return "Task avulsa criada (com item de planejamento próprio).";
  }
}
