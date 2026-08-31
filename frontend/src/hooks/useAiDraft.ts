import { useQuery } from "@tanstack/react-query";
import { apiClient, getToken } from "@/lib/api";

export type AiDraftTargetKind =
  | "concept" | "system_elements" | "planning_items" | "tasks" | "review" | "tech_stack" | "context_summary";

export interface TechStackDraftItem {
  layer:
    | "frontend"
    | "mobile"
    | "backend"
    | "database"
    | "cache"
    | "messaging"
    | "auth"
    | "storage"
    | "search"
    | "api_gateway"
    | "deploy_infra"
    | "cicd"
    | "observability"
    | "testing"
    | "documentation";
  decision: string | null;
  rationale: string | null;
}
export interface ConceptDraft {
  name: string; problem_statement: string; vision: string | null; scope_summary: string | null;
  project_description: string | null; tech_stack: TechStackDraftItem[]; documentation_markdown: string | null;
}
export interface SystemElementDraftItem { key: string; family: string; element_type: string; name: string; description: string | null }
export interface SystemRelationDraftItem { from: string; to: string; relation_type: string }
export interface SystemElementsDraft { elements: SystemElementDraftItem[]; relations: SystemRelationDraftItem[] }
export interface PlanningItemDraftItem { title: string; item_type: string; description: string | null; priority: "low" | "medium" | "high" | "critical" | null }
export interface PlanningItemsDraft { items: PlanningItemDraftItem[] }
export interface TaskDraftItem { title: string; description: string | null; plan_brief: string | null; suggested_role: "developer" | "data_engineer" | "release_manager" | "qa" | null }
export interface TasksDraft { tasks: TaskDraftItem[] }
export interface ReviewDraft { summary: string; strengths: string[]; gaps: string[]; suggested_corrections: string[] }
export interface TechStackDraft { tech_stack: TechStackDraftItem[] }
export interface ContextSummaryDraft { summary: string }

export type AiDraftByKind = {
  concept: ConceptDraft; system_elements: SystemElementsDraft; planning_items: PlanningItemsDraft;
  tasks: TasksDraft; review: ReviewDraft; tech_stack: TechStackDraft; context_summary: ContextSummaryDraft;
};

/** Backs the "Copiar prompt" button (2026-08-16, Marcelo: "preciso copiar
 * um prompt que informe o que é preciso... como fosse uma engenharia
 * reversa") -- reads the REAL instruction text build_ai_draft_prompt embeds
 * for a target_kind (GET /api/v1/ai-draft/prompt-template), instead of a
 * hand-maintained paraphrase that could drift from what the agent actually
 * receives. Static per target_kind, so a long staleTime is safe. */
export function usePromptTemplate(targetKind: AiDraftTargetKind) {
  return useQuery({
    queryKey: ["ai-draft-prompt-template", targetKind],
    queryFn: () => apiClient.get<{ target_kind: AiDraftTargetKind; instructions: string }>(
      `/api/v1/ai-draft/prompt-template?target_kind=${targetKind}`,
    ),
    staleTime: 10 * 60 * 1000,
  });
}

/** Shared SSE client for POST /api/v1/ai-draft/stream -- one icon, one
 * endpoint, one parsing shape reused by every Software Factory phase (see
 * ai_draft.py's module docstring). Copies useChat.ts's
 * useStreamImprovePrompt fetch+SSE parsing exactly (same backend event
 * shape: `: ping` keepalive comments, `data: {...}`, `event: error`,
 * `event: done`) -- the one difference is the result key is "draft", not
 * "improved_text", and it's already the target_kind's parsed/validated
 * object, not a raw string. */
export function useStreamAgentDraft<K extends AiDraftTargetKind>() {
  return async function generateDraft(
    params: { agent_id: string; target_kind: K; context: string; extra_instruction?: string; subject_id?: string },
    signal?: AbortSignal,
  ): Promise<AiDraftByKind[K]> {
    const token = getToken() ?? "";
    const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
    const url = `${apiBase}/api/v1/ai-draft/stream`;

    const resp = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(params),
      signal,
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        detail = (await resp.json()).detail ?? detail;
      } catch {
        // Body wasn't JSON -- keep the generic HTTP status message.
      }
      throw new Error(detail);
    }
    if (!resp.body) throw new Error("Empty response body");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "message";
    let draft: AiDraftByKind[K] | null = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
            continue;
          }
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          if (currentEvent === "error") {
            const parsed = JSON.parse(raw || "{}");
            throw new Error(parsed.detail ?? "ai-draft stream error");
          }
          if (currentEvent === "done") {
            currentEvent = "message";
            continue;
          }
          const parsed = JSON.parse(raw || "{}");
          if (parsed.draft) draft = parsed.draft as AiDraftByKind[K];
          currentEvent = "message";
        }
      }
    } finally {
      reader.releaseLock();
    }

    if (draft === null) throw new Error("The agent didn't return a draft.");
    return draft;
  };
}
