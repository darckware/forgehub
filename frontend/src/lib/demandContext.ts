import type { Demand } from "@/hooks/useDemands";

export function contextKey(item: Demand): string {
  return item.project_id ? `project:${item.project_id}` : item.context_area ? `area:${item.context_area}` : "unclassified";
}
