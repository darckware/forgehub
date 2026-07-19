import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRightCircle, Loader2 } from "lucide-react";
import i18n from "@/i18n";
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
import { useDocAreas, useDocsTree, type DocNode } from "@/hooks/useDocs";

const PROJECT_SCOPED_TARGETS: ConvertTarget[] = ["planning_item", "project_doc", "quick_task"];
const ITEM_TYPE_TARGETS: ConvertTarget[] = ["planning_item", "quick_task"];

/** doc's own path field splits into área + pasta + nome (below) instead of
 * one combined input -- the other path-taking targets keep a single field. */
const SPLIT_PATH_TARGETS: ConvertTarget[] = ["doc"];

function joinDocPath(folder: string, filename: string): string {
  const cleanFolder = folder.trim().replace(/^\/+|\/+$/g, "");
  const cleanName = filename.trim().replace(/^\/+/, "").replace(/\.(md|markdown)$/i, "");
  const base = cleanName || "note";
  return cleanFolder ? `${cleanFolder}/${base}.md` : `${base}.md`;
}

function flattenFolders(nodes: DocNode[]): string[] {
  const out: string[] = [];
  for (const n of nodes) {
    if (n.type === "dir") {
      out.push(n.path);
      if (n.children) out.push(...flattenFolders(n.children));
    }
  }
  return out;
}

/**
 * "Forward: Task | Document | Artifact | Knowledge Base" --
 * the one menu shared by the demand inbox and the Docs page for any note,
 * since both inbox demands and doc notes convert into the same targets via
 * the same backend helpers (core/conversions.py).
 */
export function ConvertMenu({
  defaultTitle,
  excludeTargets,
  onConvert,
  isPending,
  error,
}: {
  defaultTitle: string;
  /** e.g. ["doc"] when converting a doc that's already a doc's own copy
   * action would be confusing to hide -- callers can still allow it. */
  excludeTargets?: ConvertTarget[];
  onConvert: (payload: ConvertPayload) => void;
  isPending: boolean;
  error?: string | null;
}) {
  const { t } = useTranslation("convertMenu");
  const targets = CONVERT_TARGETS.filter((target) => !excludeTargets?.includes(target));
  const [target, setTarget] = useState<ConvertTarget>(targets[0]);
  const [title, setTitle] = useState(defaultTitle);
  const [planningItemId, setPlanningItemId] = useState("");
  const [path, setPath] = useState("");
  const [docAreaId, setDocAreaId] = useState("");
  const [docFolder, setDocFolder] = useState("");
  const [docFilename, setDocFilename] = useState(defaultTitle);
  const [artifactType, setArtifactType] = useState<string>("reference_doc");
  const [projectId, setProjectId] = useState("");
  const [itemType, setItemType] = useState<string>("documentation");
  const { data: planningItems, isLoading: planningLoading } = usePlanningItems();
  const { data: projects, isLoading: projectsLoading } = useProjects();
  const { data: docAreas, isLoading: docAreasLoading } = useDocAreas();
  const { data: docTree } = useDocsTree(docAreaId || null);
  const folderOptions = flattenFolders(docTree ?? []);

  const isProjectScoped = PROJECT_SCOPED_TARGETS.includes(target);
  const isSplitPath = SPLIT_PATH_TARGETS.includes(target);

  function handleSubmit() {
    const payload: ConvertPayload = { target, title };
    if (target === "task") payload.planning_item_id = planningItemId;
    if (target === "doc") {
      payload.path = joinDocPath(docFolder, docFilename);
      payload.area_id = docAreaId;
    }
    if (target === "knowledge_base") payload.path = path || undefined;
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
    (target !== "doc" || (Boolean(docAreaId) && Boolean(docFilename.trim()))) &&
    (!isProjectScoped || Boolean(projectId));

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <ArrowRightCircle className="h-3.5 w-3.5" /> {t("forward")}
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Select value={target} className="h-8 w-40 text-xs" onChange={(e) => setTarget(e.target.value as ConvertTarget)}>
          {targets.map((targetOption) => (
            <option key={targetOption} value={targetOption}>
              {t(CONVERT_TARGET_LABELS[targetOption])}
            </option>
          ))}
        </Select>
        {!isSplitPath && (
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t("titlePlaceholder")}
            className="h-8 w-48 text-xs"
          />
        )}
        {target === "task" && (
          <Select
            value={planningItemId}
            className="h-8 w-56 text-xs"
            disabled={planningLoading}
            onChange={(e) => setPlanningItemId(e.target.value)}
          >
            <option value="">{planningLoading ? t("loading") : t("selectPlanningItem")}</option>
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
            {ARTIFACT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
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
            <option value="">{projectsLoading ? t("loading") : t("selectProject")}</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        )}
        {ITEM_TYPE_TARGETS.includes(target) && (
          <Select value={itemType} className="h-8 w-40 text-xs" onChange={(e) => setItemType(e.target.value)}>
            {PLANNING_ITEM_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </Select>
        )}
        {isSplitPath && (
          <>
            <Select
              value={docAreaId}
              className="h-8 w-44 text-xs"
              disabled={docAreasLoading}
              onChange={(e) => {
                setDocAreaId(e.target.value);
                setDocFolder("");
              }}
            >
              <option value="">{docAreasLoading ? t("loading") : t("creationArea")}</option>
              {(docAreas ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
            <Input
              value={docFolder}
              onChange={(e) => setDocFolder(e.target.value)}
              placeholder={t("folderPlaceholder")}
              className="h-8 w-56 text-xs"
              list="convert-menu-doc-folders"
              disabled={!docAreaId}
            />
            <datalist id="convert-menu-doc-folders">
              {folderOptions.map((f) => (
                <option key={f} value={f} />
              ))}
            </datalist>
            <Input
              value={docFilename}
              onChange={(e) => setDocFilename(e.target.value)}
              placeholder={t("documentNamePlaceholder")}
              className="h-8 w-44 text-xs"
            />
          </>
        )}
        {(target === "knowledge_base" || target === "artifact" || target === "project_doc") && (
          <Input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={
              target === "knowledge_base"
                ? t("vaultPathPlaceholder")
                : t("pathOptionalPlaceholder")
            }
            className="h-8 w-64 text-xs"
          />
        )}
        <Button size="sm" disabled={!canSubmit || isPending} onClick={handleSubmit}>
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t("forward")}
        </Button>
      </div>
      {isSplitPath && (docFolder || docFilename) && (
        <p className="text-[11px] text-muted-foreground">
          {t("willBeSavedTo")} <code>{joinDocPath(docFolder, docFilename)}</code>
        </p>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function convertResultMessage(result: ConvertResult): string {
  const t = i18n.getFixedT(null, "convertMenu");
  switch (result.entity_type) {
    case "task":
      return t("results.task");
    case "doc":
      return t("results.doc", { reference: result.reference });
    case "artifact":
      return t("results.artifact");
    case "knowledge_base":
      return t("results.knowledge_base", { reference: result.reference });
    case "planning_item":
      return t("results.planning_item");
    case "project_doc":
      return t("results.project_doc", { reference: result.reference });
    case "quick_task":
      return t("results.quick_task");
  }
}
