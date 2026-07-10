import { useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Link2, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import {
  DOC_LINK_ENTITY_LABELS,
  DOC_LINK_ENTITY_TYPES,
  useCreateDocLink,
  useDeleteDocLink,
  useDocLinks,
  type DocLinkEntityType,
} from "@/hooks/useDocLinks";
import { useProducts, useAllProductVersions } from "@/hooks/useProduct";
import { useProjects } from "@/hooks/useProject";
import { usePipelines } from "@/hooks/usePipeline";
import { usePlanningItems } from "@/hooks/useBacklog";
import { useTasks } from "@/hooks/useTask";
import { useArtifacts } from "@/hooks/useArtifact";

const ENTITY_ROUTE: Record<DocLinkEntityType, string> = {
  product: "/product",
  product_version: "/product",
  project: "/projects",
  pipeline: "/pipeline",
  planning_item: "/backlog",
  task: "/tasks",
  artifact: "/artifact",
};

/** Options for the entity picker, one hook per type -- only the selected
 * type's hook actually fetches (React Query `enabled`). */
function useEntityOptions(type: DocLinkEntityType) {
  const products = useProducts();
  const versions = useAllProductVersions();
  const projects = useProjects();
  const pipelines = usePipelines();
  const planningItems = usePlanningItems();
  const tasks = useTasks();
  const artifacts = useArtifacts();

  switch (type) {
    case "product":
      return { options: (products.data ?? []).map((p) => ({ id: p.id, label: p.name })), isLoading: products.isLoading };
    case "product_version":
      return {
        options: (versions.data ?? []).map((v) => ({ id: v.id, label: v.version })),
        isLoading: versions.isLoading,
      };
    case "project":
      return { options: (projects.data ?? []).map((p) => ({ id: p.id, label: p.name })), isLoading: projects.isLoading };
    case "pipeline":
      return {
        options: (pipelines.data ?? []).map((p) => ({ id: p.id, label: p.name })),
        isLoading: pipelines.isLoading,
      };
    case "planning_item":
      return {
        options: (planningItems.data ?? []).map((p) => ({ id: p.id, label: p.title })),
        isLoading: planningItems.isLoading,
      };
    case "task":
      return { options: (tasks.data ?? []).map((t) => ({ id: t.id, label: t.title })), isLoading: tasks.isLoading };
    case "artifact":
      return {
        options: (artifacts.data ?? []).map((a) => ({ id: a.id, label: a.name })),
        isLoading: artifacts.isLoading,
      };
  }
}

/** Docs page's link panel: shows the current doc's Planning links and lets
 * you add a new one (pick type, pick entity, link) or remove an existing
 * one. This is the one place doc_links are created (entity detail screens
 * only display/unlink via EntityDocsCard). */
export function DocLinkPanel({ docPath }: { docPath: string }) {
  const { data: links, isLoading } = useDocLinks(docPath);
  const createLink = useCreateDocLink();
  const deleteLink = useDeleteDocLink();
  const [entityType, setEntityType] = useState<DocLinkEntityType>("product");
  const [entityId, setEntityId] = useState("");
  const { options, isLoading: optionsLoading } = useEntityOptions(entityType);

  function handleLink() {
    if (!entityId) return;
    createLink.mutate(
      { doc_path: docPath, entity_type: entityType, entity_id: entityId },
      { onSuccess: () => setEntityId("") }
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Link2 className="h-3.5 w-3.5" /> Planning links
      </p>

      {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      {links && links.length === 0 && (
        <p className="text-xs italic text-muted-foreground">No links yet.</p>
      )}
      {links?.map((link) => (
        <div key={link.id} className="flex items-center justify-between gap-2 text-sm">
          <span className="flex items-center gap-1.5 truncate">
            <span className="rounded bg-accent px-1.5 py-0.5 text-[10px] font-medium">
              {DOC_LINK_ENTITY_LABELS[link.entity_type]}
            </span>
            <Link
              to={`${ENTITY_ROUTE[link.entity_type]}/${link.entity_id}`}
              className="flex items-center gap-1 truncate hover:underline"
            >
              <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
              {link.entity_label ?? link.entity_id}
            </Link>
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 shrink-0"
            aria-label="Remove link"
            onClick={() => deleteLink.mutate(link.id)}
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-1.5 border-t border-border/60 pt-2">
        <Select
          value={entityType}
          className="h-8 w-36 text-xs"
          onChange={(e) => {
            setEntityType(e.target.value as DocLinkEntityType);
            setEntityId("");
          }}
        >
          {DOC_LINK_ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {DOC_LINK_ENTITY_LABELS[t]}
            </option>
          ))}
        </Select>
        <Select
          value={entityId}
          className="h-8 flex-1 text-xs"
          disabled={optionsLoading}
          onChange={(e) => setEntityId(e.target.value)}
        >
          <option value="">{optionsLoading ? "Loading…" : "Select…"}</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </Select>
        <Button size="sm" disabled={!entityId || createLink.isPending} onClick={handleLink}>
          {createLink.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Link"}
        </Button>
      </div>
      {createLink.isError && (
        <p className="text-xs text-destructive">{(createLink.error as Error)?.message}</p>
      )}
    </div>
  );
}
