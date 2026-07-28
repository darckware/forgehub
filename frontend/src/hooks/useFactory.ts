import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Software Factory cockpit
 *
 * Read-only aggregation over the product/system_scope/backlog/task domains.
 * Backend contract: GET /api/v1/factory/cockpit (app/api/routes/factory.py).
 * The Factory domain owns no table.
 *
 * The shape is a Product -> Project tree: a product is durable and every
 * evolution of it becomes a project that walks the five phases. Product is
 * the root (not a flat project list) because this screen replaced the
 * Products and Projects pages in the sidebar -- a product with no project
 * yet still has to be reachable here.
 */

export const PHASE_KEYS = ["conception", "designer", "procedures", "execution", "quality"] as const;
export type PhaseKey = (typeof PHASE_KEYS)[number];

/** Route each phase opens when clicked, so the cockpit is a way into the
 * bottleneck and not just a read-out. */
export const PHASE_ROUTES: Record<PhaseKey, string> = {
  conception: "/conception",
  designer: "/system-map",
  procedures: "/backlog",
  execution: "/tasks",
  quality: "/governance",
};

export const phaseStatusSchema = z.object({
  key: z.enum(PHASE_KEYS),
  state: z.enum(["approved", "in_progress", "pending", "blocked"]),
  detail: z.string().nullable().optional(),
  total: z.number().nullable().optional(),
  done: z.number().nullable().optional(),
});

export type PhaseStatus = z.infer<typeof phaseStatusSchema>;

export const projectCockpitRowSchema = z.object({
  project_id: z.string(),
  project_name: z.string(),
  project_status: z.string(),
  project_description: z.string().nullable().optional(),
  version_id: z.string(),
  version_number: z.string(),
  version_status: z.string(),
  phases: z.array(phaseStatusSchema),
  planning_count: z.number().default(0),
  task_count: z.number().default(0),
});

export type ProjectCockpitRow = z.infer<typeof projectCockpitRowSchema>;

export const productVersionRowSchema = z.object({
  version_id: z.string(),
  version_number: z.string(),
  version_status: z.string(),
});

export const productCockpitRowSchema = z.object({
  product_id: z.string(),
  product_name: z.string(),
  product_status: z.string(),
  product_description: z.string().nullable().optional(),
  application_url: z.string().nullable().optional(),
  application_url_dev: z.string().nullable().optional(),
  concept_status: z.string().nullable().optional(),
  versions: z.array(productVersionRowSchema),
  projects: z.array(projectCockpitRowSchema),
});

export type ProductCockpitRow = z.infer<typeof productCockpitRowSchema>;

export const cockpitSchema = z.object({
  products: z.array(productCockpitRowSchema),
});

export type Cockpit = z.infer<typeof cockpitSchema>;

export const cockpitKeys = {
  all: ["factory", "cockpit"] as const,
};

export function useCockpit() {
  return useQuery({
    queryKey: cockpitKeys.all,
    queryFn: async () => cockpitSchema.parse(await apiClient.get("/api/v1/factory/cockpit")),
  });
}
